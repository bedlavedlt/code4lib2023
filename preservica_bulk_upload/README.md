# preservicatools :sun_behind_large_cloud:

## Getting Started
### pip install
1. Ensure that you have python 3.10.7 or later installed, as well as git
2. Clone the repo:
```
git clone https://github.com/ualr-cahc/preservicatools
```
3. Install editable with pip:
```
pip install -e preservicatools
```

4. Launch the app, substituting the appropriate name for python on your system:
    * GUI version:
    ```
    python -m preservicatools.bulk_upload_app
    ```
    * Command line:
    ```
    python -m preservicatools.bulk_upload -i path/to/csv -o path/to/folder
    ```
    * Python:
    ```python
    from preservicatools.bulk_upload import Container, undo_file_moves

    container = Container(csv_path='path/to/csv', root_output_path='path/to/output')
    container.build()
    # if you want to move your content files back to their original location
    container.undo_file_moves()
    # or, if you already built the container and disposed of the original
    # Container object, locate the moves.csv file in the bulk upload
    # container's main folder and use the undo_file_moves function.
    undo_file_moves('path/to/container/moves.csv')
    ```

Build bulk_upload_app.exe (Windows). Make sure you use whatever python alias your machine relies on:
```
git clone https://github.com/ualr-cahc/preservicatools
cd preservicatools
python -m venv env
env\scripts\activate
pip install pyinstaller
pip install -r requirements.txt
pyinstaller -wF preservicatools\bulk_upload_app.py
move dist\bulk_upload_app.exe ..\bulk_upload_app.exe
cd ..
rmdir /s /q preservicatools
bulk_upload_app.exe
```
