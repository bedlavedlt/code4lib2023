# pyright: reportMissingTypeStubs=false, reportUnknownVariableType=false
# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false
"""Create XYZ tile layers for a list of GeoTIFFs.
"""

import logging
import os
import traceback
from math import ceil, cos, log2, radians
from pathlib import Path
import shutil
from time import perf_counter_ns
from typing import Optional

import rasterio
from osgeo.gdal import GDT_Byte, Translate
from osgeo_utils import gdal2tiles

from tileTools.database import Database, NewColumn
from tileTools.setup_logging import root_logger


logger = logging.getLogger(__name__)


def add_tile_data_to_database(tiles_directory: str, database_path: str):
    """Walk the directory containing your tile sets and log data about them to
    an sqlite database.

    Args:
        tiles_directory (str): The path to the directory containing the output
        from make_tiles.
        database_path (str): The path to the resulting database file. Creates
        one if it doesn't already exist. Adds a batch otherwise.
    """
    database = _initialize_tile_count_size_database(database_path)

    with database.connection as connection:
        cursor = connection.execute("select layer_name from make_tile_layer;")
        layer_names = [result[0] for result in cursor.fetchall()]

    for layer in Path(tiles_directory).iterdir():
        if layer.name in layer_names:
            with database.connection as connection:
                cursor = connection.execute(
                    "select * from make_tile_layer where "
                    "layer_name=?;", (layer.name,)
                )
                columns = [item[0] for item in cursor.description]

                layer_data = dict(list(zip(columns, cursor.fetchall()[0])))

                if layer_data['tile_size_bytes'] is None and \
                        layer_data['tile_count'] is None:
                    tile_count, tile_size = _get_tile_count_and_size(layer)
                    logger.debug("Adding size and count to database for layer "
                                 f"{layer.name}: "
                                 f"size: {tile_size}; count: {tile_count}")
                    database.update('make_tile_layer',
                                    {'layer_name': layer.name},
                                    {'tile_size_bytes': tile_size,
                                     'tile_count': tile_count})

                elif layer_data['tile_size_bytes'] is None:
                    tile_size = _get_tile_size(layer)
                    logger.debug("Adding tile size to database for layer "
                                 f"{layer.name}: {tile_size}")
                    database.update('make_tile_layer',
                                    {'layer_name': layer.name},
                                    {'tile_size_bytes': tile_size})

                elif layer_data['tile_count'] is None:
                    tile_count = _get_tile_count(layer)
                    logger.debug("Adding tile count to database for layer "
                                 f"{layer.name}: {tile_count}")
                    database.update('make_tile_layer',
                                    {'layer_name': layer.name},
                                    {'tile_count': tile_count})

                else:
                    logger.debug("Tile size and count already exist for "
                                 f"{layer.name}.")


def _find_max_zoom(file_path: str):
    """Determine the maximum tile zoom level for a single GeoTIFF.
    The result is calculated by finding the floating point 'zoom-level'
    of the original GeoTIFF and rounding up to the next integer zoom value.
    This function uses the equation for determining raster tile width given
    the zoom level, rearranged to input width and output 'zoom level'.

    Args:
        translated_file_path (str): Path to a GeoTIFF that has been converted
        to bytes using osgeo.gdal.Translate()

    Returns:
        int: Maximum zoom level.
    """

    logger.debug("Beginning find_max_zoom.")
    with rasterio.open(file_path) as raster:
        if isinstance(raster.transform, rasterio.Affine):

            original_pixel_width = abs(raster.transform[0])
            earth_diameter = 40075016.686
            latitude = raster.lnglat()[1]
            max_zoom = ceil(
                log2(earth_diameter
                     * cos(radians(latitude))
                     / original_pixel_width
                     )
                - 8
                )

            logger.info(f"original pixel width (m): {original_pixel_width}, "
                        f"earth diameter (m): {earth_diameter}, "
                        f"latitude: {latitude}"
                        f"max zoom: {max_zoom}")
        else:
            logger.error(f"Non-Affine transform type used: "
                         f"{type(raster.transform)}. ")
            raise ValueError("Non-Affine transform type used. A value for "
                             "max_zoom must be supplied.")
    return max_zoom


