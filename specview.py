import abc
from abc import ABC
from dataclasses import dataclass
from math import sqrt, log
from pathlib import Path
from typing import Union, Any

import matplotlib.transforms as transforms
import numpy as np
import numpy.ma as ma
import numpy.typing as npt
import numpy.polynomial as npp
import scipy.optimize as optimize
import wx
import wx.lib.newevent as ne
from astropy.io import fits
from matplotlib.axes import Axes
from matplotlib.backend_bases import MouseEvent, MouseButton, PickEvent, KeyEvent
from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg as FigureCanvas
from matplotlib.backends.backend_wxagg import NavigationToolbar2WxAgg as NavigationToolbar
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from scipy import interpolate

from wxutil import pick_save_file

FileReadyEvent, EVT_ID_FILE_READY = ne.NewEvent()


@dataclass
class SpecData:
    line: Line2D
    data: npt.NDArray[Any]
    header: fits.Header


class SpecEvtHandler(ABC):
    def __init__(self):
        self._figure = None
        self._axes = None
        self._data = None

    def init(self, figure: Figure, axes: Axes):
        self._figure = figure
        self._axes = axes

    def set_data(self, data: SpecData):
        self._data = data

    @abc.abstractmethod
    def dispose(self):
        pass


class SaveHandler(ABC):

    @abc.abstractmethod
    def save_file(self, file_path: Path):
        pass


class AnnotationHandler(SpecEvtHandler):
    def __init__(self):
        super().__init__()
        self._mouse_cid = None
        self._pick_cid = None
        self._key_cid = None
        self._text = None
        self._text_data = None
        self._text_pos = 0
        self._text_x = None
        self._text_y = None
        self._editing = False

    def init(self, figure: Figure, axes: Axes):
        super().init(figure, axes)
        self._mouse_cid = self._figure.canvas.mpl_connect('button_press_event', self._on_click)
        self._pick_cid = self._figure.canvas.mpl_connect('pick_event', self._on_pick)

    def dispose(self):
        if self._key_cid is not None:
            self._figure.canvas.mpl_disconnect(self._key_cid)
        self._figure.canvas.mpl_disconnect(self._pick_cid)
        self._figure.canvas.mpl_disconnect(self._mouse_cid)

    def _on_click(self, event: MouseEvent):
        if not event.inaxes:
            return
        if self._key_cid is None:
            self._key_cid = self._figure.canvas.mpl_connect('key_press_event', self._on_key)
        self._text_x = event.xdata
        self._text_y = event.ydata
        self._editing = True

    def _on_pick(self, event: PickEvent):
        self._text = event.artist
        self._text_data = self._text.get_text()
        self._text_pos = 0
        self._editing = event.mouseevent.dblclick

    def _on_key(self, event: KeyEvent):
        if event.key == 'escape':
            if self._editing:
                self._editing = False
            else:
                self._end_editing()
            return

        if event.key == 'alt+ctrl+@':
            key = '@'
        else:
            key = event.key

        if self._editing:
            if self._text is None:
                self._text_data = ''
                self._text_pos = 0
                self._text = self._axes.text(self._text_x, self._text_y, self._text_data, picker=10.0)
            if key == 'left' and self._text_pos > 0:
                self._text_pos -= 1
            elif key == 'right' and self._text_pos < len(self._text_data):
                self._text_pos += 1
            elif key == 'backspace':
                if self._text_pos > 0:
                    self._text_data = self._text_data[0:self._text_pos - 1] + self._text_data[self._text_pos:]
                    self._text_pos -= 1
                    self._text.set_text(self._text_data)
                    self._figure.canvas.draw_idle()
            elif key == 'delete' and self._text_pos < len(self._text_data):
                self._text_data = self._text_data[0:self._text_pos] + self._text_data[self._text_pos + 1:]
                self._text.set_text(self._text_data)
                self._figure.canvas.draw_idle()
            elif len(key) == 1:
                self._text_data = self._text_data[0:self._text_pos] + key + self._text_data[self._text_pos:]
                self._text_pos += 1
                self._text.set_text(self._text_data)
                self._figure.canvas.draw_idle()
        elif key == 'backspace' and self._text is not None:
            self._text.remove()
            self._end_editing()
            self._figure.canvas.draw_idle()

    def _end_editing(self):
        self._text = None
        self._figure.canvas.mpl_disconnect(self._key_cid)
        self._key_cid = None


