from astropy.io import fits
import queue
from pathlib import Path
from queue import Queue
from typing import Tuple
import wx
import wx.lib.intctrl as wxli
from bgexec import BgExec, Event
import bgexec
from progress import Progress
import tkutil
import wxutil


def _is_int(action, key_val):
    if action == '0':
        return True
    else:
        return key_val.isdigit()



class Crop(wx.Dialog):
    def __init__(self, parent: wx.Window, **kwargs):
        super().__init__(parent, **kwargs)
        self.SetTitle('Crop Images')

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

        out_dir_label = wx.StaticText(panel, wx.ID_ANY, 'Output Directory:')
        self._out_dir_text = wx.TextCtrl(panel)
        wxutil.size_text_by_chars(self._out_dir_text, text_chars)
        self._out_dir_btn_id = wx.NewIdRef()
        out_dir_btn = wx.BitmapButton(panel, id=self._out_dir_btn_id.GetId(), bitmap=folder_bmp)
        out_dir_sizer = wx.BoxSizer(wx.HORIZONTAL)
        out_dir_sizer.Add(self._out_dir_text, 1, wx.EXPAND | wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT)
        out_dir_sizer.Add(out_dir_btn, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT)

        c1_label = wx.StaticText(panel, wx.ID_ANY, 'x1, y1')
        self._cx1_text = wxli.IntCtrl(panel, min=0)
        wxutil.size_text_by_chars(self._cx1_text, 5)
        self._cy1_text = wxli.IntCtrl(panel, min=0)
        wxutil.size_text_by_chars(self._cy1_text, 5)
        c1_sizer = wx.BoxSizer(wx.HORIZONTAL)
        c1_sizer.Add(self._cx1_text, 1, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT)
        c1_sizer.AddSpacer(10)
        c1_sizer.Add(self._cy1_text, 1, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT)

        c2_label = wx.StaticText(panel, wx.ID_ANY, 'x1, y1')
        self._cx2_text = wxli.IntCtrl(panel, min=0)
        wxutil.size_text_by_chars(self._cx2_text, 5)
        self._cy2_text = wxli.IntCtrl(panel, min=0)
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

        panel.SetSizer(vbox)
        panel.Fit()
        sz = panel.GetBestSize()
        self.SetSizeHints(sz.x, sz.y, sz.x, sz.y)

    def _select_in_dir(self):
        new_in_dir = tkutil.select_dir(self, True)
        if new_in_dir:
            self._in_dir.set(new_in_dir)

    def _select_out_dir(self):
        new_out_dir = tkutil.select_dir(self, False)
        if new_out_dir:
            self._out_dir.set(new_out_dir)

    def _crop(self):
        in_path = tkutil.dir_to_path(self._in_dir.get())
        if in_path is None or not in_path.exists():
            return
        if not any(in_path.glob('*.fits')) and not any(in_path.glob('*.fit')):
            return
        out_path = tkutil.dir_to_path(self._out_dir.get())
        if out_path is None:
            return

        x1 = self._x1.get()
        x2 = self._x2.get()
        y1 = self._y1.get()
        y2 = self._y2.get()
        if x1 == x2 or y1 == y2:
            return

        self.withdraw()
        try:
            out_path.mkdir(parents=True, exist_ok=True)
        except PermissionError as err:
            # mb.showerror(master=self._master,
            #              message=f'Cannot create output directory: {err}')
            self.deiconify()
            return

        status_queue = queue.Queue()
        progress = Progress(self._master, 'Cropping...')
        x_tup = sorted((x1, x2))
        y_tup = tuple(sorted((y1, y2)))

        # def do_crop():
        #     _do_crop(in_path, out_path,
        #              (x_tup[0], x_tup[1]), (y_tup[0], y_tup[1]),
        #              status_queue, progress)
        #
        # bg_exec = BgExec(do_crop, status_queue)
        progress.start()
        # bg_exec.start()
        # self._check_progress(bg_exec, status_queue, progress)

    def _check_progress(self, bg_exec: BgExec, status_queue: Queue, progress: Progress):
        while not status_queue.empty():
            event = status_queue.get()
            # if event.evt_type == bgexec.ERROR:
            #     progress.withdraw()
            #     mb.showerror(master=self._master, message=event.client_data)
            #     self.destroy()
            #     return
            # elif event.evt_type == bgexec.FINISHED:
            #     progress.withdraw()
            #     mb.showinfo(master=self._master, message=event.client_data)
            #     self.destroy()
            #     return
            progress.message(str(event.client_data))
        if bg_exec.is_alive():
            def do_check(): self._check_progress(bg_exec, status_queue, progress)
            self._master.after(100, do_check)

    def _do_crop(self, in_dir: Path, out_dir: Path,
                 x: Tuple[int, int], y: Tuple[int, int],
                 status_queue: Queue, progress: Progress) -> None:
        files = []
        for in_file in sorted(in_dir.iterdir()):
            if not in_file.is_file() or not (in_file.suffix in ('.fits', '.fit')):
                continue
            files.append(in_file)

        n_processed = 0
        n_files = len(files)
        for in_file in files:
            if progress.WasCancelled():
                break
            msg = f'Processing file {n_processed + 1} of {n_files}'
            progress.message(n_processed, msg)
            full_out_file = out_dir / in_file.name
            hdu_l = fits.open(in_file)
            header = hdu_l[0].header
            data = hdu_l[0].data
            new_data = data[y[0]:y[1], x[0]:x[1]]
            new_hdu = fits.PrimaryHDU(new_data, header)
            new_hdu.writeto(full_out_file, overwrite=True)
            hdu_l.close()
            n_processed = n_processed + 1



        evt = Event(bgexec.FINISHED, f'Processed {n_processed:<d} file(s).')
        status_queue.put(evt)


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

    def _on_btn(event):
        try:
            dlg = Crop(frame)
            dlg.ShowModal()
        finally:
            dlg.Destroy()

    frame.Bind(wx.EVT_BUTTON, _on_btn, id=id_ref.GetId())
    frame.Show()
    app.MainLoop()
