from dataclasses import dataclass
import math
import re
import threading
from pathlib import Path
from typing import Sequence, Union, Any, Tuple, Callable, List

import astropy.units as u
import numpy as np
import numpy.ma as ma
import numpy.polynomial as poly
import numpy.typing as npt
import scipy.optimize as optimize
import scipy.signal as signal
import specview as spv
import wx
import wx.grid as grid
import wx.lib.intctrl as wxli
import wx.lib.newevent as ne
from astropy.io import fits
from astroquery.nist import Nist
from matplotlib.axes import Axes
from matplotlib.backend_bases import MouseEvent, KeyEvent
from matplotlib.figure import Figure
from numpy.ma.core import MaskError

import util
import wxutil
from config import Config


ProgressEvent, EVT_ID_PROGRESS = ne.NewEvent()
ErrorEvent, EVT_ID_ERROR = ne.NewEvent()
NumValidChgEvent, EVT_ID_NUM_VALID_CHG = ne.NewEvent()


@dataclass
class SpecEntry:
    pixel: int
    wave_len: Union[float, None] = None


class SpecSelector(spv.SpecEvtHandler):
    def __init__(self, table: grid.GridStringTable, parent: wx.EvtHandler):
        super().__init__()
        self._table = table
        self._parent = parent
        self._mouse_cid = None
        self._key_cid = None
        self._entries = []
        self._entry_line = None
        self._selected_line = None
        self._selected_entry = None

        used_lines = Config.get().get_used_lines().split(',')
        self._absorption = len(used_lines) == 1 and used_lines[0] == 'H2O'
        lines = SpecSelector._load_lines()
        self._lambda_by_text = dict()
        self._index_by_lambda = dict()
        self._choices_list = ['--']
        self._longest_text = '--'
        index = 1
        for line in lines:
            text = f'{line[0]:.2f} ({line[1]}) {line[2]}'
            self._choices_list.append(text)
            self._lambda_by_text[text] = line[0]
            self._index_by_lambda[line[0]] = index
            index += 1
            if len(text) > len(self._longest_text):
                self._longest_text = text

    def init(self, figure: Figure, axes: Axes):
        super().init(figure, axes)
        self._mouse_cid = self._figure.canvas.mpl_connect('button_press_event', self._on_click)
        self._key_cid = self._figure.canvas.mpl_connect('key_press_event', self._on_key)

    def dispose(self):
        self._figure.canvas.mpl_disconnect(self._mouse_cid)
        self._figure.canvas.mpl_disconnect(self._key_cid)

    def set_wavelength(self, row: int, wavelength: Union[float, None]):
        self._entries[row].wave_len = wavelength

    def get_wavelength(self, row: int) -> Union[float, None]:
        if len(self._entries) < row + 1:
            return None
        return self._entries[row].wave_len

    def entries(self):
        return self._entries

    def num_valid(self) -> int:
        return len([x for x in self._entries if x.wave_len is not None])

    def longest_text(self) -> str:
        return self._longest_text

    def dispersion(self, calib: Callable[[npt.NDArray], npt.NDArray]):
        ydata = self._data.data
        wave_len = calib(np.arange(0, ydata.shape[0]))
        return (wave_len[ydata.shape[0] - 1] - wave_len[0]) / (ydata.shape[0] - 1)

    def resolution(self, calib: Callable[[npt.NDArray], npt.NDArray]):
        min_width = None
        for peak in [x.pixel for x in self._entries if x.wave_len is not None]:
            _, width = fit_peak(self._data.data, peak, self._absorption)
            if width is not None and (min_width is None or width < min_width):
                min_width = width
        if min_width is None:
            return None
        pixels = self._data.data.shape[0]
        centre_wave_len = calib(np.arange(pixels / 2, pixels / 2 + 1))[0]
        return centre_wave_len / (min_width * self.dispersion(calib))

    def _on_click(self, event: MouseEvent):
        prev_selected = None
        if self._selected_entry:
            self._selected_line.remove()
            self._selected_line = None
            prev_selected = self._selected_entry
            self._selected_entry = None

        min_dist = None
        min_entry = None
        for entry in self._entries:
            dist = abs(entry.pixel - event.xdata)
            if min_dist is None or dist < min_dist:
                min_dist = dist
                min_entry = entry
            elif min_dist is not None and dist > min_dist:
                break
        if min_dist is not None and min_dist < 10 and min_entry != prev_selected:
            self._selected_entry = min_entry
        elif min_dist is None or min_dist > 10:
            x_low = int(event.xdata - 10)
            x_hi = int(event.xdata + 10)
            if x_low < 0:
                x_low = 0
            if x_hi > self._data.data.shape[0] - 1:
                x_hi = self._data.data.shape[0] - 1
            data_min = np.min(self._data.data[x_low:x_hi])
            data_max = np.max(self._data.data[x_low:x_hi])
            prominence = (data_max - data_min) / 2
            if self._absorption:
                peak_data = -(self._data.data[x_low:x_hi] - data_max)
            else:
                peak_data = self._data.data[x_low:x_hi]
            peaks, props = signal.find_peaks(peak_data, distance=4, prominence=prominence)
            min_dist = None
            min_peak = None
            for peak in peaks:
                dist = abs(event.xdata - x_low - peak)
                if min_dist is None or dist < min_dist:
                    min_dist = dist
                    min_peak = peak
                elif min_dist is not None and dist > min_dist:
                    break
            if min_peak is not None:
                new_entry = SpecEntry(int(x_low + min_peak), None)
                entry_row = 0
                if len(self._entries) == 0:
                    self._entries.append(new_entry)
                    self._table.AppendRows(1)
                    self._configure_row(0, new_entry)
                elif self._entries[-1].pixel < new_entry.pixel:
                    entry_row = len(self._entries)
                    self._entries.append(new_entry)
                    self._table.AppendRows(1)
                    self._configure_row(len(self._entries) - 1, new_entry)
                else:
                    for i, entry in enumerate(self._entries):
                        entry_row = i
                        if entry.pixel > new_entry.pixel:
                            break
                    self._table.DeleteRows(entry_row, len(self._entries) - entry_row)
                    self._entries.insert(entry_row, new_entry)
                    self._table.AppendRows(len(self._entries) - entry_row)
                    for i, entry in enumerate(self._entries[entry_row:]):
                        self._configure_row(entry_row + i, entry)

                self._selected_entry = self._entries[entry_row]

        if len(self._entries) > 0:
            xdata = [x.pixel for x in self._entries]
            ydata = [self._data.data[x] for x in xdata]
            if self._entry_line is None:
                self._entry_line = self._axes.plot(xdata, ydata, '+r').pop()
            else:
                self._entry_line.set_data(xdata, ydata)

            if self._selected_entry is not None:
                xdata = [self._selected_entry.pixel]
                ydata = [self._data.data[self._selected_entry.pixel]]
                if self._selected_line is None:
                    self._selected_line = self._axes.plot(xdata, ydata, '+g').pop()

        self._figure.canvas.draw_idle()

    def _configure_row(self, row: int, entry: SpecEntry, is_new=True):
        self._table.SetRowLabelValue(row, f'{entry.pixel}')
        gridview = self._table.View
        first_peak, first_choice = self._find_next_choice_up(row, None)
        last_peak, last_choice = self._find_last_choice_down(row, None)
        choices = ['--']
        choices.extend(self._choices_list[first_choice:last_choice])

        if is_new:
            editor = grid.GridCellChoiceEditor(choices)
            gridview.SetCellEditor(row, 0, editor)
        else:
            editor = gridview.GetCellEditor(row, 0)
            editor.SetParameters(','.join(choices))
            editor.DecRef()
        if entry.wave_len is None:
            gridview.SetCellValue(row, 0, self._choices_list[0])
        else:
            gridview.SetCellValue(row, 0, self._choices_list[self._index_by_lambda[entry.wave_len]])

    def _find_next_choice_up(self, peak, lambda_peak):
        if peak == 0:
            if lambda_peak is None:
                return 0, 1
            else:
                return None, None
        for i in range(peak - 1, -1, -1):
            wave_len = self.get_wavelength(i)
            if wave_len is not None:
                return i + 1, self._index_by_lambda[wave_len] + 1
        return 0, 1

    def _find_last_choice_down(self, peak, lambda_peak):
        num_entries = len(self._entries)
        if peak == num_entries - 1:
            if lambda_peak is None:
                return peak + 1, len(self._choices_list)
            else:
                return None, None
        for i in range(peak + 1, num_entries):
            wave_len = self.get_wavelength(i)
            if wave_len is not None:
                return i, self._index_by_lambda[wave_len]
        return num_entries, len(self._choices_list)

    def on_cell_changing(self, event: grid.GridEvent):
        text = event.GetString()
        peak_no = event.GetRow()
        gridview = self._table.View
        if text == '--':
            first_peak, first_choice = self._find_next_choice_up(peak_no, None)
            last_peak, last_choice = self._find_last_choice_down(peak_no, None)
            choices = ['--']
            choices.extend(self._choices_list[first_choice:last_choice])
            joined_choices = ','.join(choices)
            for row in range(first_peak, last_peak):
                editor = gridview.GetCellEditor(row, 0)
                editor.SetParameters(joined_choices)
                # Getting the editor increases its ref count
                editor.DecRef()
            return
        new_lambda = self._lambda_by_text[text]
        first_peak, first_choice = self._find_next_choice_up(peak_no, new_lambda)
        if first_peak is not None and first_peak != peak_no:
            choices = ['--']
            choices.extend(self._choices_list[first_choice:self._index_by_lambda[new_lambda]])
            joined_choices = ','.join(choices)
            for row in range(first_peak, peak_no):
                editor = gridview.GetCellEditor(row, 0)
                editor.SetParameters(joined_choices)
                editor.DecRef()

        last_peak, last_choice = self._find_last_choice_down(peak_no, new_lambda)
        if last_peak is not None:
            choices = ['--']
            choices.extend(self._choices_list[self._index_by_lambda[new_lambda]:last_choice])
            joined_choices = ','.join(choices)
            for row in range(peak_no + 1, last_peak):
                editor = gridview.GetCellEditor(row, 0)
                editor.SetParameters(joined_choices)
                editor.DecRef()

        if peak_no > 0:
            for peak in range(peak_no - 1, -1, -1):
                wave_len = self.get_wavelength(peak)
                if wave_len is not None:
                    if wave_len > new_lambda:
                        event.Veto()
                        return
                    break
        num_entries = len(self._entries)
        if peak_no < num_entries - 1:
            for peak in range(peak_no + 1, num_entries):
                wave_len = self.get_wavelength(peak)
                if wave_len is not None:
                    if wave_len < new_lambda:
                        event.Veto()
                        return
                    break

    def on_cell_changed(self, event: grid.GridEvent):
        peak = event.GetRow()
        text = self._table.GetValue(row=peak, col=0)
        if text == '--':
            new_lambda = None
        else:
            new_lambda = self._lambda_by_text[text]
        self.set_wavelength(peak, new_lambda)

    def _on_key(self, event: KeyEvent):
        if self._selected_entry is None or (event.key not in ('delete', 'backspace')):
            return
        deleted_row = 0
        for i, entry in enumerate(self._entries):
            deleted_row = i
            if entry == self._selected_entry:
                break
        num_valid_before = self.num_valid()
        # GridStringTable only supports deleting the last n rows (As of wxpython 4.2.1).
        # Remove all from deleted one to end and add survivors.
        num_rows = len(self._entries) - deleted_row
        self._entries.pop(deleted_row)
        num_valid_after = self.num_valid()
        self._table.DeleteRows(deleted_row, num_rows)
        if num_rows > 1:
            self._table.AppendRows(num_rows - 1)
            for row in range(deleted_row, len(self._entries)):
                self._configure_row(row, self._entries[row])
        self._selected_entry = None
        self._selected_line.remove()
        self._selected_line = None
        self._figure.canvas.draw_idle()
        xdata = [x.pixel for x in self._entries]
        ydata = [self._data.data[x] for x in xdata]
        self._entry_line.set_data(xdata, ydata)

        if num_valid_after != num_valid_before:
            self._parent.QueueEvent(NumValidChgEvent())
        if len(self._entries) == 0:
            return

        for row, entry in enumerate(self._entries):
            self._configure_row(row, entry, False)

    # noinspection PyUnusedLocal
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
                try:
                    rel_i_m = re.match(r'\d+', str(rel_int))
                    if not rel_i_m:
                        continue
                    rel_int = int(rel_i_m.group(0))
                except ValueError:
                    continue
                except MaskError:
                    continue
                result.append((wavelength, rel_int, line))
        result.sort(key=lambda x: x[1], reverse=True)
        result = result[0:200]
        result.sort(key=lambda x: x[0])
        return result


