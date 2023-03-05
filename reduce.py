from pathlib import Path
import tempfile
from typing import Union, Sequence, Dict
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
import wxutil


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
        grid = wx.FlexGridSizer(rows=11, cols=2, hgap=5, vgap=5)
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
        if not bias_pattern:
            return
        bias_path = wxutil.find_files_by_pattern(master_path, bias_pattern, 'bias', self,
                                                 unique=True)
        if not bias_path:
            return
        dark_pattern = self._dark_text.GetValue().strip()
        if not dark_pattern:
            return
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
            return
        pgm_files = wxutil.find_files_by_pattern(input_path, pgm_pattern, 'program', self)
        if not pgm_files:
            return
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

        dark_args = [bias_path, dark_files, flat_file, pgm_files, calib_path, output_path, cam_cfg_name,
                     header_overrides]

        progress_limit = 100
        self.run_task(progress_limit, self._reduce_dark, dark_args)

    def _reduce_dark(self, bias_path: Path, dark_files: Sequence[Path], flat_path: Path,
                     pgm_files: Union[Path, Sequence[Path]],
                     calib_file: Path, output_path: Path, cfg_name: str, header_overrides: Dict[str, str]):
        if flat_path:
            budget_step = 20
        else:
            budget_step = 25
        progress = 0

        if isinstance(pgm_files, Path):
            pgm_files = (pgm_files, )

        self.send_progress(0, 'Applying dark correction.')
        dark = Dark(bias_path, dark_files)
        if self.cancel_flag.is_set():
            return
        # Create temporary directory under the output dir.
        dark_output = Path(tempfile.mkdtemp(dir=output_path))
        file_list = list(pgm_files)
        file_list.append(calib_file)
        if flat_path:
            file_list.append(flat_path)
        dark.correct(file_list, dark_output, self.send_progress, budget=budget_step - 1, start_with=progress)
        if self.cancel_flag.is_set():
            util.remove_dir_recursively(dark_output)
            return
        progress += budget_step

        rotate_output = Path(tempfile.mkdtemp(dir=output_path))
        dark_corrected = [dark_output / f.name for f in file_list]
        self.send_progress(progress, 'Rotating files.')
        rot = Rotate(file_list[0])
        if self.cancel_flag.is_set():
            util.remove_dir_recursively(dark_output)
            return
        rot.rotate(dark_corrected, rotate_output, self.send_progress, budget=budget_step - 1, start_with=progress)
        util.remove_dir_recursively(dark_output)
        if self.cancel_flag.is_set():
            util.remove_dir_recursively(rotate_output)
            return
        progress += budget_step

        if flat_path:
            slant_input = Path(tempfile.mkdtemp(dir=output_path))
            flat_path = rotate_output / flat_path.name
            flat_input = [rotate_output / x.name for x in pgm_files]
            flat_input.append(rotate_output / calib_file.name)
            self.send_progress(progress, 'Applying flat correction.')
            flat.auto_flat(flat_path, flat_input, slant_input)
            util.remove_dir_recursively(rotate_output)
            if self.cancel_flag.is_set():
                util.remove_dir_recursively(slant_input)
                return
            progress += budget_step
        else:
            slant_input = rotate_output

        self.send_progress(progress, 'Applying slant correction...')
        calib_file = slant_input / calib_file.name
        slt = Slant(calib_file)
        slant_output = Path(tempfile.mkdtemp(dir=output_path))
        slt_input_files = [calib_file]
        slt_input_files.extend([slant_input / x.name for x in pgm_files])
        slt.apply(slt_input_files, slant_output)
        util.remove_dir_recursively(slant_input)
        if self.cancel_flag.is_set():
            util.remove_dir_recursively(slant_output)
            return
        progress += budget_step

        ex_o_input = [slant_output / f.name for f in pgm_files]
        d_lo, d_hi = ex_optimal(ex_o_input, cfg_name, output_path, callback=self.send_progress,
                                header_overrides=header_overrides, budget=budget_step - 1, start_with=progress)
        if not self.cancel_flag.is_set():
            calib_slt_corrected = slant_output / calib_file.name
            ex_simple(calib_slt_corrected, (d_lo, d_hi), output_path)
            simple_path = output_path / 'simple'
            simple_path.mkdir(exist_ok=True)
            ex_simple(ex_o_input, (d_lo, d_hi), simple_path)
        util.remove_dir_recursively(slant_output)
        if not self.cancel_flag.is_set():
            self.send_progress(100, 'Data reduction complete.')


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
