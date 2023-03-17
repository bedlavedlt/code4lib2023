import logging
from dataclasses import dataclass
from typing import Any, NamedTuple, Optional
from xml.etree.ElementTree import Element, indent, tostring


logger = logging.getLogger(__name__)


class Identifier(NamedTuple):
    """Container for OPEX Identifier element data."""

    type_: str
    value: str


class Fixity(NamedTuple):
    """Container for OPEX Fixity element data."""
    algorithm: str
    value: str


class CustomElement(Element):
    """Extends xml.etree.ElemenTree.Element with a convenience function
    'append_text_element' and provides hashability given that all subelements
    are also of type CustomElement"""

    def __init__(self, tag: str, **kwargs: dict[str, Any]):
        super().__init__(tag, **kwargs)

    def append_text_element(self,
                            tag: str,
                            text: str,
                            **kwargs: dict[str, Any]):
        element = CustomElement(tag, **kwargs)
        element.text = text
        self.append(element)

    def __repr__(self) -> str:

        return str(
            (
                self.tag, self.text, self.tail, self.attrib,
                set([i for i in iter(self)])
            )
        )

    def __eq__(self, other: object) -> bool:
        return repr(self) == repr(other)

    def __hash__(self):
        return hash(repr(self))


class _XML:
    """Common methods for subclasses"""

    def _get_body_element(self) -> CustomElement:
        ...

    def get_formatted_xml_string(self) -> str:
        """Adds a declaration and returns formatted xml string from
        self._get_body_element, ready to be written to a file."""

        text = f"""<?xml version="1.0" encoding="utf-8" standalone="yes"?>
{tostring(
        self.conditional_get_body_element(),
        encoding='unicode',
        method='xml')
    }
        """
        return text

    def print_xml(self) -> None:
        """Prints the formatted xml to the console"""
        print(self.get_formatted_xml_string())

    def write_xml_file(self, output_path: str):
        """Writes xml file from self.body_element"""
        text = self.get_formatted_xml_string()
        with open(output_path, 'w') as file:
            file.write(text)

    def conditional_get_body_element(self) -> CustomElement:

        at_least_one_attr = False
        for value in self.__dict__.values():
            if value is not None:
                at_least_one_attr = True
                break
        if at_least_one_attr:
            return self._get_body_element()
        else:
            raise AttributeError("No attributes supplied to "
                                 f"{type(self).__name__}. "
                                 "Cannot create xml body.")


@dataclass
class LegacyXIP(_XML):
    """class for constructing LegacyXIP metadata for aspace link"""

    accession_ref: Optional[str] = None
    virtual: Optional[str] = None

    def __post_init__(self):
        self.body_element = self.conditional_get_body_element()

    def _get_body_element(self) -> CustomElement:
        body = CustomElement(
            tag="LegacyXIP",
            attrib={"xmlns": "http://preservica.com/LegacyXIP"}
        )
        if self.accession_ref is not None:
            body.append_text_element("AccessionRef", self.accession_ref)
        if self.virtual is not None:
            body.append_text_element("Virtual", self.virtual)

        return body


@dataclass
class ExtendedXIP(_XML):
    """class for constructing ExtendedXIP metadata for aspace link"""

    digital_surrogate: bool

    def __post_init__(self):
        self.body_element = self._get_body_element()

    def _get_body_element(self) -> CustomElement:

        body = CustomElement(
            "ExtendedXIP", attrib={
                "xmlns": "http://preservica.com/ExtendedXIP/v6.0",
                "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance"
            }
        )
        body.append_text_element("DigitalSurrogate",
                                 str(self.digital_surrogate).lower())

        return body