def _get_batch_number(database: Database):

    cursor = database.connection.execute(
        "select max(batch) from make_tile_layer;", tuple()
    )
    batch = cursor.fetchall()[0][0]
    cursor.close()
    if batch is None:
        batch = 0
    else:
        batch += 1

    return batch


def _get_tile_count(layer_directory: Path):

    tile_count = 0
    for _, _, files in os.walk(layer_directory):
        for _ in files:
            tile_count += 1

    return tile_count


def _get_tile_count_and_size(layer_directory: Path):

    size = 0
    tile_count = 0
    for root, dirs, files in os.walk(layer_directory):
        for file in files:
            size += os.stat(os.path.join(root, file)).st_size
            tile_count += 1
        for directory in dirs:
            size += os.stat(os.path.join(root, directory)).st_size

    return tile_count, size


def _get_tile_size(layer_directory: Path):
    tile_size = 0
    for root, dirs, files in os.walk(layer_directory):
        for file in files:
            tile_size += os.stat(os.path.join(root, file)).st_size
        for dir in dirs:
            tile_size += os.stat(os.path.join(root, dir)).st_size

    return tile_size


def _initialize_tile_count_size_database(database_path: str):

    logger.debug(f"Initializing database {database_path}")
    shutil.copy(database_path, database_path + ".backup")
    database = _initialize_tiling_database(database_path)

    new_columns = [
        NewColumn('tile_size_bytes', 'integer'),
        NewColumn('tile_count', 'integer')
    ]

    database.add_columns('make_tile_layer', new_columns)

    return database


def _initialize_tiling_database(database_path: str):

    logger.debug(f"Initializing database {database_path}")
    database = Database(database_path)

    make_tile_layer_columns = [
        NewColumn('batch', 'integer', 'NOT NULL'),
        NewColumn('layer_name', 'text', 'NOT NULL'),
        NewColumn('min_zoom', 'integer', 'NOT NULL'),
        NewColumn('max_zoom', 'integer', 'NOT NULL'),
        NewColumn('tile_time_ns', 'integer', 'NOT NULL'),
        NewColumn('processes', 'integer', 'NOT NULL'),
        NewColumn('xyz_tiles', 'integer', 'DEFAULT 0'),
        NewColumn('translated_file_size', 'integer', 'NOT NULL'),
        NewColumn('original_file_size', 'integer', 'NOT NULL'),
        NewColumn('datetime', 'text', 'DEFAULT CURRENT_TIMESTAMP'),
        NewColumn('rgbExpand', 'integer', 'DEFAULT 0 NOT NULL')
    ]

    database.add_table('make_tile_layer',
                       make_tile_layer_columns,
                       primary_key=('batch', 'layer_name'))

    return database


def _is_color_mapped(raster_location: str) -> bool:  # type: ignore
    """Determine if the raster is color mapped"""

    raster = rasterio.open(raster_location)
    for band in range(raster.count):  # type: ignore
        try:
            band += 1
            if isinstance(raster.colormap(band), dict):  # type: ignore
                return True

        except ValueError as err:
            if str(err) == "NULL color table":
                return False
            else:
                raise err


