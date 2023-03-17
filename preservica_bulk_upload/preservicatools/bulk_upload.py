import csv
import logging
import os
import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, Generator, Optional, TypeAlias

from humanize import naturalsize

from preservicatools.xml_objects import (OPEX, CustomElement, DublinCore,
                                         ExtendedXIP, Fixity, Identifier,
                                         LegacyXIP)

logger = logging.getLogger(__name__)

# These lists are used to validate column headers in the input csv
COMMON_COLUMNS = ['filepath', 'digital object name',
                  'security tag', 'digital surrogate']
ASPACE_COLUMNS = ['archival object number']
MANUAL_COLUMNS = ['collection name', 'collection number']
DC_COLUMNS = ['dc title', 'dc creator', 'dc subject', 'dc description',
              'dc publisher', 'dc contributor', 'dc date', 'dc type',
              'dc format', 'dc identifier', 'dc source', 'dc language',
              'dc relation', 'dc coverage', 'dc rights']
ASPACE_COLUMN_SET = set(ASPACE_COLUMNS + COMMON_COLUMNS)
MANUAL_COLUMN_SET = set(MANUAL_COLUMNS + COMMON_COLUMNS)
ALL_COLUMNS_SET = ASPACE_COLUMN_SET | MANUAL_COLUMN_SET | set(DC_COLUMNS)
# Values used to verify upload type
ASPACE = 'aspace'
MANUAL = 'manual'


LabeledRow: TypeAlias = tuple[tuple[str, str], ...]
DublinCoreRow: TypeAlias = dict[str, list[str]]


def undo_file_moves(moves_csv_path: str):
    """Undo file moves that have been recorded in a container's moves.csv file.
    Used in cases where the bulk_upload.Container has been discarded
    but files need to be moved back to their original location."""

    file_moves = _FileMoves(moves_csv_path=moves_csv_path)
    file_moves.undo_moves()


def _get_dc_data_from_row(labeled_row: LabeledRow) -> dict[str, list[str]]:
    """Find and repackage DublinCore columns into a dictionary of lists with
    the column name as keys and column values as list items.

    Args:
        labeled_row (LabeledRow): tuple of tuples containing
        (column_name, column_value) for each column of a csv row.

    Returns:
        dc_row_dict (dict[str,list[str]]): A dictionary representing a set of
        columns and their values, accounting for potential duplicate column
        names by placing column values into lists.
    """

    dc_row_dict: DublinCoreRow = {}

    for column_name, column_value in labeled_row:
        if column_name in DC_COLUMNS:
            dc_row_dict.setdefault(column_name, list()).append(column_value)

    return dc_row_dict


