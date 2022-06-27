from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.backend_bases import MouseEvent, PickEvent
from matplotlib.figure import Figure
import numpy as np
import numpy.typing as npt
import tkinter as tk
from tkinter import ttk
from typing import Union, Any, Callable, SupportsFloat, SupportsInt


class Specview(ttk.Frame):
    def __init__(self, master: Union[tk.Widget, ttk.Widget, tk.Tk, tk.Toplevel], **kwargs):
        super().__init__(master, **kwargs)
        dpi = master.winfo_toplevel().winfo_fpixels('1i')
        self._fig = Figure(figsize=(5, 4), dpi=dpi)
        self._axes = self._fig.add_subplot()
        self._axes.set_xlabel('Pixels')
        self._axes.set_ylabel('Flux [ADU]')
        self._lines = dict()
        self._xdata = None
        self._line_id = 0
        self._canvas = FigureCanvasTkAgg(self._fig, master=self)
        self._canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH)
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
        self._lines[line_id], = self._axes.plot(self._xdata, data, fmt)
        self._canvas.draw()

        return line_id

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