class ContinuumFit(SpecEvtHandler, SaveHandler):
    def __init__(self, parent: wx.Window):
        super().__init__()
        self._parent = parent
        self._mouse_cid = None
        self._key_cid = None
        self._x_pick = None
        self._y_pick = None
        self._pick_line = None
        self._pick_sel_idx = None
        self._pick_sel_line = None
        self._xdata = None
        self._continuum = None
        self._continuum_line = None

    def init(self, figure: Figure, axes: Axes):
        super().init(figure, axes)
        header = self._data.header
        data = self._data.data
        if header is None or 'CDELT1' not in header:
            self._xdata = np.arange(0, data.size)
        else:
            lambda_step = float(header['CDELT1'])
            lambda_ref = float(header['CRVAL1']) + (1 - float(header['CRPIX1'])) * lambda_step
            lambda_end = lambda_ref + (data.size - 1) * lambda_step
            self._xdata = np.linspace(lambda_ref, lambda_end, data.size)

        # Initially fit a polynomial to the spectrum
        xdata = ma.asarray(self._xdata)
        ydata = ma.asarray(data)
        pixel_rejected = True
        while pixel_rejected:
            if xdata.mask is ma.nomask:
                x_fit = xdata
                y_fit = ydata
            else:
                x_fit = xdata[~xdata.mask]
                y_fit = ydata[~ydata.mask]
            poly = npp.Polynomial.fit(x_fit, y_fit, 30)
            residual = (ydata - poly(xdata))**2
            residual.mask = xdata.mask
            mean_res = ma.mean(residual)
            rej_idx = ma.nonzero(residual > 25 * mean_res)[0]
            pixel_rejected = False
            for idx in rej_idx:
                pixel_rejected = True
                xdata[idx] = ma.masked
                ydata[idx] = ma.masked
        # Now create a spline from the polynom in order to allow the user to add/remove points
        interval = int((data.size - 1)/ 20)
        self._x_pick = []
        self._y_pick = []
        for idx in range(0, data.size, interval):
            self._x_pick.append(self._xdata[idx])
        if 20 * interval != data.size - 1:
            self._x_pick.append(self._xdata[-1])
        self._y_pick = list(poly(np.asarray(self._x_pick)))

        tck = interpolate.splrep(self._x_pick, self._y_pick, s=0, k=3)
        self._continuum = interpolate.splev(self._xdata, tck, der=0)
        self._continuum_line = self._axes.plot(self._xdata, self._continuum, '-r').pop()
        self._pick_line = self._axes.plot(self._x_pick, self._y_pick, 'or').pop()
        self._mouse_cid = self._figure.canvas.mpl_connect('button_press_event', self._on_click)
        self._key_cid = self._figure.canvas.mpl_connect('key_press_event', self._on_key)
        self._figure.canvas.draw_idle()

    def dispose(self):
        self._figure.canvas.mpl_disconnect(self._key_cid)
        self._figure.canvas.mpl_disconnect(self._mouse_cid)
        if self._pick_sel_line is not None:
            self._pick_sel_line.remove()
        if self._pick_line is not None:
            self._pick_line.remove()
        if self._continuum_line is not None:
            self._continuum_line.remove()

    def save_file(self, file_path: Path):
        hdu = fits.PrimaryHDU(self._data.data, self._data.header)
        hdu.writeto(file_path, overwrite=True)

    @property
    def continuum(self):
        return self._continuum

    def _on_click(self, event: MouseEvent):
        if not event.inaxes or self._continuum_line is None or event.button != MouseButton.RIGHT:
            return
        x_idx = int((event.xdata - self._xdata[0]) / (self._xdata[1] - self._xdata[0]))
        x = self._xdata[x_idx]
        y = event.ydata
        min_idx = 0
        min_delta = None
        for i in range(0, len(self._x_pick)):
            delta = abs(self._x_pick[i] - x)
            if min_delta is None or delta < min_delta:
                min_delta = delta
                min_idx = i
            elif delta > min_delta:
                break
        closest_marker_data = (self._x_pick[min_idx], self._y_pick[min_idx])
        closest_marker_screen = self._axes.transData.transform(closest_marker_data)
        event_screen = self._axes.transData.transform((x, y))
        distance = sqrt((closest_marker_screen[0] - event_screen[0]) ** 2 +
                        (closest_marker_screen[1] - event_screen[1]) ** 2)
        if distance <= 10:
            if len(self._x_pick) < 3:
                return
            self._pick_sel_idx = min_idx
            line_modified = False
        elif x < self._x_pick[min_idx]:
            self._x_pick = self._x_pick[0:min_idx] + [x] + self._x_pick[min_idx:]
            self._y_pick = self._y_pick[0:min_idx] + [y] + self._y_pick[min_idx:]
            self._pick_sel_idx = min_idx
            line_modified = True
        else:
            self._x_pick = self._x_pick[0:min_idx + 1] + [x] + self._x_pick[min_idx + 1:]
            self._y_pick = self._y_pick[0:min_idx + 1] + [y] + self._y_pick[min_idx + 1:]
            self._pick_sel_idx = min_idx + 1
            line_modified = True

        if self._pick_sel_line is not None:
            self._pick_sel_line.remove()
            self._pick_sel_line = None
        if line_modified:
            if len(self._x_pick) < 4:
                k = 1
            else:
                k = 3
            tck = interpolate.splrep(self._x_pick, self._y_pick, s=0, k=k)
            self._continuum = interpolate.splev(self._xdata, tck, der=0)
            self._continuum_line.set_data(self._xdata, self._continuum)
        x_pick = self._x_pick[0:self._pick_sel_idx] + self._x_pick[self._pick_sel_idx + 1:]
        y_pick = self._y_pick[0:self._pick_sel_idx] + self._y_pick[self._pick_sel_idx + 1:]
        self._pick_line.set_data(x_pick, y_pick)
        self._pick_sel_line = self._axes.plot([self._x_pick[self._pick_sel_idx]],
                                              [self._y_pick[self._pick_sel_idx]], 'og').pop()

        self._figure.canvas.draw_idle()

    def _on_key(self, event: KeyEvent):
        if self._continuum_line is None:
            return
        if self._pick_sel_idx is not None and event.key == 'delete':
            self._x_pick = self._x_pick[0:self._pick_sel_idx] + self._x_pick[self._pick_sel_idx + 1:]
            self._y_pick = self._y_pick[0:self._pick_sel_idx] + self._y_pick[self._pick_sel_idx + 1:]
            self._pick_sel_idx = None
            self._pick_sel_line.remove()
            self._pick_sel_line = None
            if len(self._x_pick) < 4:
                k = 1
            else:
                k = 3
            tck = interpolate.splrep(self._x_pick, self._y_pick, s=0, k=k)
            self._continuum = interpolate.splev(self._xdata, tck, der=0)
            self._continuum_line.set_data(self._xdata, self._continuum)
            self._pick_line.set_data(self._x_pick, self._y_pick)
            self._figure.canvas.draw_idle()
        elif event.key == 'enter':
            if self._pick_sel_line is not None:
                self._pick_sel_line.remove()
                self._pick_sel_line = None
            self._pick_line.remove()
            self._pick_line = None
            self._continuum_line.remove()
            self._continuum_line = None
            self._data.data = self._data.data / self._continuum
            self._data.line.set_data(self._xdata, self._data.data)
            self._axes.autoscale()
            self._axes.relim()
            self._figure.canvas.draw_idle()
            self._parent.QueueEvent(FileReadyEvent())