def _get_collection_from_row(labeled_row: LabeledRow, upload_type: str):
    """Creates the _Collection/_DigitalObject/_Asset structure
    for one row of file data and returns the resulting _Collection.
    """

    dc_row_data = _get_dc_data_from_row(labeled_row)
    if dc_row_data:
        logger.debug(f"DublinCore data found: {dc_row_data}")
    else:
        logger.debug("No DublinCore data found.")
    base_row_data: dict[str, str] = {
        key: value for key, value in labeled_row if key not in DC_COLUMNS
    }
    logger.debug(f"Non-DublinCore row data: {base_row_data}")

    digital_surrogate = base_row_data['digital surrogate'].lower().strip()
    if digital_surrogate not in ('true', 'false'):
        raise ValueError("Invalid value for 'digital surrogate'. Expected "
                         f"'true' or 'false'. Got {digital_surrogate}.")
    else:
        digital_surrogate = True if digital_surrogate == 'true' else False

    security_descriptor = base_row_data['security tag'].lower().strip()
    digital_object_name = base_row_data['digital object name']
    file_descriptive_metadata = (
        DublinCore(
            **{key.replace('dc ', '').strip().replace(" ", "_"): value
                for key, value in dc_row_data.items()}
        ).body_element,
    ) if dc_row_data else None

    if upload_type == ASPACE:
        collection_name = (
            "archival_object_"
            f"{base_row_data['archival object number']}"
        )
        collection_description = "Archival Object"
        collection_identifiers = (Identifier('code', collection_name),)
        digital_object_identifiers = (
            Identifier('code', base_row_data['digital object name']),
        )
        file_identifiers = None
        digital_object_descriptive_metadata = (
            LegacyXIP(accession_ref='catalog').body_element,
            ExtendedXIP(digital_surrogate=digital_surrogate).body_element
        )
        collection_descriptive_metadata = (
            LegacyXIP(virtual='false').body_element,
        )
        collection_id = None
    # For non-aspace upload,
    # deal with 'collection name' and 'collection number'
    elif upload_type == MANUAL:
        collection_name = base_row_data['collection name']
        collection_description = base_row_data['collection number']
        collection_identifiers = (
            Identifier('code', base_row_data['collection number']),
        )
        digital_object_identifiers = (
            Identifier('code', base_row_data['collection number']),
        )
        file_identifiers = (
            Identifier('code', base_row_data['collection number']),
        )
        digital_object_descriptive_metadata = None
        collection_descriptive_metadata = None
        collection_id = base_row_data['collection number']
    else:
        raise ValueError(f"Unknown upload type: {upload_type}.")

    logger.debug(f"Initializing collection '{collection_name}'.")
    collection = _Collection(
        name=collection_name,
        description=collection_description,
        security_descriptor=security_descriptor,
        identifiers=collection_identifiers,
        collection_id=collection_id,
        descriptive_metadata=collection_descriptive_metadata
    )
    logger.debug(f"Initializing digital object '{digital_object_name}'.")
    digital_object = _DigitalObject(
        name=digital_object_name,
        description="Digital Object",
        security_descriptor=security_descriptor,
        identifiers=digital_object_identifiers,
        digital_surrogate=digital_surrogate,
        descriptive_metadata=digital_object_descriptive_metadata
    )
    logger.debug(f"Initializing asset '{base_row_data['filepath']}'.")
    asset = _Asset(
        input_path=base_row_data['filepath'],
        identifiers=file_identifiers,
        descriptive_metadata=file_descriptive_metadata
    )

    asset.description = (f"File Type: {asset.file_extension}; "
                         f"File Size: {asset.file_size}; "
                         f"Created: {asset.ctime}; "
                         f"Modified: {asset.mtime}")

    logger.debug(f"Asset data: {asset}.")
    digital_object.add_asset(asset)
    logger.debug(f"Digital object data: {digital_object}.")
    logger.debug(f"Adding digital object '{digital_object.name}' "
                 f"to collection '{collection.name}'")
    collection.add_digital_object(digital_object)
    logger.debug(f"Collection data: {collection}.")

    return collection


def _validate_filepaths_and_digital_objects(csv_path: str) -> None:
    """Ensure that the given files exist and that filenames don't match
    their digital object name.
    Args:
        fps_and_dos (list[tuple[str,str]]): (filepath, digital_object_name)
        for row in csv
    """

    column_names = _get_column_names_from_csv(csv_path)

    filepaths, digital_objects = zip(*[
        (row[column_names.index('filepath')],
         row[column_names.index('digital object name')])
        for row in _get_row_generator(csv_path)
    ])

    logger.debug(f"Number of rows detected: {len(filepaths)}")

    filepaths = tuple(map(Path, filepaths))

    all_filepaths = set()
    duplicate_filepaths = [
        filepath for filepath in filepaths if filepath in all_filepaths
        or (all_filepaths.add(filepath) or False)
    ]
    if duplicate_filepaths:
        duplicate_fp_text = "\n".join(
            str(filepath) for filepath in duplicate_filepaths)
        logger.error(
            "Duplicate filepaths detected in "
            f"{csv_path}:\n{duplicate_fp_text}"
        )
        raise ValueError("Duplicate filepaths detected in csv:\n"
                         f"{duplicate_fp_text}")

    # Ensure that filepaths exist
    invalid_filepaths = [
        filepath.resolve().as_posix() for filepath in filepaths
        if not filepath.exists()
    ]
    if invalid_filepaths:
        fp_text = "\n".join(str(filepath) for filepath in invalid_filepaths)
        logger.error(
            "Invalid filepaths detected in "
            f"{csv_path}:\n{fp_text}"
        )
        raise ValueError(f"Files do not exist:\n{fp_text}")
    # Ensure that no filepaths have the same name as a digital object
    invalid_names = set(
        [filepath.name for filepath in filepaths
            if filepath.name in digital_objects]
    )
    if invalid_names:
        matches_text = "\n".join(str(item) for item in invalid_names)
        logger.error("Matching filename and digital object name detected in "
                     f"{csv_path}:\n{matches_text}")
        raise ValueError(
            "Files and digital objects with "
            f"matching names detected:\n{matches_text}"
        )


