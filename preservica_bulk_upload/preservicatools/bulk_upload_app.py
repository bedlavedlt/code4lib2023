"""Bulk upload user interface"""

import logging
from pathlib import Path
from tkinter import BOTTOM, END, RIGHT, TOP, Tk
from tkinter.filedialog import askdirectory, askopenfilename
from tkinter.messagebox import showerror  # type: ignore
from tkinter.ttk import Button, Entry, Frame, Separator

from preservicatools.bulk_upload import Container, undo_file_moves

logger = logging.getLogger(__name__)


# Per convention, this class builds upon the Tk class to
# generate a custom user interface
class Application(Tk):
    def __init__(self):
        # Call the init function for the Tk class.
        super().__init__()

        self.title("Make Bulk Upload Tree")
        self.geometry('500x400')
        self.minsize(500, 400)

        # Framing
        # Top Frame________________________
        # | TopTop Frame___________________|
        # | |-csv_text------csv_button     |
        # |--------------------------------|
        # | TopMiddle Frame________________|
        # | |-output_text---output_button  |
        # |--------------------------------|
        # | TopBottom Frame________________|
        # | |---------------submit_button  |
        # |________________________________|
        # Bottom Frame_____________________|
        # | BottomTop Frame________________|
        # | undo_text-------undo_select    |
        # |--------------------------------|
        # | BottomBottom Frame_____________|
        # | |---------------undo_submit    |
        # |________________________________|

        # FRAMES #
        # See the ttk documentation for more info
        # on widgets and the .pack() method.

        # .pack() places the widget in the UI

        # Top Frame
        self.top_frame = Frame(self, padding=10)
        self.top_frame.pack(side=TOP, fill='both', expand=True)
        # Top Top Frame
        self.top_top_frame = Frame(self.top_frame, padding=10)
        self.top_top_frame.pack(side=TOP, fill='x', expand=True)
        # Top Middle Frame
        self.top_middle_frame = Frame(self.top_frame, padding=10)
        self.top_middle_frame.pack(fill='x', expand=True)
        # Top Bottom Frame
        self.top_bottom_frame = Frame(self.top_frame, padding=10)
        self.top_bottom_frame.pack(side=BOTTOM, fill='x', expand=True)
        # Separator
        self.separator = Separator(self, orient="horizontal")
        self.separator.pack(fill='x')
        # Bottom Frame
        self.bottom_frame = Frame(self, padding=10)
        self.bottom_frame.pack(side=BOTTOM, fill='x', expand=True)
        # Bottom Top Frame
        self.bottom_top_frame = Frame(self.bottom_frame, padding=10)
        self.bottom_top_frame.pack(side=TOP, fill='x', expand=True)
        # Bottom Bottom Frame
        self.bottom_bottom_frame = Frame(self.bottom_frame, padding=10)
        self.bottom_bottom_frame.pack(side=BOTTOM, fill='x', expand=True)

        # MAKE CONTAINER #
        # CSV Text
        self.csv_entry = Entry(self.top_top_frame)
        self.csv_entry.pack(fill='x', expand=True)
        # CSV Button
        self.select_csv_button = Button(self.top_top_frame,
                                        text='Select CSV File',
                                        command=self.select_csv)
        self.select_csv_button.pack(side=RIGHT)
        # Output Text
        self.output_entry = Entry(self.top_middle_frame)
        self.output_entry.pack(fill='x', expand=True)
        # Output Button
        self.select_output_button = Button(self.top_middle_frame,
                                           text='Select Output Folder',
                                           command=self.select_output)
        self.select_output_button.pack(side=RIGHT)
        # Submit Button
        self.submit_button = Button(self.top_bottom_frame,
                                    text='Submit',
                                    command=self.submit)
        self.submit_button.pack(side=RIGHT)

        # UNDO MOVES #
        # Undo Text
        self.undo_entry = Entry(self.bottom_top_frame)
        self.undo_entry.pack(fill='x', expand=True)
        # Undo Select
        self.undo_select_button = Button(self.bottom_top_frame,
                                         text='Select Moves File',
                                         command=self.undo_select)
        self.undo_select_button.pack(side=RIGHT)
        # Undo Submit
        self.undo_submit_button = Button(self.bottom_bottom_frame,
                                         text='Undo Moves',
                                         command=self.undo_submit)
        self.undo_submit_button.pack(side=RIGHT)

    # BUTTON FUNCTIONS #
    # CSV Button func
    def select_csv(self):
        # the askopenfilename widget opens an explorer window
        # and requests that the user select a file
        # with the type defined in 'filetypes'
        self.csv_path = Path(askopenfilename(title='Open CSV File',
                                             filetypes=[('csv', '.csv')],
                                             initialdir=self.set_directory())
                             ).resolve()
        # only add the path to the entry box if it is a legitimate file path
        if self.csv_path and self.csv_path.exists():
            # Remove the previous contents of the entry box
            # (from the first index position '0' to the last 'END')
            self.csv_entry.delete(0, END)
            # Add the new contents (starting from the first index position '0')
            self.csv_entry.insert(0, str(self.csv_path))
            # add the parent directory of the csv file
            # as the starting directory for the next file dialog
            self.directory = self.csv_path.parent

    # Output Button func
    def select_output(self):
        output_path = Path(askdirectory(title='Select Output Folder',
                                        initialdir=self.set_directory())
                           ).resolve()
        # Only add the output path to the entry box
        # if it is a legitimate directory path
        if output_path and output_path.exists():
            self.output_entry.delete(0, END)
            self.output_entry.insert(0, str(output_path))
            # add the parent directory of the output folder
            # as the starting directory for the next file dialog
            self.directory = output_path.parent

    # Submit Button func
    def submit(self):
        # get paths from tk.Entry widgets
        # the get() method removes the text from
        # the entry box when it is called,
        # so the text is stored as a variable for reuse.
        csv_entry_content = self.csv_entry.get().strip()
        output_entry_content = self.output_entry.get().strip()
        csv_path = Path(csv_entry_content) if csv_entry_content else None
        output_path = Path(
            output_entry_content) if output_entry_content else None

        # validate paths before running
        if csv_path and csv_path.exists():
            csv_path_good = True
        else:
            csv_path_good = False
            showerror("Uh Oh!", f"CSV path does not exist:\n{csv_path}")

        if output_path and output_path.exists():
            output_path_good = True
        else:
            output_path_good = False
            showerror("Uh Oh!", f"Output path does not exist:\n{output_path}")

        # if both paths validate, then try to make the tree
        # otherwise do nothing
        if csv_path_good and output_path_good:
            try:

                container = Container(csv_path=str(csv_path),
                                      output_folder=str(output_path))
                container.build()

                # if the tool runs successfully, then add the path
                # to the moves file to the undo moves entry box.
                if container.file_moves_path:
                    self.undo_entry.delete(0, END)
                    self.undo_entry.insert(0, str(container.file_moves_path))
            # Show any errors from bulk_upload.py in a message box
            except Exception as err:
                showerror("Error", str(err))

    # Undo Button func
    def undo_select(self):
        initialdir = self.set_directory()
        moves_file = Path(askopenfilename(
            title='Select moves.csv to Undo', initialdir=initialdir))
        if moves_file and moves_file.exists():
            self.directory = moves_file.parent
            self.undo_entry.delete(0, END)
            self.undo_entry.insert(0, str(moves_file))
        else:
            showerror("Uh Oh!", f"File does not exist:\n{moves_file}")

    # Undo Submit func
    def undo_submit(self):
        # get the path to the moves file
        moves_entry_content = self.undo_entry.get().strip()
        moves_file = Path(moves_entry_content) if moves_entry_content else None
        # ensure the path is valid before attempting to run undo_moves
        # if not, then pop up error
        if not (moves_file and moves_file.exists()):
            showerror("Uh Oh!", f"File does not exist:\n{moves_file}")
        elif not (moves_file and moves_file.is_file()):
            showerror("Uh Oh!", f"Invalid filepath:\n{moves_file}")
        else:
            try:
                undo_file_moves(str(moves_file))
            # general error handling
            except Exception as err:
                showerror("Error!", str(err))

    # Return initial directory for filedialogues
    def set_directory(self) -> Path:
        """Return self.directory if it exists,
        otherwise return the current working directory.
        This function is called to set the initial directory
        for each filedialogue and folderdialogue widget.
        """

        return (Path.home()
                if 'directory' not in self.__dict__
                else self.directory)


def run():
    """Launch the application"""
    app = Application()
    app.mainloop()


if __name__ == "__main__":
    run()