def _make_tile_layer(translated_file_path: str,
                     layer_output_folder: str,
                     batch: Optional[int],
                     min_zoom: int = 8,
                     max_zoom: Optional[int] = None,
                     processes: Optional[int] = None,
                     xyz: bool = True) -> dict[str, int | str | None]:
    """Create a raster tile layer from a single GeoTIFF file using
    gdal2tile.

    Args:
        translated_file_path (str): Path to a GeoTIFF that has been converted
        to bytes using osgeo.gdal.Translate
        layer_output_folder (str): location for gdal2tiles to drop files
        min_zoom (int): Minimum zoom level. Defaults to 8.
        max_zoom (int | None, optional): If not supplied, default zoom is
        determined by _find_max_zoom function. Defaults to None.
        processes (_type_, optional): The number of multithreading processes
        to use. Defaults to os.cpu_count() (aka max for machine).
        xyz (bool, optional): True for XYZ tiles, False for TMS.
        Defaults to True.
    """

    if processes is None:
        processes = os.cpu_count()

    logger.debug("Beginning _make_tile_layer for "
                 f"{Path(translated_file_path).name}")
    # Determine optimum max zoom level if max_zoom is not provided
    if max_zoom is None:
        logger.debug("Determining max zoom via _find_max_zoom()")
        max_zoom = _find_max_zoom(translated_file_path)

    # These are the arguments to be used with osgeo_utils.gdal2tiles
    # The argument '-e' aka 'resume mode' picks up where it left off,
    # if tiling progress has already been made.
    gdal2tile_args = ['gdal2tiles.py',
                      '-z',
                      f"{min_zoom}-{max_zoom}",
                      '-e',
                      f'--processes={processes}']
    # add OSM slippy map standard ('--xyz')
    if xyz:
        gdal2tile_args.append("--xyz")
    # add input and output paths last
    gdal2tile_args += [str(translated_file_path), str(layer_output_folder)]

    logger.debug(f"Begin tiling. Args: {gdal2tile_args}")
    begin = perf_counter_ns()
    gdal2tiles.main(gdal2tile_args)
    # if it takes longer than one minute to render a set,
    # don't move on to the next zoom level for this layer
    end = perf_counter_ns()
    duration = end-begin

    logger.info(f"Zoom {min_zoom}-{max_zoom} tile time: "
                f"{duration/1000000000} seconds")

    database_data = {
                'layer_name': Path(translated_file_path).stem,
                'min_zoom': min_zoom,
                'max_zoom': max_zoom,
                'batch': batch,
                'tile_time_ns': duration,
                'processes': processes,
                'xyz_tiles': 1 if xyz is True else 0,
                'translated_file_size': os.stat(translated_file_path).st_size
            }

    return database_data


def make_tiles(input_folder: str,
               output_folder: str,
               min_zoom: int = 8,
               max_zoom: int | None = None,
               xyz: bool = True,
               processes: int | None = None,
               database_name: Optional[str] = None,
               log: bool = True
               ):
    """Make raster tiles for all GeoTIFFs in a directory.

    Args:
        input_folder (str): location of source GeoTIFFs.
        output_folder (str): location to drop subfolders "translated" and
        "tiles" containing byte translated versions of the GeoTIFFs and the
        resulting tile sets, respectively.
        min_zoom (int): Minimum zoom level for rendered tile set. Default is 8.
        max_zoom (int | None, optional): Maximum zoom level for rendered tile
        set. If not supplied, max_zoom is calculated via _find_max_zoom()
        xyz (bool, optional): True for XYZ tiles, False for TMS.
        Defaults to True.
        processes (int | None, optional): The number of multithreading
        processes to use. Defaults to os.cpu_count() (aka max for machine).
        database_name (str | None, optional): Provide a name and the tool will
        write an sqlite3 database file with stats about the tiling process.
    Raises:
        KeyboardInterrupt: If KeyboardInterrupt is raised while tiling a layer,
        the incomplete layer is discarded before the program stops. Same goes
        for unexpected errors during tiling.
    """

    if log is True:
        root_logger(str(Path(output_folder)/"tiling.log"))

    logger.debug("Beginning make_tiles. "
                 f"args: {locals()}")

    input_filepaths = list(map(str, Path(input_folder).iterdir()))

    make_tiles_from_list(input_filepaths=input_filepaths,
                         output_folder=output_folder,
                         min_zoom=min_zoom,
                         max_zoom=max_zoom,
                         xyz=xyz,
                         processes=processes,
                         database_name=database_name)


