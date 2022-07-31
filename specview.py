from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg as FigureCanvas
from matplotlib.backends.backend_wxagg import NavigationToolbar2WxAgg as NavigationToolbar
from matplotlib.backend_bases import MouseEvent
from matplotlib.figure import Figure
import numpy as np
import numpy.typing as npt
from typing import Union, Any, Callable, SupportsFloat, SupportsInt
import wx


class Specview(wx.Panel):
    def __init__(self, parent: wx.Window, **kwargs):
        super().__init__(parent, **kwargs)
        self._fig = Figure()
        self._axes = self._fig.add_subplot(111)
        self._axes.set_xlabel('Pixels')
        self._axes.set_ylabel('Flux [ADU]')
        self._lines = dict()
        self._xdata = None
        self._line_id = 0
        self._canvas = FigureCanvas(self, wx.ID_ANY, self._fig)
        self._toolbar = NavigationToolbar(self._canvas)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self._canvas, 1, wx.LEFT | wx.TOP | wx.GROW)
        sizer.Add(self._toolbar, 0, wx.LEFT | wx.EXPAND)
        self.SetSizer(sizer)
        self.Fit()

        self._picking_cb = None
        self._picking_me_cid = None
        self._picking_pi_cid = None
        self._picking_line = None
        self._pick_xdata = None
        self._picked_x = None

    def add_spectrum(self, data: npt.NDArray[Any], lambda_ref: Union[None, float] = None,
                     lambda_step: Union[None, float] = None, fmt: str = '-b') -> str:
        if self._xdata is None:
            if lambda_ref is None:
                self._xdata = np.arange(data.shape[0])
            else:
                self._xdata = np.linspace(lambda_ref,
                                          lambda_ref + (data.shape[0] - 1) * lambda_step,
                                          data.shape[0] - 1)
        line_id = f'line{self._line_id:<d}'
        self._lines[line_id] = self._axes.plot(self._xdata, data, fmt).pop()
        self._axes.relim()
        self._canvas.draw()

        return line_id

    def clear(self):
        for item in self._lines.items():
            item[1].remove()
        self._lines.clear()
        self._canvas.draw()

    def set_spectrum_data(self, spec_id: str, data: npt.NDArray[Any]):
        if spec_id not in self._lines:
            raise ValueError(f'spectrum ID {spec_id} not found')
        if data.shape[0] != self._xdata.shape[0]:
            raise ValueError('wrong shape for spectrum data')
        line = self._lines[spec_id]
        line.set_ydata(data)
        self._canvas.draw()

    def start_picking(self, callback: Callable[[Union[SupportsFloat, SupportsInt], bool], None]):
        if self._picking_cb is None:
            self._picking_me_cid = self._canvas.mpl_connect('button_press_event', self._on_click)
        self._picking_cb = callback

    def set_pick_data(self, xdata: npt.NDArray[Any], ydata: npt.NDArray[Any], fmt: str = 'or'):
        if self._picking_line is None:
            self._picking_line, = self._axes.plot(xdata, ydata, fmt)
        else:
            self._picking_line.set_data(xdata, ydata)
        self._pick_xdata = xdata
        self._canvas.draw()

    def _on_click(self, event: MouseEvent):
        if self._picking_cb is None:
            return
        if event.inaxes != self._axes:
            return
        self._picking_cb(event.xdata, event.key == 'shift')


if __name__ == '__main__':
    import extract
    from pathlib import Path

    app = wx.App()
    frame = wx.Frame(None, title='Spectrum View')
    disp = Specview(frame)
    frame.SetMinSize(wx.Size(800, 600))
    frame.Show()
    spectrum, _ = extract.simple_single(Path.home() / 'astrowrk/spectra/reduced/rot-drk-flat.fits', (150, 200))
    disp.add_spectrum(spectrum[1:spectrum.shape[0] - 2])
    app.MainLoop()
