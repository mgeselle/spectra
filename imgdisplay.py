from astropy.io import fits
from astropy.visualization import ImageNormalize, MinMaxInterval, AsinhStretch
from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg as FigureCanvas
from matplotlib.backends.backend_wxagg import NavigationToolbar2WxAgg as NavigationToolbar
from matplotlib.figure import Figure
from os import PathLike
from pathlib import Path
from typing import Union
import wx


class ImageDisplay(wx.Panel):
    def __init__(self, parent: wx.Window, **kwargs):
        super().__init__(parent, **kwargs)

        self._figure = Figure()
        self._axes = self._figure.add_subplot(111)
        self._canvas = FigureCanvas(self, -1, self._figure)
        self._toolbar = NavigationToolbar(self._canvas)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self._canvas, 1, wx.LEFT | wx.TOP | wx.GROW)
        sizer.Add(self._toolbar, 0, wx.LEFT | wx.EXPAND)
        self.SetSizer(sizer)
        self.Fit()

        self._image = None

    def display(self, file: Union[str, bytes, PathLike]):
        file_path = Path(file)
        if not file_path.is_file() or not file_path.exists():
            raise FileNotFoundError("File does not exist or is a directory.")
        with fits.open(file_path) as in_hdu_l:
            self._axes.cla()
            self._image = in_hdu_l[0].data
            norm = ImageNormalize(self._image, interval=MinMaxInterval(), stretch=AsinhStretch())
            self._axes.imshow(self._image, origin='lower', norm=norm)
            self._canvas.draw()


if __name__ == '__main__':
    app = wx.App()
    frame = wx.Frame(None, title='Image Display')
    disp = ImageDisplay(frame)
    frame.SetMinSize(wx.Size(800, 600))
    frame.Show()
    disp.display('/home/mgeselle/astrowrk/spectra/cropped_b/Castor_Light_2022-04-17T22-21-53_001.fits')
    app.MainLoop()
