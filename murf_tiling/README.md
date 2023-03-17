# GeoTIFF to XYZ raster tiles

python >= 3.10.7

## Setup
```
git clone https://github.com/ualr-cahc/murf-tiling
cd murf-tiling
python -m venv env
env\Scripts\activate
pip install -r requirements.txt
```
You will have to either use conda forge to install GDAL or download an unofficial wheel binary and install it manually.
```
conda install -c conda-forge gdal
```
or
```
pip install [INSERT PATH TO GDAL WHEEL]
```
___
## Run the tool

* Basic implementation
```python
from tileTools.makeTiles import make_tiles

# input_dir is the directory containing the GeoTIFFs to be tiled
# output_dir is the directory where the tool will output folders and files
make_tiles(input_dir="tests/TIFFs",
           output_dir="tests/output")
```

* Output stats to sqlite3 database file (optional):
```python
make_tiles(input_dir="tests/TIFFs",
           output_dir="tests/output",
           database_name='test_tiling.db')
```
___
## All available arguments


```python
make_tiles(input_folder: str,
           output_folder: str,
           min_zoom: int = 8,
           max_zoom: int | None = None,
           xyz: bool = True,
           processes: int | None = None,
           database_name: Optional[str] = None
           )
```

___
**input_folder** *(str)*: 

Location of source GeoTIFFs.
___
**output_folder** *(str)*: 

Location to drop sub-folders "translated" and "tiles" containing byte translated versions of the GeoTIFFs and the resulting tile sets, respectively.
___
**min_zoom** *(int)*: 

Minimum zoom level for rendered tile set. Default is 8.
___
**max_zoom** *(int | None, optional)*: 

Maximum zoom level for rendered tile set. If not supplied, max_zoom is calculated via_find_max_zoom()
___
**xyz** *(bool, optional)*: 

True for XYZ tiles, False for TMS. Defaults to True.
___
**processes** *(int | None, optional)*: 

The number of multithreading processes to use. Defaults to os.cpu_count() (aka the max available).
___
**database_name** *(str | None, optional)*: 

Provide a name and the tool will write an sqlite3 database file with stats about the tiling process.