@dataclass(kw_only=True)
class OPEX(_XML):
    """class for constructing and representing OPEX metadata files"""

    title: Optional[str] = None
    description: Optional[str] = None
    security_descriptor: Optional[str] = None
    identifiers: Optional[tuple[Identifier]] = None
    subfolders: Optional[tuple[str]] = None
    metadata_files: Optional[tuple[str]] = None
    content_files: Optional[tuple[str]] = None
    fixities: Optional[tuple[Fixity]] = None
    source_id: Optional[str] = None
    original_filename: Optional[str] = None
    descriptive_metadata: Optional[tuple[Element]] = None

    def __post_init__(self):
        self.properties_components = [
            self.title,
            self.description,
            self.security_descriptor,
            self.identifiers
        ]
        logger.debug(f"properties_components: {self.properties_components}")
        self.transfer_components = [
            self.source_id,
            self.original_filename,
            self.subfolders,
            self.metadata_files,
            self.content_files,
            self.fixities
        ]
        logger.debug(f"transfer_components: {self.transfer_components}")
        self._validate_arguments()
        self.body_element = self.conditional_get_body_element()

    def _get_manifest_element(self) -> CustomElement:
        """Create manifest element from attributes self.subfolders,
        self.metadata_files, and/or self.content_files. Calls
        self.get_folders_element() and self._get_files_element().

        Returns:
            CustomElement: Manifest element.
        """

        # root element
        manifest = CustomElement("opex:Manifest")

        # only create a 'folders' element if needed
        if self.subfolders is not None:
            folders_element = self._get_folders_element()
            manifest.append(folders_element)

        # only create a 'files' element if at least one file is present
        if self.metadata_files is not None or self.content_files is not None:
            files = self._get_files_element()
            manifest.append(files)

        return manifest

    def _get_folders_element(self) -> CustomElement:
        """Create folders element from self.subfolders.

        Returns:
            CustomElement: Folders element.
        """
        folders_element = CustomElement("opex:Folders")
        # create/add child 'folder' elements
        if self.subfolders is None:
            raise AttributeError("Cannot create 'opex:Folders' element. No "
                                 "attributes were supplied.")
        for child in self.subfolders:
            folders_element.append_text_element(
                tag="opex:Folder",
                text=child)

        return folders_element

    def _get_files_element(self) -> CustomElement:
        """Create files element from self.metadata_files and
        self.content_files.

        Returns:
            CustomElement: Files element.
        """
        files = CustomElement("opex:Files")
        # create/add child 'file' elements according to type
        if self.metadata_files is not None:
            for filename in self.metadata_files:
                files.append_text_element(
                    tag="opex:File",
                    text=filename,
                    attrib={'type': 'metadata'})
        if self.content_files is not None:
            for filename in self.content_files:
                files.append_text_element(
                    tag="opex:File",
                    text=filename,
                    attrib={'type': 'content'}
                )
        return files

    def _get_fixities_element(self) -> CustomElement:
        """Create fixities element from self.fixities."""

        fixities = CustomElement("opex:Fixities")

        if not self.fixities:
            raise AttributeError("Cannot create 'opex:Fixities' element. No "
                                 "folder names were supplied.")

        for type_, value in self.fixities:
            fixity = CustomElement(
                tag='opex:Fixity',
                attrib={'type': type_, 'value': value}
            )
            fixities.append(fixity)

        return fixities

    def _get_transfer_element(self) -> CustomElement:
        """Create transfer element from self.source_id, self.subfolders,
        self.metadata_files, self.content_files, self.fixities, and/or
        self.original_filename. Calls self._get_manifest_element,
        and/or self._get_fixities_element.

        Returns:
            CustomElement: Transfer element.
        """

        transfer = CustomElement('opex:Transfer')
        if self.source_id is not None:
            transfer.append_text_element('opex:SourceID', self.source_id)

        if self.subfolders or self.metadata_files or self.content_files:
            manifest = self._get_manifest_element()
            transfer.append(manifest)

        if self.fixities is not None:
            fixities = self._get_fixities_element()
            transfer.append(fixities)

        if self.original_filename is not None:
            transfer.append_text_element(
                "opex:OriginalFilename", self.original_filename
            )

        return transfer

    def _get_body_element(self) -> CustomElement:
        """Write opex body using attributes. Calls self._get_transfer_element
        and self._get_properties_element.

        Returns:
            CustomElement: Body element
        """

        body = CustomElement(
            tag='opex:OPEXMetadata',
            attrib={
                'xmlns:opex':
                "http://www.openpreservationexchange.org/opex/v1.0"
            }
        )

        if any(self.transfer_components):
            transfer = self._get_transfer_element()
            body.append(transfer)

        if any(self.properties_components):
            properties = self._get_properties_element()
            body.append(properties)

        if self.descriptive_metadata is not None:
            descriptive_metadata_element = Element("opex:DescriptiveMetadata")
            for metadata in self.descriptive_metadata:
                descriptive_metadata_element.append(metadata)
            body.append(descriptive_metadata_element)

        indent(body, space='\t')
        return body

    def _get_properties_element(self) -> CustomElement:
        """Create properties element from self.title, self.description,
        self.security_descriptor, and/or self.identifiers. Calls
        self._get_identifiers_element.

        Returns:
            CustomElement: Properties element.
        """

        properties = CustomElement('opex:Properties')

        if self.title is not None:
            properties.append_text_element("opex:Title", self.title)

        if self.description is not None:
            properties.append_text_element("opex:Description",
                                           self.description)

        if self.security_descriptor is not None:
            properties.append_text_element("opex:SecurityDescriptor",
                                           self.security_descriptor)

        if self.identifiers is not None:
            identifiers_element = self._get_identifiers_element()
            properties.append(identifiers_element)

        return properties

    def _get_identifiers_element(self) -> CustomElement:
        """Create identifiers element from self.identifiers.

        Returns:
            CustomElement: Identifiers element.
        """
        if self.identifiers is None:
            raise AttributeError("Cannot create 'opex:Identifiers' element. "
                                 "No identifiers were supplied.")
        identifiers_element = CustomElement("opex:Identifiers")
        for itype, ivalue in self.identifiers:
            identifiers_element.append_text_element(
                tag="opex:Identifier",
                text=ivalue,
                attrib={'type': itype}
            )

        return identifiers_element

    def _validate_arguments(self):
        """Checks the type of supplied attributes.

        Raises:
            ValueError: If an invalid type is found, raises ValueError.
        """

        types: dict[str, type | tuple[type]] = {
            "title": str,
            "description": str,
            "security_descriptor": str,
            "identifiers": (Identifier,),
            "subfolders": (str,),
            "metadata_files": (str,),
            "content_files": (str,),
            "fixities": (Fixity,),
            "source_id": str,
            "original_filename": str,
            "descriptive_metadata": (Element,)
        }

        invalid_variables: list[str] = []
        for attribute_name, attribute_type in types.items():
            attribute = self.__dict__[attribute_name]
            # All attributes are optional, so skip if None
            if attribute is None:
                pass
            # Check the type of iterable attributes
            elif isinstance(attribute_type, tuple):
                # Make sure items are given in a tuple.
                for item in attribute:
                    if not isinstance(item, attribute_type[0]):
                        invalid_variables.append(
                            f"Invalid value for {attribute_name}. "
                            f"Expected: tuple of "
                            f"{attribute_type[0].__name__}. "
                            f"Got tuple of {type(item).__name__} instead: "
                            f"{item}"
                        )
                else:
                    for item in attribute:
                        if not isinstance(item, attribute_type[0]):
                            invalid_variables.append(
                                f"Invalid value in {attribute_name}. "
                                f"Expected {attribute_type[0].__name__}. "
                                f"Got {type(attribute).__name__}: "
                                f"{attribute}"
                            )

        if invalid_variables:
            error_text = "\n            ".join(
                text for text in invalid_variables
            )
            raise ValueError(error_text)