def _get_column_names_from_csv(csv_path: str):

    with open(csv_path, newline='') as file:
        reader = csv.reader(file, dialect='excel')
        column_names = [column_name.lower().strip() for column_name
                        in next(reader)]
    return column_names


def _get_row_generator(csv_path: str) -> (
    Generator[list[str], None, None]
):
    """Takes a csv with column headers and returns a generator of labeled rows.

    Args:
        csv_path (str): Path to a csv file containing bulk upload data.

    Yields:
        LabeledRow: Single row from the CSV as a tuple of tuples containing
        ((column_name, column_value)
    """

    with open(csv_path, newline='') as file:
        reader = csv.reader(file, dialect='excel')
        next(reader)
        # Continue reading the rest of the rows as content
        for row in reader:
            yield row


def _infer_upload_type(column_names):
    """Infer upload type based on whether the non-dublincore columns
    match a pre-defined set of columns."""

    # Everything but the dublincore columns
    non_dc_columns = {
        column_name for column_name in column_names
        if column_name not in DC_COLUMNS
    }

    # Check for duplicate column names,
    # excluding dublincore, since it can have multiples
    non_dc_column_names_set: set[str] = set()
    # This line uses a set comprehension to populate a set
    # with only those columns that appear more than once
    # If the column name being checked is already in column_names_set,
    # then it gets added to the duplicates list
    # Otherwise, it is added to column_names_set
    # and not added to duplicate_column_names.
    duplicate_column_names = {
        column_name for column_name in non_dc_columns
        if column_name in non_dc_column_names_set
        or (non_dc_column_names_set.add(column_name) or False)
    }
    invalid_column_names = non_dc_column_names_set.difference(ALL_COLUMNS_SET)\
        if non_dc_column_names_set else None
    if invalid_column_names:
        raise ValueError(f"Invalid column names: {invalid_column_names}")
    if duplicate_column_names:
        raise ValueError(
            f"Duplicate column names: {duplicate_column_names}")

    if non_dc_columns == ASPACE_COLUMN_SET:
        upload_type = ASPACE
    elif non_dc_columns == MANUAL_COLUMN_SET:
        upload_type = MANUAL
    else:
        error_text = f"""Expected one of two sets of columns \
(not counting dublin core columns):

    {ASPACE_COLUMN_SET}
    or
    {MANUAL_COLUMN_SET}

    Got: {non_dc_columns}"""
        raise ValueError(error_text)

    return upload_type


@dataclass
class _FileMove:
    original_location: str
    destination: str

    def move(self):
        """Move file from self.original_location to self.destination
        via shutil.move without overwriting existing files."""

        if os.path.exists(self.destination):
            raise ValueError("Destination path points to a file that already "
                             "exists: {self.destination}")
        shutil.move(self.original_location, self.destination)

    def undo_move(self):
        """Move file from self.destination to self.original_location"""
        self._swap()
        self.move()
        self._swap()

    def _swap(self):
        """Swap self.original_location and self.destination"""

        original_location = self.original_location
        self.original_location = self.destination
        self.destination = original_location


