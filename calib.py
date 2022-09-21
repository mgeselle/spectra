import math
import threading
from pathlib import Path
from typing import Sequence, Union, Any, Tuple, Callable

import astropy.units as u
import numpy as np
import numpy.ma as ma
import numpy.polynomial as poly
import numpy.typing as npt
import scipy.optimize as optimize
import scipy.signal as signal
import wx
import wx.grid as grid
import wx.lib.intctrl as wxli
import wx.lib.newevent as ne
from astropy.io import fits
from astroquery.nist import Nist

import util
import wxutil
from config import Config
from specview import Specview

ProgressEvent, EVT_ID_PROGRESS = ne.NewEvent()
ErrorEvent, EVT_ID_ERROR = ne.NewEvent()


class CalibConfigurator(wx.Dialog):

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.SetTitle('Calibration Configuration')

        panel = wx.Panel(self)
        ref_label = wx.StaticText(panel, wx.ID_ANY, 'Reference Spectra:')
        self._ref_entry = wx.TextCtrl(panel)
        wxutil.size_text_by_chars(self._ref_entry, 20)
        lambda_label = wx.StaticText(panel, wx.ID_ANY, u'\u03bb Range [\u00c5]:')
        self._lam_low = wxli.IntCtrl(panel, min=3000, max=8500)
        wxutil.size_text_by_chars(self._lam_low, 6)
        dash_label = wx.StaticText(panel, wx.ID_ANY, ' .. ')
        self._lam_high = wxli.IntCtrl(panel, min=3000, max=8500)
        wxutil.size_text_by_chars(self._lam_high, 6)
        lam_sizer = wx.BoxSizer(wx.HORIZONTAL)
        lam_sizer.Add(self._lam_low, 0, 0, 0)
        lam_sizer.Add(dash_label, 1, 0, 0)
        lam_sizer.Add(self._lam_high, 0, 0, 0)

        grid = wx.FlexGridSizer(rows=2, cols=2, vgap=5, hgap=5)
        grid.Add(ref_label, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self._ref_entry, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        grid.Add(lambda_label, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        grid.Add(lam_sizer, 0, wx.ALIGN_LEFT, wx.ALIGN_CENTER_VERTICAL)

        btn_sizer = self.CreateSeparatedButtonSizer(wx.OK | wx.CANCEL)

        vbox = wx.BoxSizer(wx.VERTICAL)
        vbox.Add(grid, 0, wx.ALL, border=10)
        vbox.Add(btn_sizer, 0, wx.ALL | wx.EXPAND, border=10)
        panel.SetSizer(vbox)
        panel.Fit()
        self.SetClientSize(panel.GetBestSize())

        self.Layout()
        sz = self.GetBestSize()
        self.SetSizeHints(sz.x, sz.y, sz.x, sz.y)

        used_lines = Config.get().get_used_lines()
        self._ref_entry.SetValue(used_lines)
        lam_low, lam_hi = Config.get().get_line_limits()
        self._lam_low.SetValue(lam_low)
        self._lam_high.SetValue(lam_hi)

        self.Bind(wx.EVT_BUTTON, self._on_btn)
        self.Bind(EVT_ID_PROGRESS, self._on_progress)
        self.Bind(EVT_ID_ERROR, self._on_error)

        self._progress = None
        self._error_msg = None
        # This is used for synchronising between the event handlers.
        # Apparently the there is some parallelism involved in handling events. This
        # wreaks havoc with when exactly to destroy child dialogs.
        self._event_ack = threading.Event()

    def _on_btn(self, event: wx.CommandEvent):
        if event.GetId() == wx.ID_CANCEL:
            if self.IsModal():
                self.EndModal(wx.CANCEL)
            else:
                self.Show(False)
            return

        ref_lines = [x.strip() for x in self._ref_entry.GetValue().split(',')]
        if not ref_lines:
            return
        present_lines = Config.get().get_calib_line_names()

        ref_missing = [x for x in ref_lines if x not in present_lines]

        lam_lower = self._lam_low.GetValue()
        lam_upper = self._lam_high.GetValue()
        if lam_lower >= lam_upper:
            return

        Config.get().set_line_limits(lam_lower, lam_upper)

        if not ref_missing:
            Config.get().set_used_lines(','.join(ref_lines))
            if self.IsModal():
                self.EndModal(wx.OK)
            else:
                self.Show(False)
            return

        self._progress = wx.ProgressDialog('Reference Spectrum Retrieval', parent=self, maximum=100,
                                           style=wx.PD_AUTO_HIDE, message='Retrieving missing reference spectra.')
        self._progress_showing = True
        self._progress.Bind(wx.EVT_SHOW, self._on_progress_close)

        retrieval_args = (ref_lines, ref_missing)
        thread = threading.Thread(target=self._retrieve_ref_spectra, args=retrieval_args)
        thread.start()

    def _retrieve_ref_spectra(self, full_list: Sequence[str], missing: Sequence[str]):
        self._event_ack.clear()
        step = int(100 / len(missing))
        completion = 0
        failed = []
        for species in missing:
            # noinspection PyBroadException
            event = ProgressEvent(completion=completion, msg=f'Retrieving reference spectrum for {species}.')
            self.QueueEvent(event)
            self._event_ack.wait()
            self._event_ack.clear()
            try:
                ref_spectrum = Nist.query(3000 * u.AA, 8500 * u.AA, linename=species, wavelength_type='vac+air')
            except Exception:
                failed.append(species)
            else:
                Config.get().save_calib_table(species, ref_spectrum)
            completion += step

        if failed:
            msg = f'Failed to retrieve: {", ".join(failed)}.'
        else:
            Config.get().set_used_lines(','.join(full_list))
            msg = ''
        event = ProgressEvent(completion=100, msg=msg)
        self.QueueEvent(event)

    def _on_progress(self, event: ProgressEvent):
        print(f'Entered _on_progress, completion = {event.completion}')
        completion = event.completion
        if completion == 100:
            self._error_msg = event.msg
        self._progress.Update(completion, event.msg)
        self._event_ack.set()
        print(f'Leaving _on_progress. Completion:{completion}, msg: {event.msg}')

    def _on_progress_close(self, event: wx.ShowEvent):
        if event.IsShown():
            return
        self._progress.Destroy()
        self._progress = None
        if not self._error_msg:
            if self.IsModal():
                self.EndModal(wx.OK)
            else:
                self.Show(False)
        else:
            self._event_ack.clear()
            self.QueueEvent(ErrorEvent())
            self._event_ack.set()

        print('Leaving _on_close')

    # noinspection PyUnusedLocal
    def _on_error(self, event: ErrorEvent):
        self._event_ack.wait()
        with wx.MessageDialog(self, self._error_msg, caption='Retrieval Errors',
                              style=wx.OK | wx.CENTRE | wx.ICON_ERROR) as dlg:
            dlg.ShowModal()


class CalibFileDialog(wx.Dialog):
    def __init__(self, parent: wx.Window, **kwargs):
        super().__init__(parent, **kwargs)
        self.SetTitle("Calibration Files")

        panel = wx.Panel(self)

        text_chars = 40
        in_dir_label = wx.StaticText(panel, wx.ID_ANY, 'Input Directory:')
        self._in_dir_text = wx.TextCtrl(panel)
        wxutil.size_text_by_chars(self._in_dir_text, text_chars)
        folder_bmp = wx.ArtProvider.GetBitmap(wx.ART_FOLDER_OPEN, wx.ART_BUTTON)
        self._in_dir_btn_id = wx.NewIdRef()
        in_dir_btn = wx.BitmapButton(panel, id=self._in_dir_btn_id.GetId(), bitmap=folder_bmp)
        in_dir_sizer = wx.BoxSizer(wx.HORIZONTAL)
        in_dir_sizer.Add(self._in_dir_text, 1, wx.EXPAND | wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT)
        in_dir_sizer.Add(in_dir_btn, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT)

        calib_label = wx.StaticText(panel, wx.ID_ANY, 'Calibration Spectrum:')
        self._calib_combo = wx.ComboBox(panel, style=wx.CB_READONLY | wx.CB_SORT)
        wxutil.size_text_by_chars(self._calib_combo, text_chars)
        pgm_label = wx.StaticText(panel, wx.ID_ANY, 'Program Spectrum:')
        self._pgm_combo = wx.ComboBox(panel, style=wx.CB_READONLY | wx.CB_SORT)
        wxutil.size_text_by_chars(self._pgm_combo, text_chars)

        out_dir_label = wx.StaticText(panel, wx.ID_ANY, 'Output Directory:')
        self._out_dir_text = wx.TextCtrl(panel)
        wxutil.size_text_by_chars(self._out_dir_text, text_chars)
        self._out_dir_btn_id = wx.NewIdRef()
        out_dir_btn = wx.BitmapButton(panel, id=self._out_dir_btn_id.GetId(), bitmap=folder_bmp)
        out_dir_sizer = wx.BoxSizer(wx.HORIZONTAL)
        out_dir_sizer.Add(self._out_dir_text, 1, wx.EXPAND | wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT)
        out_dir_sizer.Add(out_dir_btn, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT)

        grid = wx.FlexGridSizer(rows=4, cols=2, vgap=5, hgap=5)
        grid.Add(in_dir_label, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        grid.Add(in_dir_sizer, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        grid.Add(calib_label, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self._calib_combo, 0, wx.ALIGN_LEFT, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(pgm_label, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self._pgm_combo, 0, wx.ALIGN_LEFT, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(out_dir_label, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        grid.Add(out_dir_sizer, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)

        btn_sizer = self.CreateSeparatedButtonSizer(wx.OK | wx.CANCEL)

        vbox = wx.BoxSizer(wx.VERTICAL)
        vbox.Add(grid, 0, wx.ALL, border=10)
        vbox.Add(btn_sizer, 0, wx.ALL | wx.EXPAND, border=10)
        panel.SetSizer(vbox)
        panel.Fit()
        self.SetClientSize(panel.GetBestSize())

        self.Layout()
        sz = self.GetBestSize()
        self.SetSizeHints(sz.x, sz.y, sz.x, sz.y)

        self.Bind(wx.EVT_BUTTON, self._on_ok_cancel, id=wx.ID_CANCEL)
        self.Bind(wx.EVT_BUTTON, self._on_ok_cancel, id=wx.ID_OK)
        self.Bind(wx.EVT_BUTTON, self._on_dir_btn, id=self._in_dir_btn_id.GetId())
        self.Bind(wx.EVT_BUTTON, self._on_dir_btn, id=self._out_dir_btn_id.GetId())
        self.Bind(wx.EVT_TEXT, self._find_spectra, source=self._in_dir_text)

        self._calib_file = None
        self._pgm_file = None
        self._output_dir = None

    # noinspection PyUnusedLocal
    def _find_spectra(self, event: wx.Event):
        input_dir = self._in_dir_text.GetValue().strip()
        input_path = None
        if input_dir:
            input_path = util.dir_to_path(input_dir)
        if not input_dir or not input_path.is_dir():
            self._calib_combo.SetItems([''])
            self._calib_combo.SetValue('')
            self._calib_combo.SetItems([])
            self._pgm_combo.SetItems([''])
            self._pgm_combo.SetValue('')
            self._pgm_combo.SetItems([])
            return
        items = []
        for candidate in input_path.iterdir():
            if not candidate.is_file() or candidate.suffix not in ('.fits', '.fit'):
                continue
            in_hdu_l = fits.open(candidate)
            data = in_hdu_l[0].data
            if len(data.shape) == 1:
                items.append(candidate.name)
            in_hdu_l.close()
        self._calib_combo.SetItems([''])
        self._calib_combo.SetValue('')
        self._calib_combo.SetItems(items)
        self._pgm_combo.SetItems([''])
        self._pgm_combo.SetValue('')
        self._pgm_combo.SetItems(items)

    def _on_dir_btn(self, event: wx.CommandEvent):
        if event.GetId() == self._in_dir_btn_id:
            last_dir = self._in_dir_text.GetValue()
        else:
            last_dir = self._out_dir_text.GetValue()
        last_dir = last_dir.strip()
        sel_dir = wxutil.select_dir(self, event.GetId() == self._in_dir_btn_id.GetId())
        if not sel_dir or last_dir == sel_dir:
            return
        if event.GetId() == self._in_dir_btn_id:
            self._in_dir_text.SetValue(sel_dir)
        else:
            self._out_dir_text.SetValue(sel_dir)

    def _on_ok_cancel(self, event: wx.CommandEvent):
        if event.GetId() == wx.ID_CANCEL:
            self._calib_file = None
            self._pgm_file = None
            self._output_dir = None
            if self.IsModal():
                self.EndModal(wx.CANCEL)
            else:
                self.Show(False)
            return

        input_dir = self._in_dir_text.GetValue().strip()
        if not input_dir:
            return
        input_path = util.dir_to_path(input_dir)
        if not input_path.is_dir():
            return
        calib_name = self._calib_combo.GetValue().strip()
        if not calib_name:
            return

        output_dir = self._out_dir_text.GetValue()
        if not output_dir:
            return
        output_path = util.dir_to_path(output_dir)
        try:
            output_path.mkdir(parents=True, exist_ok=True)
        except PermissionError as err:
            with wx.MessageDialog(self, f'Cannot create output dir: {err}.', caption='Error',
                                  style=wx.OK | wx.ICON_ERROR) as dlg:
                dlg.ShowModal()
            return

        self._calib_file = input_path / calib_name
        pgm_name = self._pgm_combo.GetValue().strip()
        if pgm_name:
            self._pgm_file = input_path / pgm_name
        self._output_dir = output_path
        self.Show(False)

    @property
    def calib_file(self) -> Union[Path, None]:
        return self._calib_file

    @property
    def pgm_file(self) -> Union[Path, None]:
        return self._pgm_file

    @property
    def output_dir(self) -> Union[Path, None]:
        return self._output_dir


def find_peaks(data: npt.NDArray[Any]) -> Union[Tuple[npt.NDArray[Any], Sequence[float]], None]:
    prominence = np.max(data) / 20
    peaks, props = signal.find_peaks(data, prominence=prominence, width=(2, 16))
    center_peak = None
    min_peak_dist = None
    for peak_no in range(0, peaks.shape[0]):
        peak_dist = abs(data.shape[0] / 2 - peaks[peak_no])
        if center_peak is None or peak_dist < min_peak_dist:
            center_peak = peak_no
            min_peak_dist = peak_dist

    _, fwhm = fit_peak(data, peaks[center_peak], props['widths'][center_peak])
    peaks, props = signal.find_peaks(data, width=(int(0.8 * fwhm), int(2 * fwhm)))
    prominence = np.max(data) / 50
    result = []
    fwhms = []
    for peak_no in range(0, peaks.shape[0]):
        if props['prominences'][peak_no] >= prominence:
            peak, fwhm = fit_peak(data, peaks[peak_no], props['widths'][peak_no])
            result.append(peak)
            fwhms.append(fwhm)
    return np.array(result), fwhms


def fit_peak(data: npt.NDArray[Any], peak, width):
    left_i = int(peak - round(width / 2))
    last_val = data[left_i]
    while left_i > 0 and data[left_i - 1] < last_val:
        left_i -= 1
        last_val = data[left_i]
    right_i = int(peak + round(width / 2))
    last_val = data[right_i]
    while right_i < data.shape[0] - 1 and data[right_i + 1] < last_val:
        right_i += 1
        last_val = data[right_i]

    xdata = np.array(range(left_i, right_i + 1))
    ydata = data[left_i:right_i + 1]

    def func(x, a, sig, cen, c):
        return a * np.exp(-0.5 * ((x - cen) / sig)**2) + c

    c_i = (data[left_i] + data[right_i]) / 2
    a_i = data[peak] - c_i
    factor = 2 * math.sqrt(2 * math.log(2))
    sig_i = width / (2 * factor)
    popt, _ = optimize.curve_fit(func, xdata, ydata, p0=(a_i, sig_i, peak, c_i))
    fwhm = abs(popt[1] * factor)
    return popt[2], fwhm


class CalibDialog(wx.Dialog):
    def __init__(self, parent: wx.Window, data: npt.NDArray[Any], peaks: npt.NDArray, **kwargs):
        super().__init__(parent, **kwargs)
        self.SetTitle('Calibration')

        self._grid = grid.Grid(self)
        table = grid.GridStringTable(peaks.shape[0], 2)
        table.SetColLabelValue(0, u'\u03bb [\u00c5]')
        table.SetColLabelValue(1, 'Residual')
        for peak_no in range(0, peaks.shape[0]):
            table.SetRowLabelValue(peak_no, f'{round(peaks[peak_no]):>5d}')
        self._grid.SetTable(table, True)
        degree_label = wx.StaticText(self, wx.ID_ANY, 'Degree:')
        self._degree = wx.SpinCtrl(self, min=1, max=1, initial=1)
        wxutil.size_text_by_chars(self._degree, 2)
        tick_bmp = wx.ArtProvider.GetBitmap(wx.ART_TICK_MARK, wx.ART_BUTTON)
        self._calc_btn = wx.BitmapButton(self, id=wx.ID_ANY, bitmap=tick_bmp)
        self._calc_btn.Disable()
        degree_box = wx.BoxSizer(wx.HORIZONTAL)
        degree_box.Add(degree_label, 1, wx.LEFT | wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL, 5)
        degree_box.Add(self._degree, 0, wx.ALIGN_LEFT | wx.LEFT, 5)
        degree_box.Add(self._calc_btn, 0, wx.ALIGN_LEFT | wx.RIGHT, 0)

        left_vbox = wx.BoxSizer(wx.VERTICAL)
        left_vbox.Add(self._grid, 1, wx.EXPAND, 0)
        left_vbox.Add(degree_box, 0, wx.TOP, 5)

        self._specview = Specview(self)
        display = wx.Display()
        display_sz = display.GetClientArea()
        width = int(0.6 * display_sz.GetWidth())
        height = int(0.6 * display_sz.GetHeight())
        self._specview.SetMinSize(wx.Size(width=width, height=height))
        hbox = wx.BoxSizer(wx.HORIZONTAL)
        hbox.Add(left_vbox, 0, wx.EXPAND, 0)
        hbox.Add(self._specview, 1, wx.EXPAND, 0)

        btn_sizer = self.CreateSeparatedButtonSizer(wx.OK | wx.CANCEL)

        vbox = wx.BoxSizer(wx.VERTICAL)
        vbox.Add(hbox, 1, wx.EXPAND, 0)
        vbox.Add(btn_sizer, 0, wx.EXPAND | wx.BOTTOM, 5)

        self.Bind(wx.EVT_BUTTON, self._on_btn)
        self._grid.Bind(grid.EVT_GRID_CELL_CHANGING, self._on_cell_changing)
        self._grid.Bind(grid.EVT_GRID_CELL_CHANGED, self._on_cell_changed)
        self._calc_btn.Bind(wx.EVT_BUTTON, self._on_calc_btn)

        lines = CalibDialog._load_lines()
        self._lambda_by_text = dict()
        choices_list = ['--']
        longest_text = '--'
        for line in lines:
            text = f'{line[0]:.2f} ({line[1]}) {line[2]}'
            choices_list.append(text)
            self._lambda_by_text[text] = line[0]
            if len(text) > len(longest_text):
                longest_text = text

        spec_xdata = np.arange(0, data.size)
        self._specview.add_markers(spec_xdata, data, fmt='-b')
        self._peaks = peaks
        self._lambda = np.zeros(peaks.shape[0])
        self._poly = None
        peak_y = np.empty(peaks.shape[0])
        for peak_no in range(0, peaks.shape[0]):
            peak_y[peak_no] = data[round(peaks[peak_no])]
            # While sharing cell editors is theoretically possible, doing so makes wx complain
            # about reference counts < 0 on shutdown. --> Create one for every cell.
            editor = grid.GridCellChoiceEditor(choices_list, False)
            self._grid.SetCellEditor(peak_no, 0, editor)
            self._grid.SetCellValue(peak_no, 0, choices_list[0])
        self._grid.SetCellValue(0, 0, longest_text)
        self._grid.AutoSizeColumn(0, True)
        self._grid.SetCellValue(0, 0, choices_list[0])
        self._markers = self._specview.add_markers(peaks, peak_y, fmt='vr')

        vbox.SetSizeHints(self)
        self.SetSizer(vbox)

    @property
    def poly(self):
        return self._poly

    def _on_btn(self, event: wx.CommandEvent):
        if event.GetId() == wx.ID_CANCEL:
            if self.IsModal():
                self.EndModal(wx.CANCEL)
            else:
                self.Show(False)
            return
        if self._poly is None:
            return
        if self.IsModal():
            self.EndModal(wx.OK)
        else:
            self.Show(False)

    @staticmethod
    def _load_lines() -> Sequence[Tuple[float, int, str]]:
        limit_low, limit_high = Config.get().get_line_limits()
        used_lines = Config.get().get_used_lines().split(',')
        result = []
        for line in used_lines:
            table = Config.get().get_calib_table(line)
            for wavelength, rel_int in table.iterrows('Observed', 'Rel.'):
                if wavelength is ma.masked or wavelength < limit_low:
                    continue
                if wavelength > limit_high:
                    break
                result.append((wavelength, rel_int, line))
        result.sort(key=lambda x: x[0])
        return result

    def _on_cell_changing(self, event: grid.GridEvent):
        text = event.GetString()
        if text == '--':
            return
        peak_no = event.GetRow()
        new_lambda = self._lambda_by_text[text]
        if peak_no > 0:
            for peak in range(peak_no - 1, -1, -1):
                if self._lambda[peak] != 0:
                    if self._lambda[peak] > new_lambda:
                        event.Veto()
                        return
                    break
        if peak_no < self._lambda.shape[0] - 1:
            for peak in range(peak_no + 1, self._lambda.shape[0]):
                if self._lambda[peak] != 0:
                    if self._lambda[peak] < new_lambda:
                        event.Veto()
                        return
                    break

    def _on_cell_changed(self, event: grid.GridEvent):
        peak = event.GetRow()
        text = self._grid.GetCellValue(row=peak, col=0)
        if text == '--':
            new_lambda = 0
        else:
            new_lambda = self._lambda_by_text[text]
        self._lambda[peak] = new_lambda
        num_nonzero = len(np.nonzero(self._lambda)[0])
        if num_nonzero > 2:
            self._calc_btn.Enable()
            max_degree = num_nonzero - 2
            if max_degree > 4:
                max_degree = 4
            self._degree.SetMax(max_degree)
        else:
            self._calc_btn.Disable()
            self._degree.SetMax(1)
        if self._degree.GetMax() < self._degree.GetValue():
            self._degree.SetValue(self._degree.GetMax())

    # noinspection PyUnusedLocal
    def _on_calc_btn(self, event: wx.CommandEvent):
        nonzero = np.nonzero(self._lambda)[0]
        xdata = np.empty(len(nonzero))
        ydata = np.empty(len(nonzero))
        for i in range(0, len(nonzero)):
            xdata[i] = self._peaks[nonzero[i]]
            ydata[i] = self._lambda[nonzero[i]]
        degree = self._degree.GetValue()
        # noinspection PyTypeChecker
        self._poly: Callable[[npt.NDArray[Any]], npt.NDArray[Any]] = poly.Polynomial.fit(xdata, ydata, degree)
        residual = np.abs(ydata - self._poly(xdata))
        for i in range(0, len(nonzero)):
            self._grid.SetCellValue(nonzero[i], 1, f'{residual[i]:.3f}')


def apply_calibration(input_path: Path, calib: Callable[[npt.NDArray], npt.NDArray], output_path: Path,
                      resolution: Union[float, None]):
    with fits.open(input_path) as in_hdu_l:
        header = in_hdu_l[0].header
        data = in_hdu_l[0].data

    in_wl = calib(np.arange(0, data.shape[0]))
    out_wl = in_wl[0]
    wl_step = (in_wl[-1] - in_wl[0]) / (data.shape[0] - 1)
    out_data = np.empty(data.shape[0])
    orig_i = 0
    for i in range(0, data.shape[0]):
        if i == 0 or i == data.shape[0] - 1:
            out_data[i] = data[i]
            out_wl += wl_step
            continue
        while out_wl > in_wl[orig_i + 1]:
            orig_i += 1
        slope = (data[orig_i + 1] - data[orig_i]) / (in_wl[orig_i + 1] - in_wl[orig_i])
        out_data[i] = data[orig_i] + slope * (out_wl - in_wl[orig_i])
        out_wl += wl_step

    header['CRPIX1'] = 1.0
    header['CRVAL1'] = in_wl[0]
    header['CDELT1'] = wl_step
    header['CTYPE1'] = 'Wavelength'
    header['CUNIT1'] = 'Angstrom'
    if resolution:
        header['AAV_ITRP'] = int(resolution)

    out_hdu = fits.PrimaryHDU(data=out_data, header=header)
    out_hdu.writeto(output_path / input_path.name, overwrite=True)


if __name__ == '__main__':
    app = wx.App()
    app.SetAppName('spectra')
    frame = wx.Frame(None, title='Calibration Test')
    pnl = wx.Panel(frame)
    cfg_button = wx.Button(pnl, id=wx.ID_ANY, label='Run Config')
    sel_button = wx.Button(pnl, id=wx.ID_ANY, label='Run Select')
    sizer = wx.BoxSizer(wx.VERTICAL)
    sizer.Add(cfg_button, 0, 0, 0)
    sizer.Add(sel_button, 0, 0, 0)
    pnl.SetSizer(sizer)
    pnl.Fit()
    pnl_sz = pnl.GetBestSize()
    frame.SetClientSize(pnl_sz)

    def show_calib_dialog(calib_file: Path, pgm_file: Path, output_path: Path, calib_btn: wx.Button):
        with fits.open(calib_file) as in_hdu_l:
            data = in_hdu_l[0].data
        peaks, _ = find_peaks(data)
        calib_dlg = CalibDialog(frame, data, peaks, style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)

        def on_calib_show(evt: wx.ShowEvent):
            if evt.IsShown():
                return
            l_poly = calib_dlg.poly
            calib_dlg.Destroy()
            if poly is not None:
                apply_calibration(calib_file, l_poly, output_path, None)
                if pgm_file is not None:
                    apply_calibration(pgm_file, l_poly, output_path, None)
            calib_btn.Enable()

        calib_dlg.Bind(wx.EVT_SHOW, on_calib_show)
        calib_dlg.Show()


    def on_btn(event: wx.CommandEvent):
        btn = event.GetEventObject()
        btn.Disable()
        if btn == cfg_button:
            dlg = CalibConfigurator(frame)
        elif btn == sel_button:
            dlg = CalibFileDialog(frame)
        else:
            return

        def on_dlg_show(evt: wx.ShowEvent):
            if evt.IsShown():
                return
            calib_file = None
            pgm_file = None
            output_path = None
            if isinstance(dlg, CalibFileDialog):
                calib_file = dlg.calib_file
                pgm_file = dlg.pgm_file
                output_path = dlg.output_dir
            dlg.Destroy()

            if calib_file:
                show_calib_dialog(calib_file, pgm_file, output_path, btn)
            else:
                btn.Enable()

        dlg.Bind(wx.EVT_SHOW, on_dlg_show)
        dlg.Show()

    frame.Bind(wx.EVT_BUTTON, on_btn)
    frame.Show()
    app.MainLoop()