class PeakMeasureHandler(SpecEvtHandler):
    def __init__(self, parent: wx.Window):
        super().__init__()
        self._parent = parent
        self._data = None
        self._lambda_start = None
        self._lambda_step = None

        self._click_cid = None
        self._move_cid = None
        self._key_cid = None
        self._start_marker = None
        self._peak_line = None
        self._line_start_idx = None
        self._line_end_idx = None
        self._start_x = None
        self._start_y = None

    def init(self, figure: Figure, axes: Axes):
        super().init(figure, axes)
        self._click_cid = self._figure.canvas.mpl_connect('button_press_event', self._on_click)

    def set_data(self, data: SpecData):
        self._data = data.data
        header = data.header
        if 'CRVAL1' in header:
            self._lambda_step = float(header['CDELT1'])
            self._lambda_start = float(header['CRVAL1']) + (1.0 - float(header['CRPIX1']) * self._lambda_step)
        else:
            self._lambda_step = 1.0
            self._lambda_start = 0.0

    def dispose(self):
        if self._start_marker is not None:
            self._start_marker.remove()
            self._start_marker = None
            if self._peak_line is not None:
                self._peak_line.remove()
                self._peak_line = None
            self._figure.canvas.draw_idle()
            if self._move_cid is not None:
                self._figure.canvas.mpl_disconnect(self._move_cid)
                self._move_cid = None
            if self._key_cid is not None:
                self._figure.canvas.mpl_disconnect(self._key_cid)
                self._key_cid = None
        self._figure.canvas.mpl_disconnect(self._click_cid)
        self._click_cid = None
        self._data = None

    def _on_click(self, event: MouseEvent):
        if self._key_cid is not None:
            self._figure.canvas.mpl_disconnect(self._key_cid)
            self._key_cid = None
        if self._start_marker is not None:
            self._start_marker.remove()
            self._start_marker = None
            if self._peak_line is not None:
                self._peak_line.remove()
                self._peak_line = None
        if not event.inaxes:
            return
        self._line_start_idx = int((event.xdata - self._lambda_start) / self._lambda_step)
        if self._line_start_idx >= self._data.size or self._line_start_idx < 0:
            self._line_start_idx = None
            return
        self._start_x = self._lambda_start + self._line_start_idx * self._lambda_step
        self._start_y = self._data[self._line_start_idx]
        self._start_marker = self._axes.plot([self._start_x], [self._start_y], 'or').pop()
        self._move_cid = self._figure.canvas.mpl_connect('motion_notify_event', self._on_move)
        self._figure.canvas.mpl_disconnect(self._click_cid)
        self._click_cid = self._figure.canvas.mpl_connect('button_release_event', self._on_release)
        self._figure.canvas.draw_idle()

    def _draw_line_to_event(self, event: MouseEvent, draw_markers: bool = False) -> int:
        x_idx = int((event.xdata - self._lambda_start) / self._lambda_step)
        x = event.xdata
        if x_idx < 0:
            x_idx = 0
            x = self._lambda_start
        elif x_idx >= self._data.size:
            x_idx = self._data.size - 1
            x = self._lambda_start + (self._data.size - 1) * self._lambda_step
        if x < self._start_x:
            x_d = [x, self._start_x]
            y_d = [self._data[x_idx], self._start_y]
        else:
            x_d = [self._start_x, x]
            y_d = [self._start_y, self._data[x_idx]]
        if self._peak_line is None:
            self._peak_line = self._axes.plot(x_d, y_d, '-r').pop()
        else:
            self._peak_line.set_data(x_d, y_d)
        if draw_markers:
            self._start_marker.set_data(x_d, y_d)
        self._figure.canvas.draw_idle()
        return x_idx

    def _on_move(self, event: MouseEvent):
        if not event.inaxes:
            return
        self._draw_line_to_event(event)

    def _on_release(self, event: MouseEvent):
        if not event.inaxes:
            if self._peak_line is not None:
                self._peak_line.remove()
                self._peak_line = None
            self._start_marker.remove()
            self._start_marker = None
            self._figure.canvas.draw_idle()
        else:
            self._line_end_idx = self._draw_line_to_event(event, draw_markers=True)
            if self._line_end_idx < self._line_start_idx:
                tmp = self._line_end_idx
                self._line_end_idx = self._line_start_idx
                self._line_start_idx = tmp
        self._figure.canvas.mpl_disconnect(self._move_cid)
        self._move_cid = None
        self._figure.canvas.mpl_disconnect(self._click_cid)
        self._click_cid = self._figure.canvas.mpl_connect('button_press_event', self._on_click)
        self._key_cid = self._figure.canvas.mpl_connect('key_press_event', self._on_key)

    def _on_key(self, event: KeyEvent):
        if event.key != 'enter':
            return
        self._figure.canvas.mpl_disconnect(self._key_cid)
        self._key_cid = None

        # We will try to fit a gaussian on a line to the peak, i.e.:
        # f(l) = a + b * l + c * exp(-0.5 * [(l - e) / d]**2)
        lr_start = self._lambda_start + self._line_start_idx * self._lambda_step
        lr_end = self._lambda_start + self._line_end_idx * self._lambda_step

        xdata = np.linspace(lr_start, lr_end, self._line_end_idx - self._line_start_idx + 1)
        ydata = self._data[self._line_start_idx:self._line_end_idx + 1]
        ymean = (ydata[0] + ydata[-1]) / 2
        x_mid_idx = int(xdata.size / 2)
        a_0 = (ydata[0] * xdata[-1] - ydata[-1] * xdata[0]) / (xdata[-1] - xdata[0])
        b_0 = (ydata[-1] - ydata[0]) / (xdata[-1] - xdata[0])
        if ydata[x_mid_idx] < ymean:
            c_0 = -(np.min(ydata) - ymean)
        else:
            c_0 = np.max(ydata) - ymean
        factor = 2 * sqrt(2 * log(2))
        d_0 = (xdata[-1] - xdata[0]) / (4 * factor)
        e_0 = xdata[int(xdata.size / 2)]

        def model(x, a, b, c, d, e):
            return a + x * b + c * np.exp(-0.5 * ((x - e) / d) ** 2)

        try:
            popt, _ = optimize.curve_fit(model, xdata, ydata, p0=(a_0, b_0, c_0, d_0, e_0))
        except RuntimeError as ex:
            with wx.MessageDialog(self._parent, str(ex), 'Curve Fitting Error',
                                  style=wx.OK | wx.ICON_ERROR | wx.CENTRE) as dlg:
                dlg.ShowModal()
            return
        self._peak_line.set_data(xdata, model(xdata, *popt))
        fwhm = abs(popt[3] * factor)
        text = f'{popt[4]:.3f}\nFWHM = {fwhm:.3f}'
        if popt[2] < 0:
            x_off = -10 / 72
            y_off = -10 / 72
            rotation = 270.0
        else:
            rotation = 'vertical'
            x_off = 10 / 72
            y_off = 10 / 72
        translation = transforms.ScaledTranslation(x_off, y_off, self._figure.dpi_scale_trans)
        transform = self._axes.transData + translation
        self._axes.text(popt[4], model(popt[4:5], *popt)[0],
                        text, rotation=rotation, transform=transform, transform_rotates_text=False,
                        rotation_mode='anchor')
        self._figure.canvas.draw_idle()