class _FileMoves:

    def __init__(self, file_moves: Optional[list[_FileMove]] = None,
                 moves_csv_path: Optional[str] = None):

        if file_moves is not None:
            for file in file_moves:
                self.add_file_move(file)

        if moves_csv_path:
            self.add_file_moves_from_csv(moves_csv_path)

    def add_file_moves_from_csv(self, moves_csv_path: str):

        with open(moves_csv_path, newline='') as moves_file:
            reader = csv.reader(moves_file, dialect='excel')

            column_names = [name.strip() for name in next(reader)]
            if set(column_names) != set(('original_location',
                                         'destination')):
                raise ValueError("Invalid column names. Expected "
                                 "'original_location' and 'destination'."
                                 f"Got '{', '.join(c for c in column_names)}'")

            for original_location, destination in reader:
                self.add_file_move(_FileMove(
                    original_location=original_location,
                    destination=destination))

    def move(self):

        file_moves = self._validate_file_moves()
        for file in file_moves:
            file.move()

    def undo_moves(self):

        for file_move in self.moves:
            file_move.undo_move()

    def _validate_file_moves(self) -> list[_FileMove]:
        """Bulk validation of _FileMove object data.

        Raises:
            AttributeError:
            ValueError: _description_
            ValueError: _description_

        Returns:
            list[_FileMove]: _description_
        """
        if 'moves' not in self.__dict__:
            raise AttributeError("No moves to process.")

        nonexistent_files = list(
            filter(lambda file: not os.path.exists(file.original_location),
                   self.moves)
        )
        preexisting_files = list(
            filter(lambda file: os.path.exists(file.destination), self.moves)
        )

        if nonexistent_files:
            error_text = "\n".join(
                file.original_location for file in nonexistent_files
            )
            raise ValueError(
                "The following files do not exist, "
                "and therefore cannot be moved:\n"
                f"{error_text}"
                )

        if preexisting_files:
            error_text = "\n".join(
                file.destination for file in preexisting_files
            )
            raise ValueError(
                "The following files already exist, "
                "and would be overwritten by this operation: "
                f"{error_text}")

        return self.moves

    def add_file_move(self, file: _FileMove):

        if 'moves' not in self.__dict__:
            self.moves: list[_FileMove] = []
        self.moves.append(file)


@dataclass(kw_only=True)
class _OPEXTarget(ABC):
    """Base class for objects representing levels of the OPEX bulk upload
    container hierarchy. Provides optional OPEX fields and
    """

    name: str = field(
        init=False,
        repr=True,
        default_factory=str,
        hash=True
    )
    output_path: Optional[str] = field(
        init=False,
        repr=True,
        default=None,
        hash=False
    )
    opex_path: Optional[str] = field(
        init=False,
        repr=True,
        default=None,
        hash=False
    )
    # Optional[tuple[CustomElement, ...]] = None

    def __post_init__(self):
        self._logger = logging.getLogger(
            f"{__name__}.{self.__class__.__name__}"
        )

    @abstractmethod
    def get_opex(self) -> OPEX:
        """Create and return an OPEX metadata object
        based on instance attributes."""
        ...

    def _build(self):
        """Build a bulk_upload container by recursively calling
        this function on every level of the container hierarchy"""

        self.opex = self.get_opex()
        if isinstance(self, _Folder):
            if not self.output_path:
                raise AttributeError("Output path not supplied "
                                     f"for {self.name}")
            if not self.opex_path:
                raise AttributeError(f"OPEX path not supplied for {self.name}")
            if not os.path.exists(self.output_path):
                os.mkdir(self.output_path)
            self.opex.write_xml_file(str(self.opex_path))
            for child in self.get_children():
                child._build()
        elif isinstance(self, _Asset):
            self.opex.write_xml_file(str(self.opex_path))


