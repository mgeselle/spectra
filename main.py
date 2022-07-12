from astropy.io import fits
import os
from pathlib import Path
import tkinter as tk
from tkinter import ttk
from tkinter import filedialog as fd
from combine import Combine
from config import CamCfgGUI
from crop import Crop
from fitsfile import FitsImageFile
from image_display import ImageDisplay
from reduce import Reduce
from specview import Specview
import spectra


class Main(ttk.Frame):
    def __init__(self, root: tk.Tk):
        super().__init__(root)
        root.resizable(True, True)
        width = int(0.5 * root.winfo_screenwidth())
        height = int(0.5 * root.winfo_screenheight())
        if width > 1024: width = 1024
        if height > 768: height = 768
        root.geometry(f"{width: <d}x{height: <d}")

        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)

        self.grid(column=0, row=0, sticky=tk.N+tk.S+tk.E+tk.W)

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        menubar = tk.Menu(root)
        root.config(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(label='Open...', underline=0, command=self.__open)
        file_menu.add_separator()
        file_menu.add_command(label='Exit', underline=1, command=root.destroy)

        menubar.add_cascade(label='File', underline=0, menu=file_menu)

        img_ops_menu = tk.Menu(menubar, tearoff=False)
        img_ops_menu.add_command(label='Combine...', underline=0,
                                 command=lambda: Combine(self.winfo_toplevel()))
        img_ops_menu.add_command(label='Crop...', underline=3,
                                 command=lambda: Crop(self.winfo_toplevel()))
        img_ops_menu.add_command(label='Reduce...', underline=0,
                                 command=lambda: Reduce(self.winfo_toplevel()))

        menubar.add_cascade(label='Image Ops', underline=0, menu=img_ops_menu)

        cfg_menu = tk.Menu(menubar, tearoff=False)
        cfg_menu.add_command(label='Camera', underline=0,
                             command=lambda: CamCfgGUI(self.winfo_toplevel()))

        menubar.add_cascade(label='Configuration', underline=0, menu=cfg_menu)

        self._image_display = ImageDisplay(self)
        self._image_display.grid(row=0, column=0, sticky=tk.N+tk.S+tk.E+tk.W)

        root.update_idletasks()
        self._image_display.grid_remove()
        self._specview = Specview(self, width=self.winfo_width(), height=self.winfo_height())
        self._specview.grid(row=0, column=0, sticky=tk.N+tk.S+tk.E+tk.W)
        self._specview_visible = True

    def __open(self):
        file_types = (('FITS', '*.fit *.fits'), ('all', '*'))
        file_name = fd.askopenfilename(title='Open FITS file', filetypes=file_types,
                                       initialdir=spectra.current_dir)
        if not file_name:
            return
        spectra.current_dir = Path(file_name).parent
        hdu_l = fits.open(file_name)
        header = hdu_l[0].header
        data = hdu_l[0].data
        hdu_l.close()
        if header['NAXIS'] == 1:
            if not self._specview_visible:
                self._image_display.grid_forget()
                self._specview.grid()
                self._specview_visible = True
            self._specview.clear()
            self._specview.add_spectrum(data)
        elif header['NAXIS'] == 2:
            data = None
            if self._specview_visible:
                self._specview.grid_forget()
                self._specview_visible = False
                self._image_display.grid()
            fits_image = FitsImageFile(file_name)
            self._image_display.set_image(fits_image)

    def __combine(self):
        Combine(self.winfo_toplevel())


if __name__ == '__main__':
    os.chdir(spectra.current_dir)
    main = tk.Tk()
    main.wm_title("Spectra")
    main_frame = Main(main)
    main.eval('tk::PlaceWindow . center')
    tk.mainloop()

# See PyCharm help at https://www.jetbrains.com/help/pycharm/