class CropHandler(SpecEvtHandler, SaveHandler):
    def dispose(self):
        super().dispose()
        if self._mouse_cid is not None:
            self._figure.canvas.mpl_disconnect(self._mouse_cid)
            self._mouse_cid = None
        if self._key_cid is not None:
            self._figure.canvas.mpl_disconnect(self._key_cid)
            self._key_cid = None
        if self._low_line is not None:
            self._low_line.remove()
            self._low_line = None
        if self._high_line is not None:
            self._high_line.remove()
            self._high_line = None

    def save_file(self, file_path: Path):
        idx_low, idx_high, lambda_ref, _ = self._get_indexes()
        header = self._data.header
        header['CRVAL1'] = lambda_ref
        header['CRPIX1'] = 1.0
        data = self._data.data[idx_low:idx_high]
        hdu = fits.PrimaryHDU(data, header)
        hdu.writeto(file_path, overwrite=True)

    def init(self, figure: Figure, axes: Axes):
        super().init(figure, axes)
        figure.canvas.mpl_connect('button_press_event', self._on_click)

    def __init__(self, parent: wx.Window):
        super().__init__()
        self._parent = parent
        self._mouse_cid = None
        self._key_cid = None
        self._lambda_low = None
        self._lambda_high = None
        self._low_line = None
        self._high_line = None

    def _on_click(self, event: MouseEvent):
        if not event.inaxes:
            return
        if event.button == MouseButton.LEFT:
            self._lambda_low = event.xdata
            if self._low_line is not None:
                self._low_line.remove()
            self._low_line = self._axes.axvline(self._lambda_low, linestyle='--')
            if self._lambda_high is not None and self._lambda_high <= self._lambda_low:
                self._lambda_high = None
                self._high_line.remove()
                self._high_line = None
            self._figure.canvas.draw_idle()
        elif event.button == MouseButton.RIGHT:
            self._lambda_high = event.xdata
            if self._high_line is not None:
                self._high_line.remove()
            self._high_line = self._axes.axvline(self._lambda_high, linestyle='--')
            if self._lambda_low is not None and self._lambda_low >= self._lambda_high:
                self._lambda_low = None
                self._low_line.remove()
                self._low_line = None
            self._figure.canvas.draw_idle()
        if self._lambda_low is not None and self._lambda_high is not None and self._key_cid is None:
            self._key_cid = self._figure.canvas.mpl_connect('key_press_event', self._on_key)
        elif (self._lambda_low is None or self._lambda_high is None) and self._key_cid is not None:
            self._figure.canvas.mpl_disconnect(self._key_cid)
            self._key_cid = None

    def _on_key(self, event: KeyEvent):
        if event.key != 'enter':
            return
        self._figure.canvas.mpl_disconnect(self._key_cid)
        self._low_line.remove()
        self._low_line = None
        self._high_line.remove()
        self._high_line = None
        idx_low, idx_high, x_low, x_high = self._get_indexes()
        xdata = np.linspace(x_low, x_high,
                            num=idx_high - idx_low, endpoint=False)
        ydata = self._data.data[idx_low:idx_high]
        self._data.line.set_data(xdata, ydata)
        self._axes.autoscale()
        self._axes.relim()
        self._figure.canvas.draw_idle()
        self._parent.QueueEvent(FileReadyEvent())

    def _get_indexes(self):
        header = self._data.header
        lambda_step = header['CDELT1']
        lambda_ref = header['CRVAL1'] + (1 - header['CRPIX1']) * lambda_step
        idx_low = int((self._lambda_low - lambda_ref) / lambda_step)
        if idx_low < 0:
            idx_low = 0
        idx_high = int((self._lambda_high - lambda_ref) / lambda_step)
        if idx_high > self._data.data.size:
            idx_high = self._data.data.size
        x_low = lambda_ref + idx_low * lambda_step
        x_high = lambda_ref + idx_high * lambda_step

        return idx_low, idx_high, x_low, x_high


