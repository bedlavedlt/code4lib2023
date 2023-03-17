#! python3.11

import logging
import unittest
from pathlib import Path
import shutil

from tileTools.setup_logging import root_logger
from tileTools import makeTiles

TESTS = Path("./tests").resolve()
OUTPUT = TESTS / "output"
TIFFS = TESTS / "TIFFs"
EXPECTED_OUTPUT = TESTS / "expected_output.txt"
# TIFFS = Path("./logs/TIFFs")


root_logger = root_logger("./logs/test_tiling.log")
logger = logging.getLogger(__name__)


class test_makeTiles(unittest.TestCase):

    def setUp(self) -> None:

        if not OUTPUT.exists():
            OUTPUT.mkdir()

    def tearDown(self) -> None:
        shutil.rmtree(OUTPUT)
        ...

    def test_makeTiles(self):
        makeTiles.make_tiles(
            input_folder=str(TIFFS),
            output_folder=str(OUTPUT),
            database_name=str(TESTS/'tiling.db'),
            log=False
        )
        with open(EXPECTED_OUTPUT) as expected_output:
            for output in map(lambda x: x.strip(),
                              expected_output.readlines()):
                with self.subTest(output=output):
                    self.assertTrue(Path(output).exists())
