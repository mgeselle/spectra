import itertools
from pathlib import Path
import tempfile
from typing import Union, Sequence, Iterable, Callable
import wx

import flat
from config import Config
from dark import Dark
from extract import optimal as ex_optimal
from extract import simple as ex_simple
from flat import FlatDialog
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

        master_dir_label = wx.StaticText(panel, wx.ID_ANY, 'Master Directory:')
        self._master_dir_text = wx.TextCtrl(panel)
        wxutil.size_text_by_chars(self._master_dir_text, text_chars)
        self._master_dir_btn_id = wx.NewIdRef()
        master_dir_btn = wx.BitmapButton(panel, id=self._master_dir_btn_id.GetId(), bitmap=folder_bmp)
        master_dir_sizer = wx.BoxSizer(wx.HORIZONTAL)
        master_dir_sizer.Add(self._master_dir_text, 1, wx.EXPAND | wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT)
        master_dir_sizer.Add(master_dir_btn, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT)

        output_dir_label = wx.StaticText(panel, wx.ID_ANY, 'Output Directory:')
        self._output_dir_text = wx.TextCtrl(panel)
        wxutil.size_text_by_chars(self._output_dir_text, text_chars)
        self._output_dir_btn_id = wx.NewIdRef()
        output_dir_btn = wx.BitmapButton(panel, id=self._output_dir_btn_id.GetId(), bitmap=folder_bmp)
        output_dir_sizer = wx.BoxSizer(wx.HORIZONTAL)
        output_dir_sizer.Add(self._output_dir_text, 1, wx.EXPAND | wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT)
        output_dir_sizer.Add(output_dir_btn, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT)

        bias_label = wx.StaticText(panel, wx.ID_ANY, 'Bias Pattern:')
        self._bias_text = wx.TextCtrl(panel)
        wxutil.size_text_by_chars(self._bias_text, text_chars)

        dark_label = wx.StaticText(panel, wx.ID_ANY, 'Dark Pattern:')
        self._dark_text = wx.TextCtrl(panel)
        wxutil.size_text_by_chars(self._dark_text, text_chars)

        flat_label = wx.StaticText(panel, wx.ID_ANY, 'Flat Pattern:')
        self._flat_text = wx.TextCtrl(panel)
        wxutil.size_text_by_chars(self._flat_text, text_chars)

        calib_label = wx.StaticText(panel, wx.ID_ANY, 'Calibration Pattern:')
        self._calib_text = wx.TextCtrl(panel)
        wxutil.size_text_by_chars(self._calib_text, text_chars)

        pgm_label = wx.StaticText(panel, wx.ID_ANY, 'Program Pattern:')
        self._pgm_text = wx.TextCtrl(panel)
        wxutil.size_text_by_chars(self._pgm_text, text_chars)

        cam_cfg_label = wx.StaticText(panel, wx.ID_ANY, 'Camera Configuration:')
        config_values = Config.get().get_camera_configs()
        self._cam_cfg_combo = wx.ComboBox(panel, value=config_values[0], choices=config_values,
                                          style=wx.CB_DROPDOWN | wx.CB_READONLY)
        wxutil.size_text_by_chars(self._cam_cfg_combo, 30)

        vbox = wx.BoxSizer(wx.VERTICAL)
        grid = wx.FlexGridSizer(rows=9, cols=2, hgap=5, vgap=5)
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
        grid.Add(cam_cfg_label, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self._cam_cfg_combo, 1, wx.ALIGN_LEFT)

        btn_sizer = self.CreateSeparatedButtonSizer(wx.OK | wx.CANCEL)

        vbox.Add(grid, 0, wx.ALL, border=10)
        vbox.Add(btn_sizer, 0, wx.ALL | wx.EXPAND, border=10)

        panel.SetSizer(vbox)
        panel.Fit()

        self.Layout()
        sz = self.GetBestSize()
        self.SetSizeHints(sz.x, sz.y, sz.x, sz.y)

        self.Bind(wx.EVT_BUTTON, self._get_input_dir, id=self._in_dir_btn_id.GetId())
        self.Bind(wx.EVT_BUTTON, self._get_master_dir, id=self._master_dir_btn_id.GetId())
        self.Bind(wx.EVT_BUTTON, self._get_output_dir, id=self._output_dir_btn_id.GetId())
        self.Bind(wx.EVT_BUTTON, self._do_reduce, id=wx.ID_OK)
        self.Bind(wx.EVT_BUTTON, self.on_cancel, id=wx.ID_CANCEL)

    def _get_input_dir(self, event: wx.CommandEvent) -> None:
        in_dir = wxutil.select_dir(self, True)
        if in_dir:
            self._in_dir_text.SetValue(in_dir)

    def _get_output_dir(self, event: wx.CommandEvent) -> None:
        out_dir = wxutil.select_dir(self, False)
        if out_dir:
            self._output_dir_text.SetValue(out_dir)

    def _get_master_dir(self, event: wx.CommandEvent) -> None:
        mst_dir = wxutil.select_dir(self, True)
        if mst_dir:
            self._master_dir_text.SetValue(mst_dir)

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
        cfg_name = self._cam_cfg_combo.GetValue()

        dark_output = Path(tempfile.mkdtemp(dir=output_path))
        pgm_out = [dark_output / f.name for f in pgm_files]
        flat_and_calib = [calib_path]
        calib_out = dark_output / calib_path.name
        if flat_file:
            flat_and_calib.append(flat_file)
            flat_out = dark_output / flat_file.name

            def dark_completion():
                self._reduce_flat(flat_out, calib_out, pgm_out, output_path, cfg_name)

            self.completion_callback = dark_completion
            self.auto_hide = True
        else:
            flat_out = None

        dark_input = itertools.chain(pgm_files, flat_and_calib)
        dark_args = [bias_path, dark_files, dark_input, dark_output]
        if flat_file:
            dark_args.append(None)
        else:

            def dark_continue():
                self._reduce_1d(calib_out, pgm_out, output_path, cfg_name, budget=50, start_with=50)

            dark_args.append(dark_continue)

        progress_limit = 100
        self.run_task(progress_limit, self._reduce_dark, dark_args)

    def _reduce_dark(self, bias_path: Path, dark_files: Sequence[Path], files: Iterable[Path],
                     output_path: Path, continuation: Union[Callable[[], None], None]):
        total_budget = 100
        if continuation:
            total_budget /= 2
        half_budget = int(total_budget / 2)

        self.send_progress(0, 'Applying dark correction.')
        dark = Dark(bias_path, dark_files)
        if self.cancel_flag.is_set():
            return
        # output_path is a temporary directory under the output dir.
        # Create another temporary directory under the output dir.
        dark_output = Path(tempfile.mkdtemp(dir=output_path.parent))
        file_list = list(files)
        dark.correct(file_list, dark_output, self.send_progress, budget=half_budget, start_with=0)
        if self.cancel_flag.is_set():
            util.remove_dir_recursively(dark_output)
            return

        dark_corrected = [dark_output / f.name for f in file_list]
        self.send_progress(half_budget, 'Rotating files.')
        rot = Rotate(file_list[0])
        if self.cancel_flag.is_set():
            util.remove_dir_recursively(dark_output)
            util.remove_dir_recursively(output_path)
            return
        rot.rotate(dark_corrected, output_path, self.send_progress, budget=half_budget, start_with=half_budget)
        util.remove_dir_recursively(dark_output)

        if continuation:
            continuation()

    def _reduce_flat(self, flat_file: Path, calib_file: Path, pgm_files: Sequence[Path], output_path: Path,
                     cfg_name: str):
        flat_dlg = FlatDialog(self, flat_file)

        def on_flat_hide(evt: wx.ShowEvent):
            if evt.IsShown():
                evt.Skip()
                return
            flat_param = flat_dlg.result
            flat_dlg.Destroy()
            if flat_param:
                flat_output = Path(tempfile.mkdtemp(dir=output_path))
                flat_input = [calib_file]
                flat_input.extend(pgm_files)
                flat.apply(flat_param, flat_input, flat_output)
                calib_out = flat_output / calib_file.name
                pgm_out = [flat_output / f.name for f in pgm_files]
                util.remove_dir_recursively(calib_file.parent)
            else:
                calib_out = calib_file
                pgm_out = pgm_files
            self.completion_callback = None
            self.auto_hide = False

            reduce1d_params = (calib_out, pgm_out, output_path, cfg_name)
            self.run_task(100, self._reduce_1d, reduce1d_params)

        flat_dlg.Bind(wx.EVT_SHOW, on_flat_hide)
        flat_dlg.Show()

    def _reduce_1d(self, calib_file: Path, pgm_files: Sequence[Path], output_path: Path,
                   cfg_name:str, budget: int = 100, start_with: int = 0):
        progress = start_with
        self.send_progress(progress, 'Applying slant correction...')
        slt = Slant(calib_file)
        slt_output = Path(tempfile.mkdtemp(dir=output_path))
        slt_input = [calib_file]
        slt_input.extend(pgm_files)
        slt_budget = int(budget / 10)
        slt.apply(slt_input, slt_output)
        util.remove_dir_recursively(calib_file.parent)
        if self.cancel_flag.is_set():
            util.remove_dir_recursively(slt_output)
            return
        progress += slt_budget
        ext_budget = budget - 2 * slt_budget
        ex_o_input = [slt_output / f.name for f in pgm_files]
        d_lo, d_hi = ex_optimal(ex_o_input, cfg_name, output_path, self.send_progress,
                                ext_budget, progress)
        if not self.cancel_flag.is_set():
            calib_slt_corrected = slt_output / calib_file.name
            ex_simple(calib_slt_corrected, (d_lo, d_hi), output_path)
            simple_path = output_path / 'simple'
            simple_path.mkdir(exist_ok=True)
            ex_simple(ex_o_input, (d_lo, d_hi), simple_path)
        util.remove_dir_recursively(slt_output)
        if not self.cancel_flag.is_set():
            self.send_progress(start_with + budget, 'Data reduction complete.')


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
