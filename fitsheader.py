import astropy.io.fits as fits
import sys
import wx

from pathlib import Path


class FitsHeaderDialog(wx.Dialog):

    def __init__(self, parent: wx.Window, file: Path, style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER, **kwargs):
        super().__init__(parent, style=style, **kwargs)
        self.SetTitle(f'FITS Header of {file}')

        list_ctrl = wx.ListCtrl(self, style=wx.LC_REPORT)
        name_header = 'Attribute Name'
        name_width = list_ctrl.GetFullTextExtent('M' * len(name_header))[0]
        list_ctrl.InsertColumn(0, name_header, width=name_width)
        # Max length of a header card is 80 chars
        value_width = list_ctrl.GetFullTextExtent('M' * 80)[0]
        list_ctrl.InsertColumn(1, 'Attribute Value', width=value_width)

        with fits.open(file) as hdu_l:
            header = hdu_l[0].header
        row_idx = 0
        for item_key in header.keys():
            if item_key in ('HISTORY', 'COMMENT'):
                for line in header[item_key]:
                    FitsHeaderDialog._insert_label_and_text(list_ctrl, row_idx, item_key, line)
                    row_idx += 1
            else:
                FitsHeaderDialog._insert_label_and_text(list_ctrl, row_idx, item_key, header[item_key])
                row_idx += 1

        vbox = wx.BoxSizer(wx.VERTICAL)
        vbox.Add(list_ctrl, 1, wx.EXPAND, 0)

        btn_sizer = self.CreateSeparatedButtonSizer(wx.OK)
        vbox.Add(btn_sizer, 0, wx.EXPAND | wx.TOP | wx.BOTTOM | wx.LEFT | wx.RIGHT, 10)
        self.SetSizer(vbox)

        self.Layout()
        sz = self.GetBestSize()
        self.SetSizeHints(sz.GetWidth(), int(sz.GetWidth() / 2))

    @staticmethod
    def _insert_label_and_text(ctrl: wx.ListCtrl, row_idx: int, label: str, text: str):
        ctrl.InsertItem(row_idx, label)
        ctrl.SetItem(row_idx, 1, str(text))


if __name__ == '__main__':
    import wxutil
    app = wx.App()
    app.SetAppName('spectra')
    frame = wx.Frame(None, title='FITS Header Test')
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
        file = wxutil.select_file(frame)
        if not file:
            button.Enable()
            return

        file_path = Path(file)
        dlg = FitsHeaderDialog(frame, file_path)

        def on_dlg_show(evt: wx.ShowEvent):
            if not evt.IsShown():
                dlg.Destroy()
                button.Enable()

        dlg.Bind(wx.EVT_SHOW, on_dlg_show)
        dlg.Show()

    frame.Bind(wx.EVT_BUTTON, _on_btn, id=id_ref.GetId())
    frame.Show()
    app.MainLoop()
