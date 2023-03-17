import unittest
from pathlib import Path
import re
import shutil
import logging
from datetime import datetime
from typing import TypeAlias

from preservicatools import bulk_upload, setup_logging

log = setup_logging.setup_logger(__name__)
logger = logging.getLogger(__name__)

TESTS = Path('./tests')
INPUT = TESTS/'input'
OUTPUT = TESTS/'output'
CSV = TESTS/'CSV'
XML = TESTS/'XML'
MOVES = CSV/'moves.csv'
MOVES_INVALID_COLUMNS = CSV/'moves_invalid_columns.csv'
MOVES_OVERWRITE = CSV/'moves_overwrite.csv'
MOVES_NONEXISTENT = CSV/'moves_nonexistent.csv'
SIMPLE_ASPACE = CSV/'simple_aspace.csv'
SIMPLE_MANUAL = CSV/'simple_manual.csv'
MANUAL_DC = CSV/'manual_dc.csv'
ASPACE_DC = CSV/'aspace_dc.csv'
ASPACE_EXPECTED = CSV/'aspace_expected.csv'
MANUAL_EXPECTED = CSV/'manual_expected.csv'
MULTIPLE_DC_EXPECTED = CSV/'multiple_dc_expected.csv'
MULTIPLE_DC = CSV/'multiple_dc.csv'
INVALID_FILEPATHS = CSV/'invalid_filepaths.csv'
DUPLICATE_DIGITAL_OBJECTS = CSV/'duplicate_digital_objects.csv'
DUPLICATE_FILE_PATHS = CSV/'duplicate_file_paths.csv'
FP_DO_MATCH = CSV/'fp_do_match.csv'
SIMPLE_ASPACE_XML = XML/'simple_aspace'
SIMPLE_MANUAL_XML = XML/'simple_manual'
MANUAL_DC_XML = XML/'manual_dc'
ASPACE_DC_XML = XML/'aspace_dc'
MULTIPLE_DC_XML = XML/'multiple_dc'
DATE_PATTERN = re.compile(
    "[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}"
)
INPUT_RANGE = range(4)

DigitalObjectStructure: TypeAlias = tuple[str, ...]
CollectionStructure: TypeAlias = dict[str, DigitalObjectStructure]
ContainerStructure: TypeAlias = dict[str, CollectionStructure]