@dataclass
class DublinCore(_XML):
    """object representing dublincore metadata _XML"""
    title: Optional[tuple[str]] = None
    creator: Optional[tuple[str]] = None
    subject: Optional[tuple[str]] = None
    description: Optional[tuple[str]] = None
    publisher: Optional[tuple[str]] = None
    contributor: Optional[tuple[str]] = None
    date: Optional[tuple[str]] = None
    type: Optional[tuple[str]] = None
    format: Optional[tuple[str]] = None
    identifier: Optional[tuple[str]] = None
    source: Optional[tuple[str]] = None
    language: Optional[tuple[str]] = None
    relation: Optional[tuple[str]] = None
    coverage: Optional[tuple[str]] = None
    rights: Optional[tuple[str]] = None

    def __post_init__(self):
        self.body_element = self.conditional_get_body_element()

    def _get_body_element(self) -> CustomElement:
        """Create body element from attributes.

        Returns:
            CustomElement: _description_
        """

        args = (
            ("dc:title", self.title),
            ("dc:creator", self.creator),
            ("dc:subject", self.subject),
            ("dc:description", self.description),
            ("dc:publisher", self.publisher),
            ("dc:contributor", self.contributor),
            ("dc:date", self.date),
            ("dc:type", self.type),
            ("dc:format", self.format),
            ("dc:identifier", self.identifier),
            ("dc:source", self.source),
            ("dc:language", self.language),
            ("dc:relation", self.relation),
            ("dc:coverage", self.coverage),
            ("dc:rights", self.rights)
        )

        body = CustomElement(
            "oai_dc:dc",
            attrib={
                "xsi:schemaLocation":
                    "http://www.openarchives.org/OAI/2.0/oai_dc/ oai_dc.xsd",
                "xmlns:dc": "http://purl.org/dc/elements/1.1/",
                "xmlns:oai_dc": "http://www.openarchives.org/OAI/2.0/oai_dc/",
                "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance"
            }
        )

        for tag, value in args:
            if value is not None:
                for text in value:
                    body.append_text_element(tag, text)

        indent(body, space='\t')

        return body
