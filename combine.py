from astropy.io import fits
import numpy as np
import numpy.typing as npt
from pathlib import Path
from typing import Union, Any, Sequence
from taskdialog import TaskDialog
import wx
import wxutil


class Combine(TaskDialog):
    _methods = ['average', 'median']

    def __init__(self, parent: wx.Window, **kwargs):
        super().__init__(parent, **kwargs)
        self.SetTitle('Combine Images')
        self.progress_title = 'Combining...'
        self.message_template = u'\u00a0' * 40

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

        base_name_label = wx.StaticText(panel, wx.ID_ANY, 'Image Basename:')
        self._base_name_text = wx.TextCtrl(panel)
        wxutil.size_text_by_chars(self._base_name_text, text_chars)

        out_dir_label = wx.StaticText(panel, wx.ID_ANY, 'Output Directory:')
        self._out_dir_text = wx.TextCtrl(panel)
        wxutil.size_text_by_chars(self._out_dir_text, text_chars)
        self._out_dir_btn_id = wx.NewIdRef()
        out_dir_btn = wx.BitmapButton(panel, id=self._out_dir_btn_id.GetId(), bitmap=folder_bmp)
        out_dir_sizer = wx.BoxSizer(wx.HORIZONTAL)
        out_dir_sizer.Add(self._out_dir_text, 1, wx.EXPAND | wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT)
        out_dir_sizer.Add(out_dir_btn, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT)

        out_name_label = wx.StaticText(panel, wx.ID_ANY, 'Output Name:')
        self._out_name_text = wx.TextCtrl(panel)
        wxutil.size_text_by_chars(self._out_name_text, text_chars)

        method_label = wx.StaticText(panel, wx.ID_ANY, 'Method:')
        self._method_combo = wx.ComboBox(panel, value=Combine._methods[0],
                                         choices=Combine._methods,
                                         style=wx.CB_READONLY | wx.CB_DROPDOWN)
        wxutil.size_text_by_chars(self._method_combo, 8)

        vbox = wx.BoxSizer(wx.VERTICAL)
        grid = wx.FlexGridSizer(rows=5, cols=2, hgap=5, vgap=5)
        grid.Add(in_dir_label, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        grid.Add(in_dir_sizer, 1, wx.ALIGN_LEFT)
        grid.Add(base_name_label, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self._base_name_text, 1, wx.ALIGN_LEFT)
        grid.Add(out_dir_label, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        grid.Add(out_dir_sizer, 1, wx.ALIGN_LEFT)
        grid.Add(out_name_label, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self._out_name_text, 1, wx.ALIGN_LEFT)
        grid.Add(method_label, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self._method_combo, 1, wx.ALIGN_LEFT)

        btn_sizer = self.CreateSeparatedButtonSizer(wx.OK | wx.CANCEL)

        vbox.Add(grid, 0, wx.ALL, border=10)
        vbox.Add(btn_sizer, 0, wx.ALL | wx.EXPAND, border=10)

        panel.SetSizer(vbox)
        panel.Fit()

        self.Layout()
        sz = self.GetBestSize()
        self.SetSizeHints(sz.x, sz.y, sz.x, sz.y)

        self.Bind(wx.EVT_BUTTON, self._select_in_dir, id=self._in_dir_btn_id.GetId())
        self.Bind(wx.EVT_BUTTON, self._select_out_dir, id=self._out_dir_btn_id.GetId())
        self.Bind(wx.EVT_BUTTON, self._do_combine, id=wx.ID_OK)
        self.Bind(wx.EVT_BUTTON, self.on_cancel, id=wx.ID_CANCEL)

    # noinspection PyUnusedLocal
    def _select_in_dir(self, event: wx.Event):
        new_in_dir = wxutil.select_dir(self, True)
        if new_in_dir:
            self._in_dir_text.SetValue(new_in_dir)

    # noinspection PyUnusedLocal
    def _select_out_dir(self, event: wx.Event):
        new_out_dir = wxutil.select_dir(self, False)
        if new_out_dir:
            self._out_dir_text.SetValue(new_out_dir)

    # noinspection PyUnusedLocal
    def _do_combine(self, event: wx.Event):
        in_dir = self._in_dir_text.GetValue().strip()
        in_basename = self._base_name_text.GetValue().strip()
        out_dir = self._out_dir_text.GetValue().strip()
        out_name = self._out_name_text.GetValue().strip()
        if not in_dir or not in_basename or not out_dir or not out_name:
            return

        mode = self._method_combo.GetValue()

        in_dir = in_dir.replace('~', str(Path.home()))
        in_path = Path(in_dir)
        out_dir = out_dir.replace('~', str(Path.home()))
        out_path = Path(out_dir)

        in_files = []
        for candidate in in_path.glob(in_basename + '*.*'):
            if candidate.suffix in ('.fit', '.fits'):
                in_files.append(candidate)
        if not in_files:
            with wx.MessageDialog(self, 'No matching input files found.', caption='Error',
                                  style=wx.OK | wx.ICON_ERROR) as dlg:
                dlg.ShowModal()
            return
        try:
            out_path.mkdir(parents=True, exist_ok=True)
        except PermissionError as err:
            with wx.MessageDialog(self, f'Cannot create output dir: {err}.', caption='Error',
                                  style=wx.OK | wx.ICON_ERROR) as dlg:
                dlg.ShowModal()
            return

        self.run_task(maximum=len(in_files) + 2, target=self._do_combine_bg,
                      args=(in_files, out_dir, out_name, mode))

    def _do_combine_bg(self, in_files: Sequence[Path], out_dir: Path,
                       out_name: str, mode: str):
        input_data: Union[None, npt.NDArray[Any]] = None
        header = None
        data_idx = 0
        in_type = None
        for input_file in in_files:
            if self.cancel_flag.is_set():
                break
            self.send_progress(data_idx + 1, f'Reading {input_file.name}')
            in_hdu_l = fits.open(input_file)
            data: npt.NDArray[Any] = in_hdu_l[0].data
            if input_data is None:
                header = in_hdu_l[0].header
                num_files = len(in_files)
                input_data = np.empty((num_files, data.shape[0], data.shape[1]), data.dtype)
                header['HISTORY'] = f'Combined {num_files} files.'
                in_type = data.dtype
            input_data[data_idx, :, :] = data
            in_hdu_l.close()
            data_idx = data_idx + 1
        output_data = None
        if not self.cancel_flag.is_set():
            self.send_progress(data_idx + 1, f'Combining using {mode}.')
            data_idx = data_idx + 1
            if mode == 'median':
                output_data = np.median(input_data, axis=0)
            else:
                output_data = np.mean(input_data, axis=0)
        if not self.cancel_flag.is_set():
            out_hdu = fits.PrimaryHDU(output_data.astype(in_type), header)
            out_name_full = out_name
            if not out_name_full.endswith('.fit') and not out_name_full.endswith('.fits'):
                out_name_full = out_name_full + in_files[0].suffix
            out_path = Path(out_dir) / out_name_full
            out_hdu.writeto(out_path, overwrite=True)
            self.send_progress(data_idx + 1, f'Output written to {out_name_full}')


if __name__ == '__main__':
    app = wx.App()
    frame = wx.Frame(None, title='Combine Test')
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
        dlg = Combine(frame)

        def on_dlg_show(evt: wx.ShowEvent):
            if not evt.IsShown():
                dlg.Destroy()
                button.Enable()

        dlg.Bind(wx.EVT_SHOW, on_dlg_show)
        dlg.Show()

    frame.Bind(wx.EVT_BUTTON, _on_btn, id=id_ref.GetId())
    frame.Show()
    app.MainLoop()
