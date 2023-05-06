from pathlib import Path
import tempfile
from dataclasses import dataclass
from typing import Union, Sequence, Dict, Tuple
import wx

import flat
from config import Config
from dark import Dark
from extract import optimal as ex_optimal
from extract import simple as ex_simple
from taskdialog import TaskDialog
from rotate import Rotate
from slant import Slant
import util
import wx.lib.intctrl as wxli
import wxutil


@dataclass
class ReduceParams:
    output_path: Path
    calib_file: Path
    cam_cfg_name: str
    header_overrides: Dict
    # Optional explicit limits for simple extraction without rotation
    limits: Union[None , Tuple[int, int]] = None
    # We might just want to look at a calibration spectrum -> the other files might not be specified
    bias_path: Union[None , Path] = None
    dark_files: Union[None , Sequence[Path]] = None
    flat_path: Union[None , Path] = None
    pgm_files: Union[None , Path , Sequence[Path]] = None


class Reduce(TaskDialog):
    _last_input_dir = None
    _last_master_dir = None
    _last_output_dir = None

    def __init__(self, parent: wx.Window, **kwargs):
        super().__init__(parent, **kwargs)
        self.SetTitle('Reduce Images')
        self.progress_title = 'Reducing...'

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

        master_dir_label = wx.StaticText(self, wx.ID_ANY, 'Master Directory:')
        self._master_dir_text = wx.TextCtrl(self)
        wxutil.size_text_by_chars(self._master_dir_text, text_chars)
        self._master_dir_btn_id = wx.NewIdRef()
        master_dir_btn = wx.BitmapButton(self, id=self._master_dir_btn_id.GetId(), bitmap=folder_bmp)
        master_dir_sizer = wx.BoxSizer(wx.HORIZONTAL)
        master_dir_sizer.Add(self._master_dir_text, 1, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT)
        master_dir_sizer.Add(master_dir_btn, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT)

        output_dir_label = wx.StaticText(self, wx.ID_ANY, 'Output Directory:')
        self._output_dir_text = wx.TextCtrl(self)
        wxutil.size_text_by_chars(self._output_dir_text, text_chars)
        self._output_dir_btn_id = wx.NewIdRef()
        output_dir_btn = wx.BitmapButton(self, id=self._output_dir_btn_id.GetId(), bitmap=folder_bmp)
        output_dir_sizer = wx.BoxSizer(wx.HORIZONTAL)
        output_dir_sizer.Add(self._output_dir_text, 1, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT)
        output_dir_sizer.Add(output_dir_btn, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT)

        bias_label = wx.StaticText(self, wx.ID_ANY, 'Bias Pattern:')
        self._bias_text = wx.TextCtrl(self)
        wxutil.size_text_by_chars(self._bias_text, text_chars)

        dark_label = wx.StaticText(self, wx.ID_ANY, 'Dark Pattern:')
        self._dark_text = wx.TextCtrl(self)
        wxutil.size_text_by_chars(self._dark_text, text_chars)

        flat_label = wx.StaticText(self, wx.ID_ANY, 'Flat Pattern:')
        self._flat_text = wx.TextCtrl(self)
        wxutil.size_text_by_chars(self._flat_text, text_chars)

        calib_label = wx.StaticText(self, wx.ID_ANY, 'Calibration Pattern:')
        self._calib_text = wx.TextCtrl(self)
        wxutil.size_text_by_chars(self._calib_text, text_chars)

        pgm_label = wx.StaticText(self, wx.ID_ANY, 'Program Pattern:')
        self._pgm_text = wx.TextCtrl(self)
        wxutil.size_text_by_chars(self._pgm_text, text_chars)

        limits_label = wx.StaticText(self, wx.ID_ANY, 'Y Limits:')
        self._y_lo_text = wxli.IntCtrl(self, min=0, allow_none=True, value=None)
        wxutil.size_text_by_chars(self._y_lo_text, 5)
        self._y_hi_text = wxli.IntCtrl(self, min=0, allow_none=True, value=None)
        wxutil.size_text_by_chars(self._y_hi_text, 5)
        limits_sizer = wx.BoxSizer(wx.HORIZONTAL)
        limits_sizer.Add(self._y_lo_text, 1, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT)
        limits_sizer.AddSpacer(10)
        limits_sizer.Add(self._y_hi_text, 1, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT)

        eq_cfg_label = wx.StaticText(self, wx.ID_ANY, 'Equipment Configuration:')
        config_values = ['']
        config_values[1:] = Config.get().get_aavso_config_names()
        self._eq_cfg_combo = wx.ComboBox(self, value=config_values[0], choices=config_values,
                                         style=wx.CB_DROPDOWN | wx.CB_READONLY | wx.CB_SORT)
        wxutil.size_text_by_chars(self._eq_cfg_combo, 30)

        loc_label = wx.StaticText(self, wx.ID_ANY, 'Location Name:')
        loc_values = ['']
        loc_values[1:] = Config.get().get_location_names()
        self._loc_combo = wx.ComboBox(self, value=loc_values[0], choices=loc_values,
                                      style=wx.CB_DROPDOWN | wx.CB_READONLY | wx.CB_SORT)
        wxutil.size_text_by_chars(self._loc_combo, 30)

        obj_label = wx.StaticText(self, wx.ID_ANY, 'Object:')
        self._obj_entry = wx.TextCtrl(self)
        wxutil.size_text_by_chars(self._obj_entry, text_chars)

        vbox = wx.BoxSizer(wx.VERTICAL)
        grid = wx.FlexGridSizer(rows=12, cols=2, hgap=5, vgap=5)
        grid.Add(in_dir_label, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        grid.Add(in_dir_sizer, 1, wx.ALIGN_LEFT)
        grid.Add(master_dir_label, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        grid.Add(master_dir_sizer, 1, wx.ALIGN_LEFT)
        grid.Add(output_dir_label, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        grid.Add(output_dir_sizer, 1, wx.ALIGN_LEFT)
        grid.Add(bias_label, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self._bias_text, 1, wx.ALIGN_LEFT)
        grid.Add(dark_label, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self._dark_text, 1, wx.ALIGN_LEFT)
        grid.Add(flat_label, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self._flat_text, 1, wx.ALIGN_LEFT)
        grid.Add(calib_label, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self._calib_text, 1, wx.ALIGN_LEFT)
        grid.Add(pgm_label, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self._pgm_text, 1, wx.ALIGN_LEFT)
        grid.Add(limits_label, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        grid.Add(limits_sizer, 1, wx.ALIGN_LEFT)
        grid.Add(eq_cfg_label, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self._eq_cfg_combo, 1, wx.ALIGN_LEFT)
        grid.Add(loc_label, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self._loc_combo, 1, wx.ALIGN_LEFT)
        grid.Add(obj_label, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self._obj_entry, 1, wx.ALIGN_LEFT)

        btn_sizer = self.CreateSeparatedButtonSizer(wx.OK | wx.CANCEL)

        vbox.Add(grid, 0, wx.ALL, border=10)
        vbox.Add(btn_sizer, 0, wx.ALL | wx.EXPAND, border=10)

        self.SetSizer(vbox)
        self.Fit()
        sz = self.GetBestSize()
        self.SetSizeHints(sz.x, sz.y, sz.x, sz.y)

        self.Bind(wx.EVT_BUTTON, self._get_input_dir, id=self._in_dir_btn_id.GetId())
        self.Bind(wx.EVT_BUTTON, self._get_master_dir, id=self._master_dir_btn_id.GetId())
        self.Bind(wx.EVT_BUTTON, self._get_output_dir, id=self._output_dir_btn_id.GetId())
        self.Bind(wx.EVT_BUTTON, self._do_reduce, id=wx.ID_OK)
        self.Bind(wx.EVT_BUTTON, self.on_cancel, id=wx.ID_CANCEL)

    # noinspection PyUnusedLocal
    def _get_input_dir(self, event: wx.CommandEvent) -> None:
        in_dir = wxutil.select_dir(self, True)
        if in_dir:
            self._in_dir_text.SetValue(in_dir)

    # noinspection PyUnusedLocal
    def _get_output_dir(self, event: wx.CommandEvent) -> None:
        out_dir = wxutil.select_dir(self, False)
        if out_dir:
            self._output_dir_text.SetValue(out_dir)

    # noinspection PyUnusedLocal
    def _get_master_dir(self, event: wx.CommandEvent) -> None:
        mst_dir = wxutil.select_dir(self, True)
        if mst_dir:
            self._master_dir_text.SetValue(mst_dir)

    # noinspection PyUnusedLocal
    def _do_reduce(self, event: wx.CommandEvent) -> None:
        input_dir = self._in_dir_text.GetValue().strip()
        if not input_dir:
            return
        input_path = wxutil.ensure_dir_exists(input_dir, 'input', self)
        if not input_path:
            return
        output_dir = self._output_dir_text.GetValue().strip()
        if not output_dir:
            return
        master_dir = self._master_dir_text.GetValue().strip()
        if not master_dir:
            master_path = input_path
        else:
            master_path = wxutil.ensure_dir_exists(master_dir, 'master', self)
        bias_pattern = self._bias_text.GetValue().strip()
        if bias_pattern:
            bias_path = wxutil.find_files_by_pattern(master_path, bias_pattern, 'bias', self,
                                                     unique=True)
            if not bias_path:
                return
        else:
            bias_path = None

        dark_pattern = self._dark_text.GetValue().strip()
        if not dark_pattern:
            dark_files = None
        else:
            dark_files = wxutil.find_files_by_pattern(master_path, dark_pattern, 'dark', self)
            if not dark_files:
                return
        flat_pattern = self._flat_text.GetValue().strip()
        if flat_pattern:
            flat_file = wxutil.find_files_by_pattern(master_path, flat_pattern, 'flat', self,
                                                     unique=True)
            if not flat_file:
                return
        else:
            flat_file = None
        pgm_pattern = self._pgm_text.GetValue().strip()
        if not pgm_pattern:
            pgm_files = None
        else:
            pgm_files = wxutil.find_files_by_pattern(input_path, pgm_pattern, 'program', self)
            if not pgm_files:
                return
            if isinstance(pgm_files, Path):
                pgm_files = (pgm_files,)

        calib_pattern = self._calib_text.GetValue().strip()
        if not calib_pattern:
            return
        calib_path = wxutil.find_files_by_pattern(input_path, calib_pattern, 'calibration', self,
                                                  unique=True)
        if not calib_path:
            return
        output_path = wxutil.create_dir(output_dir, 'output', self)
        if not output_path:
            return
        y_lo = self._y_lo_text.GetValue()
        y_hi = self._y_hi_text.GetValue()
        if y_lo is None or y_hi is None:
            limits = None
        elif y_lo > y_hi:
            limits = (y_hi, y_lo)
        else:
            limits = (y_lo, y_hi)
        eq_cfg_name = self._eq_cfg_combo.GetValue()
        eq_cfg = Config.get().get_aavso_config(eq_cfg_name)
        cam_cfg_name = eq_cfg.ccd
        header_overrides = dict()
        header_overrides['AAV_INST'] = eq_cfg_name

        obj_name = self._obj_entry.GetValue().strip()
        if obj_name:
            header_overrides['OBJNAME'] = obj_name
        obscode = Config.get().get_aavso_obscode()
        if obscode:
            header_overrides['OBSERVER'] = obscode
        loc_name = self._loc_combo.GetValue()
        if loc_name:
            header_overrides['AAV_SITE'] = loc_name

        reduce_params = ReduceParams(output_path=output_path,
                                     calib_file=calib_path,
                                     cam_cfg_name=cam_cfg_name,
                                     header_overrides=header_overrides,
                                     limits=limits,
                                     bias_path=bias_path,
                                     dark_files=dark_files,
                                     flat_path=flat_file,
                                     pgm_files=pgm_files)

        dark_args = [bias_path, dark_files, flat_file, pgm_files, calib_path, output_path, cam_cfg_name,
                     header_overrides]

        progress_limit = 100
        self.run_task(progress_limit, self._reduce_dark, (reduce_params, ))

    def _reduce_dark(self, params: ReduceParams):
        num_steps = 5
        if not params.dark_files:
            # No dark correction
            num_steps -= 1
        if not params.pgm_files or params.limits:
            # No rotation
            num_steps -= 1
        if not params.flat_path:
            # No flat correction
            num_steps -= 1
        budget_step = int(100.0 / num_steps)
        progress = 0

        if params.dark_files:
            self.send_progress(0, 'Applying dark correction.')
            output = self._apply_dark_correction(params, budget_step, progress)
            if self.cancel_flag.is_set():
                if output:
                    util.remove_dir_recursively(output)
                return
            progress += budget_step
        else:
            output = None

        if params.pgm_files and not params.limits:
            self.send_progress(progress, 'Rotating files.')
            previous_output = output
            output = self._rotate_images(params, previous_output, budget_step, progress)
            if previous_output:
                util.remove_dir_recursively(previous_output)
            if self.cancel_flag.is_set():
                if output:
                    util.remove_dir_recursively(output)
                return
            progress += budget_step

        if params.flat_path:
            self.send_progress(progress, 'Applying flat correction.')
            previous_output = output
            output = self._apply_flat_correction(params, previous_output)
            if previous_output:
                util.remove_dir_recursively(previous_output)
            if self.cancel_flag.is_set():
                if output:
                    util.remove_dir_recursively(output)
                return
            progress += budget_step

        self.send_progress(progress, 'Applying slant correction...')
        previous_output = output
        output = self._apply_slant_correction(params, previous_output)
        if previous_output:
            util.remove_dir_recursively(previous_output)
        if self.cancel_flag.is_set():
            if output:
                util.remove_dir_recursively(output)
            return
        progress += budget_step

        self._extract_spectra(params, output, budget_step, progress)
        if output:
            util.remove_dir_recursively(output)
        if not self.cancel_flag.is_set():
            self.send_progress(100, 'Data reduction complete.')

    def _apply_dark_correction(self, params: ReduceParams, budget_step: int, progress: int) -> Union[None, Path]:
        dark = Dark(params.bias_path, params.dark_files)
        if self.cancel_flag.is_set():
            return None
        # Create temporary directory under the output dir.
        dark_output = Path(tempfile.mkdtemp(dir=params.output_path))
        file_list = list()
        if params.pgm_files:
            file_list.extend(params.pgm_files)
        file_list.append(params.calib_file)
        if params.flat_path:
            file_list.append(params.flat_path)
        dark.correct(file_list, dark_output, self.send_progress, budget=budget_step - 1, start_with=progress)

    def _rotate_images(self, params: ReduceParams, input_dir: Union[None, Path],
                       budget_step: int, progress: int) -> Union[None, Path]:
        rotate_output = Path(tempfile.mkdtemp(dir=params.output_path))
        file_list = list()
        if input_dir:
            file_list.extend([input_dir / f.name for f in params.pgm_files])
            file_list.append(input_dir / params.calib_file.name)
            if params.flat_path:
                file_list.append(input_dir / params.flat_path.name)
        else:
            file_list.extend(params.pgm_files)
            file_list.append(params.calib_file)
            if params.flat_path:
                file_list.append(params.flat_path)

        rot = Rotate(file_list[0])
        if self.cancel_flag.is_set():
            return rotate_output
        rot.rotate(file_list, rotate_output, self.send_progress, budget=budget_step - 1, start_with=progress)
        return rotate_output

    @staticmethod
    def _apply_flat_correction(params: ReduceParams, input_dir: Union[None, Path]) -> Union[None, Path]:
        output = Path(tempfile.mkdtemp(dir=params.output_path))
        if input_dir:
            flat_path = input_dir / params.flat_path.name
            flat_input = list()
            if params.pgm_files:
                flat_input.extend([input_dir / x.name for x in params.pgm_files])
            flat_input.append(input_dir / params.calib_file.name)
        else:
            flat_path = params.flat_path
            flat_input = list()
            if params.pgm_files:
                flat_input.extend(params.pgm_files)
            flat_input.append(params.calib_file)
        flat.auto_flat(flat_path, flat_input, output)
        return output

    def _apply_slant_correction(self, params: ReduceParams, input_dir: Union[None, Path]) -> Union[None, Path]:
        if input_dir:
            calib_file = input_dir / params.calib_file.name
            slt_input_files = [calib_file]
            if params.pgm_files:
                slt_input_files.extend([input_dir / f.name for f in params.pgm_files])
        else:
            calib_file = params.calib_file
            slt_input_files = [calib_file]
            if params.pgm_files:
                slt_input_files.extend(params.pgm_files)
        slt = Slant(calib_file)
        if self.cancel_flag.is_set():
            return None
        slant_output = Path(tempfile.mkdtemp(dir=params.output_path))
        slt.apply(slt_input_files, slant_output)
        return slant_output

    def _extract_spectra(self, params: ReduceParams, input_dir: Union[None, Path],
                         budget_step: int, progress: int):
        if params.pgm_files:
            if input_dir:
                pgm_files = [input_dir / f.name for f in params.pgm_files]
            else:
                pgm_files = params.pgm_files
        else:
            pgm_files = None
        if input_dir:
            calib_file = input_dir / params.calib_file.name
        else:
            calib_file = params.calib_file

        if params.pgm_files and not params.limits:
            d_lo, d_hi = ex_optimal(pgm_files, params.cam_cfg_name, params.output_path,
                                    callback=self.send_progress,
                                    header_overrides=params.header_overrides,
                                    budget=budget_step - 1, start_with=progress)
            if not self.cancel_flag.is_set():
                ex_simple(calib_file, (d_lo, d_hi), params.output_path)
        else:
            if pgm_files:
                ex_simple(pgm_files, params.limits, params.output_path)
            ex_simple(calib_file, params.limits, params.output_path)


if __name__ == '__main__':
    app = wx.App()
    app.SetAppName('spectra')
    frame = wx.Frame(None, title='Reduce Test')
    pnl = wx.Panel(frame)
    id_ref = wx.NewIdRef()
    button = wx.Button(pnl, id=id_ref.GetId(), label='Run')
    sizer = wx.BoxSizer(wx.VERTICAL)
    sizer.Add(button, 0, 0, 0)
    pnl.SetSizer(sizer)
    pnl.Fit()
    pnl_sz = pnl.GetBestSize()
    frame.SetClientSize(pnl_sz)

    # noinspection PyUnusedLocal
    def _on_btn(event):
        button.Disable()
        dlg = Reduce(frame)

        def on_dlg_show(evt: wx.ShowEvent):
            if not evt.IsShown():
                dlg.Destroy()
                button.Enable()

        dlg.Bind(wx.EVT_SHOW, on_dlg_show)
        dlg.Show()

    frame.Bind(wx.EVT_BUTTON, _on_btn, id=id_ref.GetId())
    frame.Show()
    app.MainLoop()