class Specview(wx.Panel):
    def __init__(self, parent: wx.Window, **kwargs):
        super().__init__(parent, **kwargs)
        self._fig = Figure()
        self._axes = self._fig.add_subplot(111)
        self._axes.set_xlabel('Pixels')
        self._axes.set_ylabel('Relative Intensity')
        self._lines = dict()
        self._xdata = None
        self._line_id = 0
        self._canvas = FigureCanvas(self, wx.ID_ANY, self._fig)
        self._toolbar = NavigationToolbar(self._canvas)
        self._toolbar.Realize()

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self._canvas, 1, wx.LEFT | wx.TOP | wx.GROW)
        sizer.Add(self._toolbar, 0, wx.LEFT | wx.EXPAND)
        sizer.SetSizeHints(self)
        self.SetSizer(sizer)
        sz = self._canvas.GetBestSize()
        tb_sz = self._toolbar.GetBestSize()
        min_sz = wx.Size(sz.Width, sz.Height + tb_sz.Height)
        self.SetMinSize(min_sz)

        self._event_handler = None
        self._current_max = None

    def add_spectrum(self, data: npt.NDArray[Any], header: Union[fits.Header, None] = None,
                     fmt: str = '-b') -> str:
        if header is not None and 'CRVAL1' in header:
            lambda_step = float(header['CDELT1'])
            lambda_ref = float(header['CRVAL1']) + (float(header['CRPIX1']) - 1) * lambda_step
            xdata = np.linspace(lambda_ref,
                                lambda_ref + (data.shape[0] - 1) * lambda_step,
                                data.shape[0])
            unit = u'\u00c5'
        else:
            xdata = np.arange(data.shape[0])
            unit = 'Pixels'
        self._axes.set_xlabel(unit)
        return self.add_markers(xdata, data, fmt=fmt, header=header)

    def add_markers(self, xdata: npt.NDArray[Any], ydata: npt.NDArray[any], fmt: str = 'or',
                    line_id: Union[None, str] = None, header: Union[None, fits.Header] = None):
        if not line_id:
            line_id = f'line{self._line_id:<d}'
            self._line_id += 1
        if line_id not in self._lines:
            line = self._axes.plot(xdata, ydata, fmt).pop()
        else:
            line = self._lines[line_id].line
            line.set_data(xdata, ydata)
        line_data = SpecData(line, ydata, header)
        self._lines[line_id] = line_data
        self._axes.autoscale()
        self._canvas.draw()
        self.Layout()
        data_max = np.max(ydata)
        if self._current_max is None or data_max > self._current_max:
            self._current_max = data_max

        return line_id

    def clear(self):
        for item in self._lines.items():
            item[1].line.remove()
        self._lines.clear()
        self._axes.clear()
        self._axes.relim()
        self._canvas.draw_idle()
        self._xdata = None
        self._current_max = None

    def set_spectrum_data(self, spec_id: str, data: npt.NDArray[Any]):
        if spec_id not in self._lines:
            raise ValueError(f'spectrum ID {spec_id} not found')
        if data.shape[0] != self._xdata.shape[0]:
            raise ValueError('wrong shape for spectrum data')
        line = self._lines[spec_id]
        line.set_ydata(data)
        self._canvas.draw()

    def toggle_event_handler(self, event_handler: Union[None, SpecEvtHandler]):
        if self._event_handler is not None:
            self._event_handler.dispose()
        self._event_handler = event_handler
        if self._event_handler is not None:
            if len(self._lines) == 1:
                self._event_handler.set_data(list(self._lines.values())[0])
            self._event_handler.init(self._fig, self._axes)

    def save_file(self):
        if isinstance(self._event_handler, SaveHandler):
            file_path = pick_save_file(self)
            self._event_handler.save_file(file_path)

    @property
    def current_max(self):
        return self._current_max


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