class TestContainerBuild(unittest.TestCase):
    """Verify the tree structure and opex contents for covered use-cases."""

    def check_structure(self, expected_structure: Path, expected_xml: Path):
        """Helper function that does most of the work for each test case."""

        all_ran = False
        # List of contents in the output folder
        self.output_contents = list(OUTPUT.iterdir())
        # List of contents in the output folder that are named like a container
        self.container_glob_list = list(
            OUTPUT.glob(self.container_glob_pattern)
        )

        # Test whether the output directory has the right contents
        with self.subTest(output_contents=self.output_contents,
                          container_glob_list=self.container_glob_list):
            logger.debug("Sub-testing container exists.")
            self.assertTrue(len(self.container_glob_list) == 1)
            self.assertTrue(len(self.output_contents) == 1)
            one_match_in_output = len(self.container_glob_list) == 1
            one_item_in_output = len(self.output_contents) == 1
            # Only continue if there is one and only one
            # matching container in the folder
            if not (one_match_in_output and one_item_in_output):
                self.assertTrue(all_ran)
                return

        # Read the list of expected folder/file paths one line at a time
            for structure_line in expected_structure.read_text().split("\n"):

                self.container_name = self.container_glob_list[0].name
                # Convert string to path object and insert container name
                structure_line = Path(
                    structure_line.replace("*", str(self.container_name))
                )
                logger.debug(f"Expected structure line: {structure_line}")
                # (sub)test for each line
                with self.subTest(line=structure_line):
                    logger.debug("Sub-testing expected structure.")
                    self.assertTrue(structure_line.exists())
                    # Test whether line exists and continue
                    # if it is an opex file
                    if (not structure_line.exists()
                            or not structure_line.match("*.opex")):
                        logger.debug(
                            f"Aborting line test. "
                            f"Line exists: {structure_line.exists()}, "
                            f"Line is opex: {structure_line.match('*.opex')}")
                        continue

                    # Special condition for containers
                    # since their name is always unique
                    if "Container" in str(structure_line.name):
                        expected_opex = expected_xml/"Container.opex"
                    else:
                        expected_opex = expected_xml/structure_line.name
                    logger.debug(f"Expected opex: {expected_opex}")
                    # Read both the generated file and the verification file
                    expected_opex_text = expected_opex.read_text()
                    test_opex_text = structure_line.read_text()
                    # Subtest for each opex file
                    # so each test and verification file can be seen in
                    # the testing output
                with self.subTest(expected_opex=expected_opex,
                                  test_opex=structure_line):
                    logger.debug(f"Sub-testing opex: {structure_line}")
                    # Regular expression match all dates in both files
                    dates_expected = re.findall(DATE_PATTERN,
                                                expected_opex_text)
                    dates_test = re.findall(DATE_PATTERN, test_opex_text)
                    # Regular expression match each unique date pattern
                    # and replace with filler text
                    for date in dates_expected:
                        expected_opex_text = re.sub(
                            date,
                            "VALUE_REPLACED_BY_TEST",
                            expected_opex_text
                        )
                    for date in dates_test:
                        test_opex_text = re.sub(
                            date,
                            "VALUE_REPLACED_BY_TEST",
                            test_opex_text)
                    # Convert file text into lists for comparison
                    expected_lines = [
                        line.strip() for line
                        in expected_opex_text.split("\n")
                    ]
                    test_lines = [
                        line.strip() for line
                        in test_opex_text.split('\n')
                    ]
                    expected = f"{len(expected_lines)}"
                    got = f"{len(test_lines)}"
                    diff = set(expected_lines).symmetric_difference(
                                    set(test_lines)
                                )
                with self.subTest(expected=expected,
                                  got=got,
                                  diff=diff):
                    logger.debug("Sub-testing opex contents.")
                    # Test whether the files are the same length
                    # and only continue if True
                    self.assertTrue(
                        len(expected_lines) == len(test_lines)
                    )
                    if not len(expected_lines) == len(test_lines):
                        logger.debug(
                            "Expected lines differs: "
                            + str(set(expected_lines).symmetric_difference(
                                set(test_lines)
                            ))
                        )
                    else:
                        # Loop through all the test lines
                        # and verify them individually
                        for i in range(len(test_lines)):
                            # Subtest so that the lines are visible
                            # in the testing output
                            with self.subTest(
                                expected_line=expected_lines[i],
                                test_line=test_lines[i]
                            ):
                                self.assertTrue(
                                    expected_lines[i] == test_lines[i]
                                )
                    logger.debug("Finished tests for structure line: "
                                 f"{structure_line}")

    def setUp(self):
        # remove output
        if OUTPUT.exists():
            shutil.rmtree(OUTPUT)
        # remake output
        OUTPUT.mkdir()
        # ensure input folder exists
        if not INPUT.exists():
            INPUT.mkdir()
        # ensure that test files exist
        for i in INPUT_RANGE:
            (INPUT / f"file{i}.txt").touch()

        # set expected container name just before constructing container
        self.container_glob_pattern = datetime.now().strftime(
            "Container_%Y-%m-%d_%H_%M_%S"
        )

    def tearDown(self):

        # Make sure nothing remains of previous tests
        for item in self.__dict__:
            del item
        if OUTPUT.exists():
            shutil.rmtree(OUTPUT)
        OUTPUT.mkdir()
        for i in INPUT_RANGE:
            (INPUT / f"file{i}.txt").touch()

    def basic_test(self,
                   csv_path: Path,
                   expected_structure: Path,
                   expected_xml: Path):
        logger.debug("Beginning test. "
                     f"csv_path: {csv_path}, "
                     f"expected_structure: {expected_structure}, "
                     f"expected_xml: {expected_xml}")
        bulk_upload.Container(
            csv_path=str(csv_path),
            output_folder=str(OUTPUT)).build()
        self.check_structure(expected_structure, expected_xml)

    def test_simple_aspace(self):
        """Test aspace columns only"""

        self.basic_test(SIMPLE_ASPACE, ASPACE_EXPECTED, SIMPLE_ASPACE_XML)

    def test_simple_manual(self):
        """Test manual columns only"""

        self.basic_test(SIMPLE_MANUAL, MANUAL_EXPECTED, SIMPLE_MANUAL_XML)

    def test_manual_dc(self):
        """Test manual columns and all dc columns"""

        self.basic_test(MANUAL_DC, MANUAL_EXPECTED, MANUAL_DC_XML)

    def test_aspace_dc(self):
        """Test aspace columns and all dc columns"""

        self.basic_test(ASPACE_DC, ASPACE_EXPECTED, ASPACE_DC_XML)

    def test_invalid_filepaths(self):

        logger.debug(F"Beginning test. csv_path: {INVALID_FILEPATHS}")

        with self.assertRaises(ValueError):
            bulk_upload.Container(
                csv_path=str(INVALID_FILEPATHS),
                output_folder=str(OUTPUT)
            ).build()

    def test_duplicate_digital_objects(self):

        logger.debug(F"Beginning test. csv_path: {DUPLICATE_DIGITAL_OBJECTS}")

        with self.assertRaisesRegex(
            ValueError, "Duplicate digital objects found:.*"
        ):
            bulk_upload.Container(
                csv_path=str(DUPLICATE_DIGITAL_OBJECTS),
                output_folder=str(OUTPUT)
            ).build()

    def test_duplicate_file_paths(self):
        logger.debug(f"Beginning test. csv_path {DUPLICATE_FILE_PATHS}")

        with self.assertRaisesRegex(
            ValueError, "Duplicate filepaths detected in csv:*"
        ):
            bulk_upload.Container(
                csv_path=str(DUPLICATE_FILE_PATHS),
                output_folder=str(OUTPUT)
            ).build()

    def test_fp_do_names_match(self):

        logger.debug(F"Beginning test. csv_path: {FP_DO_MATCH}")

        with self.assertRaisesRegex(
            ValueError,
            "Files and digital objects with matching names detected:.*"
        ):
            bulk_upload.Container(
                csv_path=str(FP_DO_MATCH),
                output_folder=str(OUTPUT)
            ).build()

    def test_multiple_dc(self):

        self.basic_test(MULTIPLE_DC, MANUAL_EXPECTED, MULTIPLE_DC_XML)

    def test_undo_moves(self):

        logger.debug(f"Beginning test. moves.csv path: {MOVES}")

        bulk_upload.undo_file_moves(str(MOVES))

    def test_invalid_undo_moves_columns(self):

        logger.debug(
            f"Beginning test. moves.csv path: {MOVES_INVALID_COLUMNS}"
        )
        with self.assertRaisesRegex(ValueError, "Invalid column names. *"):
            bulk_upload.undo_file_moves(str(MOVES_INVALID_COLUMNS))

    def test_undo_moves_overwrite_existing_files(self):

        logger.debug(f"Beginning test. moves.csv path: {MOVES_OVERWRITE}")
        with self.assertRaisesRegex(
            ValueError,
            "Destination path points to a file that already exists: *"
        ):
            bulk_upload.undo_file_moves(
                moves_csv_path=str(MOVES_OVERWRITE))

    def test_undo_moves_nonexistent_files(self):
        logger.debug(f"Beginning test. moves.csv path: {MOVES}")
        with self.assertRaises(FileNotFoundError):
            bulk_upload.undo_file_moves(
                moves_csv_path=str(MOVES_NONEXISTENT))

    def test_supply_undo_file_moves_as_list(self):
        ...


if __name__ == "__main__":
    unittest.main()