def make_tiles_from_list(input_filepaths: list[str],
                         output_folder: str,
                         min_zoom: int = 8,
                         max_zoom: int | None = None,
                         xyz: bool = True,
                         processes: int | None = None,
                         database_name: Optional[str] = None
                         ):

    max_zoom_internal = None

    args = {k: v for k, v in locals().items() if k != "input_filepaths"}

    logger.debug(f"Beginning make_tiles_from_list. args: {args}")
    if database_name is not None:
        database = _initialize_tiling_database(database_name)
        batch = _get_batch_number(database)
    else:
        database = None
        batch = None

    # Convert the output directory to a Path object
    output_folder_path = Path(output_folder)
    # Create output directory for translated files
    # and for tile layers.
    translate_output_folder = output_folder_path / "translated"
    tile_output_folder = output_folder_path / "tiles"
    # Make sure the folders exist.
    _validate_output_folders(tile_output_folder, translate_output_folder)

    logger.debug("Looping through input_filepaths.")
    for input_filepath in map(Path, input_filepaths):
        logger.debug(f"Processing input filepath {input_filepath}")
        if input_filepath.suffix != ".tif":
            logger.debug(f"Skipping non-tif file: {input_filepath}.")
            continue
        if max_zoom is None:
            try:
                max_zoom_internal = _find_max_zoom(str(input_filepath))
            except Exception as err:
                logger.error(err)
                continue

        filename = input_filepath.name
        layer_name = input_filepath.stem
        translated_file_path = translate_output_folder / filename
        layer_output_folder = tile_output_folder / layer_name

        if layer_output_folder.exists():
            logger.debug(f"Layer already rendered, skipping: "
                         f"{layer_name}")
            continue

        logger.debug(f"input_filepath: {input_filepath}, "
                     f"filename: {filename}, "
                     f"layer_name: {layer_name}, "
                     f"translated_file_path: {translated_file_path}, "
                     f"layer_output_folder: {layer_output_folder}")
        # only try to translate a file if the
        # translated file doesn't already exist
        if translated_file_path in translate_output_folder.iterdir():
            logging.debug("Removing pre-existing translated file: "
                          f"{translated_file_path}")
            os.remove(translated_file_path)
            # Try to translate, and log errors without exiting.
            # Some layers won't translate due to problems with the file.
        try:
            color_mapped = False
            color_mapped = _is_color_mapped(str(input_filepath))
        except Exception as err:
            logger.error(err)
            logger.debug(f"Skipping file: {input_filepath}")
            continue

        if color_mapped:
            rgbExpand = "rgb"
        else:
            rgbExpand = None

        try:
            logger.debug(f"Translating {translated_file_path} to bytes.")

            Translate(str(translated_file_path),
                      str(input_filepath),
                      outputType=GDT_Byte,
                      rgbExpand=rgbExpand)

        except Exception:
            # If an error occurs in translation, log it,
            # stop trying to process this input file,
            # and move on to the next
            error = traceback.format_exc()
            logger.error(error)
            logger.debug(f"Skipping file: {input_filepath}")
            break

        # ensure layer output directory exists
        if not layer_output_folder.is_dir():
            os.makedirs(layer_output_folder)

        # Try to make the current tile layer,
        # but remove it if an error is raised before it completes.
        try:
            logger.info(f"Making tile layer for {layer_name}")
            print(f"Tiling: {layer_name}")
            database_data = _make_tile_layer(
                str(translated_file_path),
                str(layer_output_folder),
                batch,
                min_zoom,
                max_zoom_internal,
                xyz=xyz,
                processes=processes
            )

            if database is not None:
                database_data.update({
                    'original_file_size': input_filepath.stat().st_size,
                    'rgbExpand': True if rgbExpand is not None else False
                })
                database.insert(
                    table_name='make_tile_layer',
                    items_to_insert=database_data
                )

        # If the user raises a KeyboardInterrupt log it,
        # remove the incomplete layer, and exit.
        except KeyboardInterrupt:
            shutil.rmtree(layer_output_folder)
            raise KeyboardInterrupt
        # If an unexpected error occurs, log it, remove the incomplete layer,

        except Exception:
            error = traceback.format_exc().replace("\n", ";")
            logger.error(error)
            logger.debug(f"Skipping file: {input_filepath}")
            shutil.rmtree(layer_output_folder)


def _validate_output_folders(*paths: Path):
    """For each path, create it if it doesn't already exist.

    Raises:
        ValueError: If the path already exists as a file, ValueError is raised.
    """

    for path in paths:
        if not path.exists():
            os.makedirs(path)
        elif path.is_file():
            raise ValueError("Trying to write output to directory "
                             f"that is actually a file {path}")