class CalibConfigurator(wx.Dialog):

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.SetTitle('Calibration Configuration')

        ref_label = wx.StaticText(self, wx.ID_ANY, 'Reference Spectra:')
        self._ref_entry = wx.TextCtrl(self)
        wxutil.size_text_by_chars(self._ref_entry, 20)
        lambda_label = wx.StaticText(self, wx.ID_ANY, u'\u03bb Range [\u00c5]:')
        self._lam_low = wxli.IntCtrl(self, min=3000, max=9200)
        wxutil.size_text_by_chars(self._lam_low, 6)
        dash_label = wx.StaticText(self, wx.ID_ANY, ' .. ')
        self._lam_high = wxli.IntCtrl(self, min=3000, max=9200)
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

        self.SetSizer(vbox)
        self.Fit()
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
                ref_spectrum = Nist.query(3000 * u.AA, 9200 * u.AA, linename=species, wavelength_type='vac+air')
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

        text_chars = 40
        in_dir_label = wx.StaticText(self, wx.ID_ANY, 'Input Directory:')
        self._in_dir_text = wx.TextCtrl(self)
        wxutil.size_text_by_chars(self._in_dir_text, text_chars)
        folder_bmp = wx.ArtProvider.GetBitmap(wx.ART_FOLDER_OPEN, wx.ART_BUTTON)
        self._in_dir_btn_id = wx.NewIdRef()
        in_dir_btn = wx.BitmapButton(self, id=self._in_dir_btn_id.GetId(), bitmap=folder_bmp)
        in_dir_sizer = wx.BoxSizer(wx.HORIZONTAL)
        in_dir_sizer.Add(self._in_dir_text, 1, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT)
        in_dir_sizer.Add(in_dir_btn, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT)

        calib_label = wx.StaticText(self, wx.ID_ANY, 'Calibration Spectrum:')
        self._calib_combo = wx.ComboBox(self, style=wx.CB_READONLY | wx.CB_SORT)
        wxutil.size_text_by_chars(self._calib_combo, text_chars)
        pgm_label = wx.StaticText(self, wx.ID_ANY, 'Program Spectrum:')
        self._pgm_combo = wx.ComboBox(self, style=wx.CB_READONLY | wx.CB_SORT)
        wxutil.size_text_by_chars(self._pgm_combo, text_chars)
        flat_label = wx.StaticText(self, wx.ID_ANY, 'Flat Spectrum:')
        self._flat_combo = wx.ComboBox(self, style=wx.CB_READONLY | wx.CB_SORT)
        wxutil.size_text_by_chars(self._flat_combo, text_chars)

        out_dir_label = wx.StaticText(self, wx.ID_ANY, 'Output Directory:')
        self._out_dir_text = wx.TextCtrl(self)
        wxutil.size_text_by_chars(self._out_dir_text, text_chars)
        self._out_dir_btn_id = wx.NewIdRef()
        out_dir_btn = wx.BitmapButton(self, id=self._out_dir_btn_id.GetId(), bitmap=folder_bmp)
        out_dir_sizer = wx.BoxSizer(wx.HORIZONTAL)
        out_dir_sizer.Add(self._out_dir_text, 1, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT)
        out_dir_sizer.Add(out_dir_btn, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT)

        grid = wx.FlexGridSizer(rows=5, cols=2, vgap=5, hgap=5)
        grid.Add(in_dir_label, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        grid.Add(in_dir_sizer, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        grid.Add(calib_label, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self._calib_combo, 0, wx.ALIGN_LEFT, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(pgm_label, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self._pgm_combo, 0, wx.ALIGN_LEFT, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(flat_label, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self._flat_combo, 0, wx.ALIGN_LEFT, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(out_dir_label, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        grid.Add(out_dir_sizer, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)

        btn_sizer = self.CreateSeparatedButtonSizer(wx.OK | wx.CANCEL)

        vbox = wx.BoxSizer(wx.VERTICAL)
        vbox.Add(grid, 0, wx.ALL, border=10)
        vbox.Add(btn_sizer, 0, wx.ALL | wx.EXPAND, border=10)
        self.SetSizer(vbox)

        self.Fit()
        sz = self.GetBestSize()
        self.SetSizeHints(sz.x, sz.y, sz.x, sz.y)

        self.Bind(wx.EVT_BUTTON, self._on_ok_cancel, id=wx.ID_CANCEL)
        self.Bind(wx.EVT_BUTTON, self._on_ok_cancel, id=wx.ID_OK)
        self.Bind(wx.EVT_BUTTON, self._on_dir_btn, id=self._in_dir_btn_id.GetId())
        self.Bind(wx.EVT_BUTTON, self._on_dir_btn, id=self._out_dir_btn_id.GetId())
        self.Bind(wx.EVT_TEXT, self._find_spectra, source=self._in_dir_text)

        self._calib_file = None
        self._pgm_file = None
        self._flat_file = None
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
            self._flat_combo.SetItems([''])
            self._flat_combo.SetValue('')
            self._flat_combo.SetItems([])
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
        self._flat_combo.SetItems([''])
        self._flat_combo.SetValue('')
        self._flat_combo.SetItems(items)

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
            self._flat_file = None
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

        if not calib_name:
            self._calib_file = None
        else:
            self._calib_file = input_path / calib_name
        pgm_name = self._pgm_combo.GetValue().strip()
        if pgm_name:
            self._pgm_file = input_path / pgm_name
        flat_name = self._flat_combo.GetValue().strip()
        if flat_name:
            self._flat_file = input_path / flat_name
        self._output_dir = output_path
        self.Show(False)

    @property
    def calib_file(self) -> Union[Path, None]:
        return self._calib_file

    @property
    def pgm_file(self) -> Union[Path, None]:
        return self._pgm_file

    @property
    def flat_file(self) -> Union[Path, None]:
        return self._flat_file

    @property
    def output_dir(self) -> Union[Path, None]:
        return self._output_dir


def find_peaks(data: npt.NDArray[Any]) -> Union[Tuple[npt.NDArray[Any], Sequence[float]], None]:
    prominence = np.max(data) / 20
    max_width = 16
    peaks, props = signal.find_peaks(data, prominence=prominence, width=(max_width / 4, max_width))
    while peaks.shape[0] < 4 and max_width < data.shape[1] / 10:
        max_width = max_width + 4
        peaks, props = signal.find_peaks(data, prominence=prominence, width=(max_width / 4, max_width))
    center_peak = None
    min_peak_dist = None
    for peak_no in range(0, peaks.shape[0]):
        peak_dist = abs(data.shape[0] / 2 - peaks[peak_no])
        if center_peak is None or peak_dist < min_peak_dist:
            center_peak = peak_no
            min_peak_dist = peak_dist

    _, fwhm = fit_peak(data, peaks[center_peak], props['widths'][center_peak])
    peaks, props = signal.find_peaks(data, width=(int(0.8 * fwhm), int(2 * fwhm)))
    prominence = np.max(data) / 100
    result = []
    fwhms = []
    for peak_no in range(0, peaks.shape[0]):
        if props['prominences'][peak_no] >= prominence:
            peak, fwhm = fit_peak(data, peaks[peak_no], props['widths'][peak_no])
            result.append(peak)
            fwhms.append(fwhm)
    return np.array(result), fwhms


def fit_peak(data: npt.NDArray[Any], peak: int, absorption: bool):
    left_i = peak - 10
    if left_i < 0:
        left_i = 0
    right_i = left_i + 20
    if right_i > data.shape[0]:
        right_i = data.shape[0]
        left_i = right_i - 20
    xdata = np.array(range(left_i, right_i))
    ydata = data[left_i:right_i]

    def func(x, a, sig, cen, c):
        return a * np.exp(-0.5 * ((x - cen) / sig)**2) + c

    if absorption:
        c_i = np.max(ydata)
    else:
        c_i =  np.min(ydata)
    a_i = data[peak] - c_i
    factor = 2 * math.sqrt(2 * math.log(2))
    sig_i = 4 / (2 * factor)
    try:
        popt, _ = optimize.curve_fit(func, xdata, ydata, p0=(a_i, sig_i, peak, c_i))
        fwhm = abs(popt[1] * factor)
        return popt[2], fwhm
    except RuntimeError:
        return None


class CalibDialog(wx.Dialog):
    def __init__(self, parent: wx.Window, data: npt.NDArray[Any], **kwargs):
        super().__init__(parent, **kwargs)
        self.SetTitle('Calibration')

        self._grid = grid.Grid(self)
        table = grid.GridStringTable(0, 2)
        table.SetColLabelValue(0, u'\u03bb [\u00c5]')
        table.SetColLabelValue(1, 'Residual')
        self._grid.SetTable(table, True)
        self._selector = SpecSelector(table, self)

        dc = wx.ClientDC(self)
        dc.SetFont(self._grid.GetDefaultCellFont())
        col_width, _ = dc.GetTextExtent(self._selector.longest_text())
        self._grid.SetColMinimalWidth(0, col_width)
        self._grid.SetColSize(0, col_width)
        degree_label = wx.StaticText(self, wx.ID_ANY, 'Degree:')
        self._degree = wx.SpinCtrl(self, min=1, max=1, initial=1)
        wxutil.size_text_by_chars(self._degree, 2)
        tick_bmp = wx.ArtProvider.GetBitmap(wx.ART_TICK_MARK, wx.ART_BUTTON)
        self._calc_btn = wx.BitmapButton(self, id=wx.ID_ANY, bitmap=tick_bmp)
        self._calc_btn.Disable()
        dispersion_label = wx.StaticText(self, wx.ID_ANY, 'Dispersion [\u00c5 / px]:')
        self._dispersion = wx.StaticText(self, wx.ID_ANY, '        ')
        dc.SetFont(self._dispersion.GetFont())
        disp_width, disp_height = dc.GetTextExtent('0000000')
        self._dispersion.SetMinSize(wx.Size(disp_width, disp_height))
        resolution_label = wx.StaticText(self, wx.ID_ANY, 'Resolution:')
        self._resolution_txt = wx.StaticText(self, wx.ID_ANY, '        ')
        dispersion_box = wx.BoxSizer(wx.HORIZONTAL)
        degree_box = wx.BoxSizer(wx.HORIZONTAL)
        degree_box.Add(degree_label, 1, wx.LEFT | wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL, 5)
        degree_box.Add(self._degree, 0, wx.ALIGN_LEFT | wx.LEFT, 5)
        degree_box.Add(self._calc_btn, 0, wx.ALIGN_LEFT | wx.RIGHT, 0)
        dispersion_box.Add(dispersion_label, 0, wx.LEFT | wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT, 5)
        dispersion_box.Add(self._dispersion, 1, wx.ALIGN_LEFT | wx.LEFT, 10)
        dispersion_box.Add(resolution_label, 0, wx.LEFT | wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT, 10)
        dispersion_box.Add(self._resolution_txt, 1, wx.ALIGN_LEFT | wx.LEFT, 10)

        left_vbox = wx.BoxSizer(wx.VERTICAL)
        left_vbox.Add(self._grid, 1, wx.EXPAND, 0)
        left_vbox.Add(dispersion_box, 0, wx.TOP, 5)
        left_vbox.Add(degree_box, 0, wx.TOP, 5)

        self._specview = spv.Specview(self)
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
        self.Bind(EVT_ID_NUM_VALID_CHG, self._num_valid_changed)
        self._grid.Bind(grid.EVT_GRID_CELL_CHANGING, self._selector.on_cell_changing)
        self._grid.Bind(grid.EVT_GRID_CELL_CHANGED, self._on_cell_changed)
        self._calc_btn.Bind(wx.EVT_BUTTON, self._on_calc_btn)

        spec_xdata = np.arange(0, data.size)
        self._specview.add_markers(spec_xdata, data, fmt='-b')
        self._poly = None
        self._resolution = None

        self._specview.toggle_event_handler(self._selector)

        vbox.SetSizeHints(self)
        self.SetSizer(vbox)
        vbox_best_sz = self.GetBestSize()
        if vbox_best_sz.GetHeight() > 0.8 * display_sz.GetHeight():
            vbox_best_sz = wx.Size(vbox_best_sz.GetWidth(), int(0.8 * display_sz.GetHeight()))
        self.SetSizeHints(vbox_best_sz)
        self.SetInitialSize(vbox_best_sz)

    @property
    def poly(self):
        return self._poly

    @property
    def resolution(self):
        return self._resolution

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

    def _on_calc_btn(self, event: wx.CommandEvent):
        valid_entries = [x for x in self._selector.entries() if x.wave_len is not None]
        num_valid = self._selector.num_valid()
        xdata = np.empty(num_valid)
        ydata = np.empty(num_valid)
        for i, entry in enumerate(valid_entries):
            xdata[i] = entry.pixel
            ydata[i] = entry.wave_len
        degree = self._degree.GetValue()
        # noinspection PyTypeChecker
        self._poly: Callable[[npt.NDArray[Any]], npt.NDArray[Any]] = poly.Polynomial.fit(xdata, ydata, degree)
        residual = np.abs(ydata - self._poly(xdata))
        i = 0
        for row, entry in enumerate(self._selector.entries()):
            if entry.wave_len is not None:
                self._grid.SetCellValue(row, 1, f'{residual[i]:.3f}')
                i += 1
        dispersion = self._selector.dispersion(self._poly)
        self._dispersion.SetLabel(f'{dispersion:6.3f}')

        self._resolution = self._selector.resolution(self._poly)
        if self._resolution is not None:
            self._resolution_txt.SetLabel(f'{self._resolution:5.0f}')

    def _on_cell_changed(self, event: grid.GridEvent):
        self._selector.on_cell_changed(event)
        self._num_valid_changed(event)

    def _num_valid_changed(self, event: wx.Event):
        num_valid = self._selector.num_valid()
        if num_valid > 2:
            self._calc_btn.Enable()
            max_degree = num_valid - 2
            if max_degree > 4:
                max_degree = 4
            self._degree.SetMax(max_degree)
        else:
            self._calc_btn.Disable()
            self._degree.SetMax(1)
        if self._degree.GetMax() < self._degree.GetValue():
            self._degree.SetValue(self._degree.GetMax())


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
        calib_dlg = CalibDialog(frame, data, style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)

        def on_calib_show(evt: wx.ShowEvent):
            if evt.IsShown():
                return
            l_poly = calib_dlg.poly
            calib_dlg.Destroy()
            if l_poly is not None:
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
