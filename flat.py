from astropy.io import fits
from dataclasses import dataclass
import numpy as np
import numpy.typing as npt
from pathlib import Path
from scipy.interpolate import CubicSpline
from typing import Union, Any, Tuple, Sequence
import wx
from specview import Specview


@dataclass(frozen=True)
class FlatParam:
    flat: npt.NDArray[Any]
    x_lo: int
    y_lo: int
    x_hi: int
    y_hi: int


class FlatDialog(wx.Dialog):
    def __init__(self, parent: wx.Window, flat_file: Path, **kwargs):
        super().__init__(parent, **kwargs)
        self.SetTitle('Flat Spectrum')

        self._specview = Specview(self)
        self._btn_sizer = self.CreateSeparatedButtonSizer(wx.OK | wx.CANCEL)
        vbox = wx.BoxSizer(wx.VERTICAL)
        vbox.Add(self._specview, 1, wx.ALL | wx.EXPAND, border=10)
        vbox.Add(self._btn_sizer, 0, wx.ALL | wx.EXPAND, border=10)

        self.SetSizer(vbox)
        vbox.SetSizeHints(self)
        self.Fit()

        self.Bind(wx.EVT_BUTTON, self._on_btn, id=wx.ID_OK)
        self.Bind(wx.EVT_BUTTON, self._on_btn, id=wx.ID_CANCEL)

        self._result = None

        flat_hdu_l = fits.open(flat_file)
        data = flat_hdu_l[0].data
        self._x_lo, self._x_hi = FlatDialog._find_shortest_black(data[0, :])
        self._y_lo, self._y_hi = FlatDialog._find_shortest_black(data[:, 0])
        self._cropped_data = data[self._y_lo:self._y_hi, self._x_lo:self._x_hi]
        flat_hdu_l.close()

        self._summed = self._cropped_data.sum(axis=0)
        self._specview.add_spectrum(self._summed)
        self._pick_xdata = np.array([0, self._summed.shape[0] - 1])
        pick_ydata = np.array([self._summed[0], self._summed[-1]])
        self._specview.start_picking(self._on_pick)
        self._specview.set_pick_data(self._pick_xdata, pick_ydata)
        cs = CubicSpline(self._pick_xdata, pick_ydata)
        spline_y = np.fromfunction(cs, self._summed.shape)
        # noinspection PyTypeChecker
        self._spline = self._specview.add_spectrum(spline_y, fmt='--m')

    def _on_btn(self, evt: wx.CommandEvent):
        if evt.GetId() == wx.ID_OK:
            flat = np.empty(self._cropped_data.shape)
            for i in range(0, self._cropped_data.shape[0]):
                cs_y = []
                for cs_x in self._pick_xdata:
                    cs_y.append(self._cropped_data[i, cs_x])
                cs = CubicSpline(self._pick_xdata, np.array(cs_y))
                sp_flat = np.fromfunction(cs, self._summed.shape)
                flat[i, :] = sp_flat
            flat = self._cropped_data / flat
            self._result = FlatParam(flat, self._x_lo, self._y_lo, self._x_hi, self._y_hi)
            if self.IsModal():
                self.EndModal(wx.OK)
        if self.IsModal():
            self.EndModal(wx.CANCEL)
        else:
            self.Show(False)

    def _on_pick(self, x_picked, is_delete):
        if is_delete:
            delta = None
            x_idx = None
            for i in range(0, self._pick_xdata.shape[0]):
                new_delta = abs(self._pick_xdata[i] - x_picked)
                if delta is None or new_delta < delta:
                    delta = new_delta
                    x_idx = i
                elif new_delta > delta:
                    break
            if x_idx == 0 or x_idx == self._summed.shape[0]:
                return
            self._pick_xdata = np.delete(self._pick_xdata, x_idx)
        else:
            self._pick_xdata = np.append(self._pick_xdata, round(x_picked))
            self._pick_xdata.sort()
        y_picked = []
        for xp in self._pick_xdata:
            y_picked.append(self._summed[xp])
        pick_ydata = np.array(y_picked)
        self._specview.set_pick_data(self._pick_xdata, pick_ydata)
        cs = CubicSpline(self._pick_xdata, pick_ydata)
        spline_y = np.fromfunction(cs, self._summed.shape)
        # noinspection PyTypeChecker
        self._specview.set_spectrum_data(self._spline, spline_y)

    @staticmethod
    def _find_shortest_black(row_or_col: npt.NDArray[Any]) -> Tuple[int, int]:
        if row_or_col[0] != 0:
            return 0, 0
        i_low = 0
        for i in range(0, row_or_col.shape[0]):
            if row_or_col[i] != 0:
                i_low = i
                break
        i_hi = row_or_col.shape[0]
        for i in range(row_or_col.shape[0] - 1, 0, -1):
            if row_or_col[i] != 0:
                i_hi = i
                break

        if row_or_col.shape[0] - i_hi < i_low:
            return row_or_col.shape[0] - i_hi, i_hi

        return i_low, row_or_col.shape[0] - i_low

    @property
    def result(self):
        return self._result


def apply(param: FlatParam, input_files: Union[Path, Sequence[Path]], output_path: Path):
    if isinstance(input_files, Path):
        input_files = (input_files, )

    for input_file in input_files:
        in_hdu_l = fits.open(input_file)
        header = in_hdu_l[0].header
        data = in_hdu_l[0].data
        out_data = data[param.y_lo:param.y_hi, param.x_lo:param.x_hi]
        out_data = out_data / param.flat
        in_hdu_l.close()
        out_hdu = fits.PrimaryHDU(out_data, header)
        out_hdu.writeto(output_path / input_file.name, overwrite=True)


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
        in_dir = Path.home() / 'astrowrk/spectra/dark'
        flat_file = next(f for f in in_dir.glob('rot-drk-flat*.*'))
        dlg = FlatDialog(frame, flat_file)

        def on_dlg_show(evt: wx.ShowEvent):
            if not evt.IsShown():
                flat_param = dlg.result
                dlg.Destroy()
                button.Enable()
                if flat_param:
                    print(flat_param)

        dlg.Bind(wx.EVT_SHOW, on_dlg_show)
        dlg.Show()

    frame.Bind(wx.EVT_BUTTON, _on_btn, id=id_ref.GetId())
    frame.Show()
    app.MainLoop()
