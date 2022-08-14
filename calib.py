import astropy.units as u
from astroquery.nist import Nist
from pathlib import Path
import threading
from typing import Sequence, Union, Dict
import wx
import wx.lib.newevent as ne
import wx.lib.intctrl as wxli
from config import Config
from wxutil import size_text_by_chars


ProgressEvent, EVT_ID_PROGRESS = ne.NewEvent()
ErrorEvent, EVT_ID_ERROR = ne.NewEvent()


def _retrieve_lines(name: str, lower: Union[None, int], higher: Union[None, int]) -> Union[None, Sequence[Dict]]:
    lines = [x.strip() for x in name.split(',')]
    # noinspection PyBroadException
    try:
        result = []
        for line in lines:
            line_src = Config.get().get_calib_table(line)
            if line_src is None:
                line_src = Nist.query(3000 * u.AA, 8500 * u.AA, linename=line)
                Config.get().save_calib_table(line, line_src)
            for row in line_src.iterrows('Observed', 'Rel.'):
                try:
                    observed = row[0]
                    if str(observed) == '--':
                        continue
                    rel = int(row[1])
                    if rel < 10:
                        continue
                    if lower is not None and observed < lower:
                        continue
                    if higher is not None and observed > higher:
                        continue
                    result.append({'lam': observed, 'rel': rel, 'name': line})
                except ValueError:
                    continue
        result.sort(key=lambda x: x['lam'])
        return result
    except Exception:
        return None


class CalibConfigurator(wx.Dialog):

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.SetTitle('Calibration Configuration')

        panel = wx.Panel(self)
        ref_label = wx.StaticText(panel, wx.ID_ANY, 'Reference Spectra:')
        self._ref_entry = wx.TextCtrl(panel)
        size_text_by_chars(self._ref_entry, 20)
        lambda_label = wx.StaticText(panel, wx.ID_ANY, u'\u03bb Range [\u00c5]:')
        self._lam_low = wxli.IntCtrl(panel, min=3000, max=8500)
        size_text_by_chars(self._lam_low, 6)
        dash_label = wx.StaticText(panel, wx.ID_ANY, ' .. ')
        self._lam_high = wxli.IntCtrl(panel, min=3000, max=8500)
        size_text_by_chars(self._lam_high, 6)
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
                ref_spectrum = Nist.query(3000 * u.AA, 8500 * u.AA, linename=species)
            except Exception:
                failed.append(species)
            else:
                Config.get().save_calib_table(species, ref_spectrum)
            completion += step

        if failed:
            msg=f'Failed to retrieve: {", ".join(failed)}.'
        else:
            Config.get().set_used_lines(','.join(full_list))
            msg=''
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

    def _on_error(self, event: ErrorEvent):
        self._event_ack.wait()
        with wx.MessageDialog(self, self._error_msg, caption='Retrieval Errors',
                              style=wx.OK | wx.CENTRE | wx.ICON_ERROR) as dlg:
            dlg.ShowModal()


if __name__ == '__main__':
    app = wx.App()
    app.SetAppName('spectra')
    frame = wx.Frame(None, title='Calibration Test')
    pnl = wx.Panel(frame)
    id_ref = wx.NewIdRef()
    cfg_button = wx.Button(pnl, id=id_ref.GetId(), label='Run Config')
    sizer = wx.BoxSizer(wx.VERTICAL)
    sizer.Add(cfg_button, 0, 0, 0)
    pnl.SetSizer(sizer)
    pnl.Fit()
    pnl_sz = pnl.GetBestSize()
    frame.SetClientSize(pnl_sz)

    def on_btn(event:wx.CommandEvent):
        btn = event.GetEventObject()
        btn.Disable()
        if btn == cfg_button:
            dlg = CalibConfigurator(frame)
        else:
            return

        def on_dlg_show(event: wx.ShowEvent):
            if event.IsShown():
                return
            dlg.Destroy()
            btn.Enable()

        dlg.Bind(wx.EVT_SHOW, on_dlg_show)
        dlg.Show()

    frame.Bind(wx.EVT_BUTTON, on_btn)
    frame.Show()
    app.MainLoop()