@dataclass
class _Child(_OPEXTarget):
    """Class for identifying bulk upload hierarchy objects that can be
    contained within another bulk upload hierarchy object."""
    identifiers: Optional[tuple[Identifier]] = None
    descriptive_metadata: Optional[tuple[CustomElement, ...]] = field(
        init=True,
        repr=False,
        default=None
    )


@dataclass(kw_only=True)
class _Folder(_OPEXTarget):
    """Base class for Container, _Collection, and _DigitalObject"""

    def __post_init__(self):  # pragma: no cover
        self._add_child_alias = "add_child"
        self._child_type = _Child
        self._children: dict[str, Any] = {}
        self._logger = logging.getLogger(
            f"{__name__}.{self.__class__.__name__}"
        )

    @abstractmethod
    def get_children(self) -> tuple[_Child]:
        return tuple(self._children.values())

    def _add_child(self, new_child: _Child, child_type: type):
        """Defines setter behavior for child classes."""

        if not isinstance(new_child, child_type):
            raise ValueError(f"Expected {child_type}. Got '{type(new_child)}'")

        def get_set_minus_children(child: _Child) -> set[tuple[str, _Child]]:
            return set(
                [(k, v) for k, v in child.__dict__.items() if k != "_children"]
            )

        new_child_set_minus_children = get_set_minus_children(new_child)
        self._logger.debug("New child set minus children: "
                           f"{new_child_set_minus_children}")
        conflicting_child = [
            get_set_minus_children(child) for child in self.get_children()
            if (
                child.name == new_child.name and
                get_set_minus_children(child) != new_child_set_minus_children)
        ]
        if conflicting_child:
            raise ValueError(
                f"A {child_type.__name__.lower()} named '{new_child.name}'"
                f"is already present in {self.__class__.__name__}"
                f"'{self.name}' with conflicting values:"
                f"""
            Old {child_type.__name__}: {
                conflicting_child[0].difference(new_child_set_minus_children)
                }
            New {child_type.__name__}: {
                new_child_set_minus_children.difference(conflicting_child[0])
                }
            """)

        twin_children = [
            child for child in self.get_children()
            if get_set_minus_children(child) == new_child_set_minus_children
        ]
        if twin_children:
            logger.debug(f"Twin children: {twin_children}")
            logger.debug(
                "Twin children type: "
                f"{[type(twin_child) for twin_child in twin_children]}"
            )
            logger.debug(f"Twin children length: {twin_children}")
            
            twin_child = twin_children[0]
            if (isinstance(new_child, _Folder)
                    and isinstance(twin_child, _Folder)):
                for child in new_child.get_children():
                    twin_child._add_child(child, twin_child._child_type)
                    logger.debug("Adding child to "
                                 f"{twin_child.name}: {child.name}")
        elif len(twin_children) > 1:
            raise ValueError("Multiple of the same child already present. "
                             f"{new_child.name}")
        else:
            self._logger.debug(f"No matching children found in {self.name}. "
                               f"Adding {new_child.name} as a new entry.")
            self._children[new_child.name] = new_child

    def _get_child(self, child_name: str) -> Any:
        """Retrieve a child object from self._children"""

        if child_name in self._children:
            return self._children[child_name]
        else:
            raise KeyError(
                f"No {self._child_type.__name__} named {child_name} "
                f"is present in {self.name}."
            )

    def list_descendants(self, indent: int = 0):  # pragma: no cover

        white_space = indent * 4 * ' '
        for child in self.get_children():
            print(white_space + child.name)
            if isinstance(child, _Folder):
                child.list_descendants(indent + 1)

    def _generate_output_paths(self):
        """Propagate output paths and opex output paths downward through
        the container tree using parent path and child name."""

        if not self.output_path:
            raise ValueError(f"Output path not set for {self.name}")

        self.opex_path = os.path.join(self.output_path, self.name + ".opex")

        for child in self.get_children():

            assert isinstance(child, self._child_type)

            child.output_path = os.path.join(self.output_path, child.name)
            self._logger.debug(
                f"{child.name} output path: {child.output_path}"
            )

            if child.output_path and os.path.exists(child.output_path):
                raise ValueError(f"Duplicate output path: {child.output_path}")

            if isinstance(child, _Folder):
                child._generate_output_paths()
            elif isinstance(child, _Asset):
                child_opex = child.name + ".opex"
                child.opex_path = os.path.join(self.output_path, child_opex)
                self._logger.debug(
                    f"{child.name} output path: {child.output_path}"
                )


