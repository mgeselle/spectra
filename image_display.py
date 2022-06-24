import tkinter as tk
from tkinter import ttk
from PIL.ImageTk import PhotoImage
from PIL.ImageEnhance import Brightness, Contrast
from pathlib import Path


class ImageDisplay(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self._canvas = tk.Canvas(self)
        self._canvas.grid(row=0, column=0, sticky=tk.N + tk.S + tk.E + tk.W)
        self._x_scroll = ttk.Scrollbar(self, orient=tk.HORIZONTAL, command=self._canvas.xview)
        self._canvas.configure(xscrollcommand=self._x_scroll.set)
        self._x_scroll.grid(row=1, column=0, sticky=tk.E + tk.W)
        self._y_scroll = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=self._y_scroll.set)
        self._y_scroll.grid(row=0, column=1, sticky=tk.N + tk.S)
        self._image_file = None
        self._image = None
        self._photo = None

        status_frame = ttk.Frame(self)
        status_frame.grid(row=2, column=0, columnspan=2, sticky=tk.N + tk.S + tk.E + tk.W)
        status_frame.columnconfigure(1, weight=1)

        slider_frame = ttk.Frame(status_frame)
        slider_frame.grid(row=0, column=0, sticky=tk.N + tk.S + tk.E + tk.W)
        res_dir = Path(__file__).parent / 'resources'
        self._bright_icon = tk.PhotoImage(file=res_dir / 'brightness.gif')

        bright_label = ttk.Label(slider_frame, image=self._bright_icon, padding=(4, 4, 4, 4))
        bright_label.grid(row=0, column=0, sticky=tk.E)
        self._brightness = tk.DoubleVar(slider_frame, 1.0, 'brightness')
        self._bright_slide = ttk.Scale(slider_frame, from_=1.0, to=10.0,
                                       orient=tk.HORIZONTAL, state=tk.DISABLED,
                                       variable=self._brightness, command=self._brightness_contrast_changed)
        self._bright_slide.grid(row=0, column=1, sticky=tk.E)

        self._contrast_icon = tk.PhotoImage(file=res_dir / 'contrast.gif')
        contrast_label = ttk.Label(slider_frame, image=self._contrast_icon, padding=(4, 4, 4, 4))
        contrast_label.grid(row=0, column=2, sticky=tk.E)
        self._contrast = tk.DoubleVar(slider_frame, 1.0, 'contrast')
        self._contrast_slide = ttk.Scale(slider_frame, from_=1.0, to=10.0,
                                         orient=tk.HORIZONTAL, state=tk.DISABLED,
                                         variable=self._contrast, command=self._brightness_contrast_changed)
        self._contrast_slide.grid(row=0, column=3, sticky=tk.E)

        coords_frame = ttk.Frame(status_frame)
        coords_frame.grid(row=0, column=2, sticky=tk.W)
        self._image_dims = tk.StringVar()
        self._image_dims.set('')
        dims_label = ttk.Label(coords_frame, textvariable=self._image_dims)
        dims_label.pack(side=tk.LEFT, anchor=tk.W, padx=(0, 4), pady=(4,4))
        coords_x_label = ttk.Label(coords_frame, text='x')
        coords_x_label.pack(side=tk.LEFT, anchor=tk.E, padx=(4, 4), pady=(4, 4))
        self._image_x = tk.StringVar(coords_frame, '', 'image_x')
        coords_x_text = ttk.Label(coords_frame, textvariable=self._image_x,
                                  width=6, relief=tk.GROOVE, anchor=tk.E)
        coords_x_text.pack(side=tk.LEFT, anchor=tk.E, padx=(4, 4), pady=(4, 4))

        coords_y_label = ttk.Label(coords_frame, text='y')
        coords_y_label.pack(side=tk.LEFT, anchor=tk.E, padx=(10, 4), pady=(4, 4))
        self._image_y = tk.StringVar(coords_frame, '', 'image_y')
        coords_y_text = ttk.Label(coords_frame, textvariable=self._image_y,
                                  width=6, relief=tk.GROOVE, anchor=tk.E)
        coords_y_text.pack(side=tk.LEFT, anchor=tk.E, padx=(4, 4), pady=(4, 4))

        coords_adu_label = ttk.Label(coords_frame, text='ADU')
        coords_adu_label.pack(side=tk.LEFT, anchor=tk.E, padx=(10, 4), pady=(4, 4))
        self._image_adu = tk.StringVar(coords_frame, '', 'image_adu')
        coords_adu_text = ttk.Label(coords_frame, textvariable=self._image_adu,
                                    width=7, relief=tk.GROOVE, anchor=tk.E)
        coords_adu_text.pack(side=tk.LEFT, anchor=tk.E, padx=(4, 4), pady=(4, 4))

        self._canvas.bind('<Enter>', self._enter_motion)
        self._canvas.bind('<Motion>', self._enter_motion)

    def get_canvas_size(self):
        return self._canvas.winfo_width(), self._canvas.winfo_height()

    def set_image(self, image_file):
        if self._canvas.gettags('image'):
            self._canvas.delete('image')
            self._brightness.set(1.0)
            self._contrast.set(1.0)
        else:
            self._bright_slide.configure(state=tk.NORMAL)
            self._contrast_slide.configure(state=tk.NORMAL)
        self._image_file = image_file
        w = self._canvas.winfo_width()
        h = self._canvas.winfo_height()
        print(f'Canvas dimensions {w}x{h}')
        self._canvas.configure(scrollregion=(0, 0, w, h))
        self._image = self._image_file.as_image((w, h))
        self._photo = PhotoImage(self._image)
        self._canvas.create_image(0, 0, image=self._photo, anchor=tk.NW, tags='image')

        img_w = self._image_file.width
        img_h = self._image_file.height
        self._image_dims.set(f'{img_w:<d}x{img_h:<d}')

    # noinspection PyUnusedLocal
    def _brightness_contrast_changed(self, event):
        brightness = self._brightness.get()
        contrast = self._contrast.get()
        self._image = self._image_file.as_image(self._image.size)
        if brightness > 1.0:
            self._image = Brightness(self._image).enhance(brightness)
        if contrast > 1.0:
            self._image = Contrast(self._image).enhance(contrast)
        self._canvas.delete('image')
        self._photo = PhotoImage(self._image)
        self._canvas.create_image(0, 0, image=self._photo, anchor=tk.NW, tags='image')

    def _enter_motion(self, event):
        if self._image is None:
            return
        x = self._canvas.canvasx(event.x)
        y = self._canvas.canvasy(event.y)
        scale = self._image.width / self._image_file.width
        x_img = int(x / scale)
        y_img = int(y / scale)
        self._image_x.set(f'{x_img: >6d}')
        self._image_y.set(f'{y_img: >6d}')
        adu = int(self._image_file.adu(x_img, y_img))
        self._image_adu.set(f'{adu: >7d}')
