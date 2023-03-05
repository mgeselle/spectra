from astropy.io import fits
from pathlib import Path
from typing import Sequence, Tuple
import wx
import wx.lib.intctrl as wxli

from taskdialog import TaskDialog
import util
import wxutil


class Crop(TaskDialog):
    def __init__(self, parent: wx.Window, **kwargs):
        super().__init__(parent, **kwargs)
        self.SetTitle('Crop Images')
        self.progress_title = 'Cropping...'
        self.message_template = u'\u00a0' * 30

        text_chars = 40
        in_dir_label = wx.StaticText(self, wx.ID_ANY, 'Input Directory:')
        self._in_dir_text = wx.TextCtrl(self)
        wxutil.size_text_by_chars(self._in_dir_text, text_chars)
        folder_bmp = wx.ArtProvider.GetBitmap(wx.ART_FOLDER_OPEN, wx.ART_BUTTON)
        self._in_dir_btn_id = wx.NewIdRef()
        in_dir_btn = wx.BitmapButton(self, id=self._in_dir_btn_id.GetId(), bitmap=folder_bmp)
        in_dir_sizer = wx.BoxSizer(wx.HORIZONTAL)
        in_dir_sizer.Add(self._in_dir_text, 1, wx.EXPAND | wx.ALIGN_LEFT)
        in_dir_sizer.Add(in_dir_btn, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT)

        out_dir_label = wx.StaticText(self, wx.ID_ANY, 'Output Directory:')
        self._out_dir_text = wx.TextCtrl(self)
        wxutil.size_text_by_chars(self._out_dir_text, text_chars)
        self._out_dir_btn_id = wx.NewIdRef()
        out_dir_btn = wx.BitmapButton(self, id=self._out_dir_btn_id.GetId(), bitmap=folder_bmp)
        out_dir_sizer = wx.BoxSizer(wx.HORIZONTAL)
        out_dir_sizer.Add(self._out_dir_text, 1, wx.EXPAND | wx.ALIGN_LEFT)
        out_dir_sizer.Add(out_dir_btn, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT)

        c1_label = wx.StaticText(self, wx.ID_ANY, 'x1, y1')
        self._cx1_text = wxli.IntCtrl(self, min=0)
        wxutil.size_text_by_chars(self._cx1_text, 5)
        self._cy1_text = wxli.IntCtrl(self, min=0)
        wxutil.size_text_by_chars(self._cy1_text, 5)
        c1_sizer = wx.BoxSizer(wx.HORIZONTAL)
        c1_sizer.Add(self._cx1_text, 1, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT)
        c1_sizer.AddSpacer(10)
        c1_sizer.Add(self._cy1_text, 1, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT)

        c2_label = wx.StaticText(self, wx.ID_ANY, 'x2, y2')
        self._cx2_text = wxli.IntCtrl(self, min=0)
        wxutil.size_text_by_chars(self._cx2_text, 5)
        self._cy2_text = wxli.IntCtrl(self, min=0)
        wxutil.size_text_by_chars(self._cy2_text, 5)
        c2_sizer = wx.BoxSizer(wx.HORIZONTAL)
        c2_sizer.Add(self._cx2_text, 1, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT)
        c2_sizer.AddSpacer(10)
        c2_sizer.Add(self._cy2_text, 1, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT)

        vbox = wx.BoxSizer(wx.VERTICAL)
        grid = wx.FlexGridSizer(rows=4, cols=2, hgap=5, vgap=5)
        grid.Add(in_dir_label, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        grid.Add(in_dir_sizer, 1, wx.ALIGN_LEFT)
        grid.Add(out_dir_label, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        grid.Add(out_dir_sizer, 1, wx.ALIGN_LEFT)
        grid.Add(c1_label, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        grid.Add(c1_sizer, 1, wx.ALIGN_LEFT)
        grid.Add(c2_label, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        grid.Add(c2_sizer, 1, wx.ALIGN_LEFT)

        btn_sizer = self.CreateSeparatedButtonSizer(wx.OK | wx.CANCEL)

        vbox.Add(grid, 0, wx.ALL, border=10)
        vbox.Add(btn_sizer, 0, wx.ALL | wx.EXPAND, border=10)

        self.SetSizer(vbox)
        self.Fit()
        sz = self.GetBestSize()
        self.SetSizeHints(sz.x, sz.y, sz.x, sz.y)

        self.Bind(wx.EVT_BUTTON, self._select_in_dir, id=self._in_dir_btn_id.GetId())
        self.Bind(wx.EVT_BUTTON, self._select_out_dir, id=self._out_dir_btn_id.GetId())
        self.Bind(wx.EVT_BUTTON, self._crop, id=wx.ID_OK)
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
    def _crop(self, event: wx.Event):
        in_path = util.dir_to_path(self._in_dir_text.GetValue())
        if in_path == '' or not in_path.exists():
            return
        if not any(in_path.glob('*.fits')) and not any(in_path.glob('*.fit')):
            return
        out_path = util.dir_to_path(self._out_dir_text.GetValue())
        if out_path == '':
            return

        x1 = self._cx1_text.GetValue()
        x2 = self._cx2_text.GetValue()
        y1 = self._cy1_text.GetValue()
        y2 = self._cy2_text.GetValue()
        if x1 == x2 or y1 == y2:
            return

        try:
            out_path.mkdir(parents=True, exist_ok=True)
        except PermissionError as err:
            with wx.MessageDialog(self, message=f'Cannot create output directory: {err}',
                                  style=wx.OK | wx.ICON_ERROR | wx.CANCEL, caption='Error') as mb:
                mb.ShowModal()
            return

        files = []
        for in_file in sorted(in_path.iterdir()):
            if not in_file.is_file() or not (in_file.suffix in ('.fits', '.fit')):
                continue
            files.append(in_file)
        if len(files) == 0:
            return

        x_tup = sorted((x1, x2))
        y_tup = tuple(sorted((y1, y2)))

        self.run_task(maximum=len(files) + 1, target=self._do_crop,
                      args=(files, out_path, x_tup, y_tup))

    def _do_crop(self, files: Sequence[Path], out_dir: Path,
                 x: Tuple[int, int], y: Tuple[int, int]) -> None:

        n_processed = 0
        n_files = len(files)
        for in_file in files:
            if self.cancel_flag.is_set():
                break
            self.send_progress(n_processed, f'Processing file {n_processed + 1:d} of {n_files:d}')
            full_out_file = out_dir / in_file.name
            hdu_l = fits.open(in_file)
            header = hdu_l[0].header
            data = hdu_l[0].data
            new_data = data[y[0]:y[1], x[0]:x[1]]
            new_hdu = fits.PrimaryHDU(new_data, header)
            new_hdu.writeto(full_out_file, overwrite=True)
            hdu_l.close()
            n_processed = n_processed + 1

        if not self.cancel_flag.is_set():
            self.send_progress(n_processed + 1, f'Processed {n_processed} file(s).')


if __name__ == '__main__':
    app = wx.App()
    frame = wx.Frame(None, title='Crop Test')
    pnl = wx.Panel(frame)
    id_ref = wx.NewIdRef()
    button = wx.Button(pnl, id=id_ref.GetId(), label='Run')
    sizer = wx.BoxSizer(wx.VERTICAL)
    sizer.Add(button)
    pnl.SetSizer(sizer)
    pnl.Fit()

    # noinspection PyUnusedLocal
    def _on_btn(event):
        button.Disable()
        crp = Crop(frame, id=4711)

        def _on_complete(evt: wx.ShowEvent):
            if not evt.IsShown():
                crp.Destroy()
                button.Enable()

        crp.Bind(wx.EVT_SHOW, _on_complete)
        crp.Show()

    frame.Bind(wx.EVT_BUTTON, _on_btn, id=id_ref.GetId())
    frame.Show()
    app.MainLoop()