@dataclass(kw_only=True)
class _Asset(_Child):
    input_path: str
    fixities: Optional[tuple[Fixity]] = field(
        init=False,
        repr=True,
        default=None)

    def __post_init__(self):
        input_path = Path(self.input_path).resolve()
        self.name = input_path.name
        file_data = input_path.stat()
        self.file_extension = input_path.suffix.strip('.')
        self.file_size = naturalsize(file_data.st_size)
        self.ctime = datetime.fromtimestamp(
            file_data.st_ctime).strftime("%Y-%m-%d %H:%M:%S")
        self.mtime = datetime.fromtimestamp(
            file_data.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        self.fixities = (Fixity('SHA-256', self.get_sha256()),)
        self.description = (f"File Type: {self.file_extension}; "
                            f"File Size: {self.file_size} Bytes; "
                            f"Created: {self.ctime}; "
                            f"Modified: {self.mtime}")
        self._logger = logging.getLogger(
            f"{__name__}.{self.__class__.__name__}"
        )

    def get_sha256(self) -> str:
        """Returns the sha256 checksum of the file."""
        with open(self.input_path, 'rb') as f:
            file_bytes = f.read()
            return sha256(file_bytes).hexdigest()

    def get_opex(self) -> OPEX:
        self._logger.debug(f"Building OPEX for {self.name}.")
        return OPEX(
            descriptive_metadata=self.descriptive_metadata,
            description=self.description,
            identifiers=self.identifiers,
            fixities=self.fixities
        )


@dataclass(kw_only=True)
class _DigitalObject(_Folder, _Child):
    name: str
    description: str
    security_descriptor: str
    digital_surrogate: bool

    def __post_init__(self):
        self._children: dict[str, _Asset] = {}
        self._child_type = _Asset
        self._add_child_alias = "add_asset"
        self._logger = logging.getLogger(
            f"{__name__}.{self.__class__.__name__}"
        )

    def get_children(self):
        return tuple(self._children.values())

    def list_assets(self):
        return tuple(self._children.keys())

    @property
    def assets(self):
        return self.get_children()

    def add_asset(self, asset: _Asset):
        self._logger.debug(
            f"Adding asset '{asset.name}' to digital object '{self.name}'"
        )
        self._add_child(asset, self._child_type)

    def get_opex(self):
        return OPEX(descriptive_metadata=self.descriptive_metadata,
                    description=self.description,
                    identifiers=self.identifiers,
                    security_descriptor=self.security_descriptor,
                    content_files=self.list_assets(),
                    metadata_files=tuple(
                        [f"{name}.opex" for name in self.list_assets()]
                    ),
                    title=self.name)

    def get_asset(self, asset_name: str) -> _Asset:
        return self._get_child(asset_name)

    def __getitem__(self, child_name: str) -> _Asset:
        return self.get_asset(child_name)


@dataclass(kw_only=True)
class _Collection(_Folder, _Child):

    name: str
    description: str
    security_descriptor: str
    collection_id: Optional[str] = None

    def __post_init__(self):
        self._child_type = _DigitalObject
        self._add_child_alias = "add_digital_object"
        self._children: dict[str, _DigitalObject] = {}
        self._logger = logging.getLogger(
            f"{__name__}.{self.__class__.__name__}"
        )

    def get_children(self):
        return tuple(self._children.values())

    def list_digital_objects(self):
        return tuple(self._children.keys())

    @property
    def digital_objects(self):
        return self.get_children()

    def add_digital_object(self, digital_object: _DigitalObject):
        return self._add_child(digital_object, _DigitalObject)

    def get_opex(self):
        self._logger.debug(f"Building OPEX for {self.name}.")
        return OPEX(descriptive_metadata=self.descriptive_metadata,
                    description=self.description,
                    identifiers=self.identifiers,
                    subfolders=self.list_digital_objects(),
                    security_descriptor=self.security_descriptor,
                    title=self.name)

    def get_digital_object(self, digital_object_name: str) -> _DigitalObject:
        return self._get_child(digital_object_name)

    def __getitem__(self, child_name: str) -> _DigitalObject:
        return self.get_digital_object(child_name)


@dataclass(kw_only=True)
class Container(_Folder):
    """Create and manage an OPEX bulk upload container.

    Args:
        csv_path (str): Path to a csv containing these columns, at minimum:
        'filepath', 'digital object name', 'security tag', 'digital surrogate',
        and either 'collection name' and 'collection number'
        or 'archival object number' (for uploads intended to be linked
        to ArchivesSpace).

    Raises:
        ValueError: If any digital objects have the same name.
        AttributeError: If any assets lack output_path at move time.
        AttributeError: If the container lacks output_path at move time.

    Returns:
        preservicatools.bulk_upload.Container

    >>> from preservicatools.bulk_upload import Container
    >>> c = Container(csv_path="./tests/csv/simple_aspace.csv",
    ...               output_folder="./tests/output")
    >>> c.build()
    >>> c.undo_file_moves()

    """
    csv_path: str
    output_folder: str

    def __post_init__(self):
        self._logger = logging.getLogger(
            f"{__name__}.{self.__class__.__name__}"
        )
        self.name = datetime.now().strftime("Container_%Y-%m-%d_%H_%M_%S")
        self._output_folder = os.path.abspath(self.output_folder)
        self.output_path = os.path.join(self._output_folder, self.name)
        self._child_type = _Collection
        self._add_child_alias = "_add_collection"
        self._children: dict[str, _Collection] = {}
        self._from_csv(self.csv_path)
        self._generate_output_paths()

    def get_children(self) -> tuple[_Collection, ...]:
        """Return a tuple of all child objects
        """
        return tuple(self._children.values())

    def list_collections(self) -> tuple[str, ...]:
        """Get a tuple containing the names of all collections
        in the container.

        Returns:
            tuple[str, ...]: Collection names which can be used with
            Container.get_collection() or with Container[collection_name]
            syntax to retrieve a specific collection.
        """

        return tuple(self._children.keys())

    def list_digital_objects(self) -> tuple[tuple[str, str], ...]:
        """Get a tuple of tuples containing the collection name and
        digital object name for each digital object in the
        container.

        Returns:
            tuple[tuple[str, str], ...]: (
                (collection_name, digital_object_name)
            ) to be used with Container[collection_name][digital_object_name]
            for retrieval of nested digital objects.
        """

        return tuple([(collection.name, digital_object.name)
                      for collection in self.collections for digital_object
                      in collection.digital_objects])

    def list_assets(self) -> tuple[tuple[str, str, str], ...]:
        """Get a tuple of tuples containing the collection name,
        digital object name, and asset name for each asset in the container.

        Returns:
            tuple[tuple[str, str, str], ...]: (
                (collection_name, digital_object_name, asset_name), ...
            ) to be used via
            ContainerContainer[collection_name][digital_object_name][asset_name]
        """
        return tuple([
            (collection.name, digital_object.name, asset.name)
            for collection in self.collections
            for digital_object in collection.digital_objects
            for asset in digital_object.assets])

    @property
    def collections(self) -> tuple[_Collection, ...]:
        """Get a tuple of all _Collection objects nested within the container.
        """
        return self.get_children()

    @property
    def digital_objects(self) -> tuple[_DigitalObject, ...]:
        """Get a tuple of _DigitalObject objects nested within the collection.
        """
        return tuple(
            [do for collection in self.collections
             for do in collection.digital_objects]
        )

    @property
    def assets(self) -> tuple[_Asset, ...]:
        """Get a tuple containing all _Asset objects nested
        within the container.
        """
        return tuple(
            [asset for digital_object in self.digital_objects
             for asset in digital_object.assets]
        )

    def _add_collection(self, collection: _Collection):
        self._add_child(collection, _Collection)

    def get_collection(self, collection_name: str) -> _Collection:
        """Get a _Collection object by name."""
        return self._get_child(collection_name)

    def __getitem__(self, child_name: str) -> _Collection:
        """Get a _Collection object by name."""
        return self._get_child(child_name)

    def _check_for_duplicate_digital_objects(self):
        """Ensure no duplicate objects share the same name.

        Raises:
            ValueError: If duplicate digital objects are found.
        """
        all_digital_objects: set[str] = set()
        collections = [col for col in self.get_children()]
        duplicate_digital_objects: list[str] = [
            digital_object.name
            for collection in collections
            for digital_object in collection.digital_objects
            if digital_object.name in all_digital_objects
            or (all_digital_objects.add(digital_object.name) or False)
        ]
        if duplicate_digital_objects:
            all_duplicates_listed = [
                collection.name + "/" + duplicate_digital_object
                for collection in collections
                for duplicate_digital_object in duplicate_digital_objects
                if duplicate_digital_object
                in collection.list_digital_objects()
            ]
            raise ValueError("Duplicate digital objects found: "
                             f"{all_duplicates_listed}.")

    def _from_csv(self, csv_path: str):
        """Create the bulk upload model from csv data:
        Args:
            csv_path (str): Path to comma separated file containing valid
            bulk upload data

            output_folder (str): The folder where the tree is to
            be written.
        """

        # Ensure that all the supplied files exist and that no
        # filenames match their parent digital object.
        csv_path = Path(csv_path).resolve().as_posix()
        self._logger.debug(
            f"Building container from csv: {csv_path}"
        )
        self.column_names = _get_column_names_from_csv(csv_path)
        upload_type = _infer_upload_type(self.column_names)
        self._logger.debug(f"Upload type: {upload_type}")
        self._logger.debug("Validating filepaths and digital objects.")
        _validate_filepaths_and_digital_objects(csv_path)
        self._logger.debug(
            "Validation of filepaths and digital objects complete."
            )
        row_generator = _get_row_generator(csv_path)

        for row in row_generator:
            labeled_row: LabeledRow = tuple(zip(self.column_names, row))
            self._logger.debug(
                "Creating collection from row "
                f"{labeled_row}"
            )
            collection = _get_collection_from_row(labeled_row, upload_type)
            if collection is not None:
                self._add_collection(collection)
        self._check_for_duplicate_digital_objects()

    def _process_moves(self):

        if self.output_path is not None:
            self.file_moves_path = os.path.join(self.output_path, "moves.csv")
        else:
            raise AttributeError("No output path found for "
                                 f"container: {self.name}")

        files = _FileMoves()
        for asset in self.assets:
            if asset.output_path is None:
                raise AttributeError("No output path found for "
                                     f"asset: {asset.name}.")
            files.add_file_move(_FileMove(asset.input_path, asset.output_path))

        files.move()

        with open(self.file_moves_path, "w", newline='') as moves_file:
            writer = csv.writer(moves_file)
            writer.writerow(['original_location', 'destination'])
            writer.writerows([[file.original_location, file.destination]
                              for file in files.moves])

    def get_opex(self):
        self._logger.debug(f"Building OPEX for {self.name}")
        return OPEX(subfolders=tuple(map(lambda x: x.name, self.collections)))

    def undo_file_moves(self):
        """Undo any file moves processed by the container.
        """
        undo_file_moves(self.file_moves_path)

    def build(self):
        self._build()
        self._process_moves()
