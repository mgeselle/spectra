from astropy.io import fits
import numpy as np
import numpy.typing as npt
from os import PathLike
from pathlib import Path
from scipy.interpolate import CubicSpline
import tkinter as tk
import tkinter.ttk as ttk
from typing import Union, Any, Tuple, Iterable
from specview import Specview
from tkutil import center_on_parent


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


class Flat(tk.Toplevel):
    def __init__(self, master: Union[tk.Tk, tk.Toplevel], input_dir: Union[str, bytes, PathLike], flat_basename: str):
        super().__init__(master)
        dpi = master.winfo_fpixels('1i')
        w = int(5 * dpi) + 10
        h = int(4 * dpi) + 50
        self.configure(width=w, height=h)

        top = ttk.Frame(self, relief=tk.RAISED)
        top.pack(side=tk.TOP, fill=tk.BOTH)
        self._specview = Specview(top)
        self._specview.pack(side=tk.TOP, fill=tk.BOTH, padx=10, pady=10)

        bottom = ttk.Frame(self, relief=tk.RAISED)
        bottom.pack(side=tk.TOP, fill=tk.X)
        self._status = tk.IntVar()
        self._status.set(0)
        ok_button = ttk.Button(bottom, text='OK', command=lambda: self._status.set(1))
        ok_button.pack(side=tk.LEFT, expand=True, pady=20)
        cancel_button = ttk.Button(bottom, text='Cancel', command=lambda: self._status.set(2))
        cancel_button.pack(side=tk.LEFT, expand=True, pady=20)

        center_on_parent(master, self)
        self.resizable(width=True, height=False)

        flat_file = None
        self._input_path = Path(input_dir)
        for candidate in sorted(self._input_path.glob(flat_basename + '*.*')):
            if candidate.is_file() and candidate.suffix in ('.fits', '.fit'):
                flat_file = candidate
                break
        if flat_file is None:
            raise FileNotFoundError(f'Flat frame {flat_basename} not found in {input_dir}')
        flat_hdu_l = fits.open(flat_file)
        data = flat_hdu_l[0].data
        self._x_lo, self._x_hi = _find_shortest_black(data[0, :])
        self._y_lo, self._y_hi = _find_shortest_black(data[:, 0])
        self._cropped_data = data[self._y_lo:self._y_hi, self._x_lo:self._x_hi]
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

        self.wait_variable(self._status)
        self.wm_withdraw()
        if self._status.get() == 2:
            self._flat = self._cropped_data / self._cropped_data
        else:
            self._flat = np.empty(self._cropped_data.shape)
            for i in range(0, self._cropped_data.shape[0]):
                cs_y = []
                for cs_x in self._pick_xdata:
                    cs_y.append(self._cropped_data[i, cs_x])
                cs = CubicSpline(self._pick_xdata, np.array(cs_y))
                sp_flat = np.fromfunction(cs, self._summed.shape)
                self._flat[i, :] = sp_flat
            self._flat = self._cropped_data / self._flat
        flat_hdu_l.close()
        self._cropped_data = None
        self._summed = None
        self._pick_xdata = None

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

    def apply(self, basenames: Iterable[str], output_dir: Union[str, bytes, PathLike] = None,
              prefix: str = 'flt-'):
        if output_dir is None:
            output_path = self._input_path
        else:
            output_path = Path(output_dir)

        for candidate in self._input_path.iterdir():
            if not candidate.is_file() or candidate.suffix not in ('.fits', '.fit'):
                continue
            for basename in basenames:
                if candidate.name.startswith(basename):
                    in_hdu_l = fits.open(candidate)
                    header = in_hdu_l[0].header
                    data = in_hdu_l[0].data
                    out_data = data[self._y_lo:self._y_hi, self._x_lo:self._x_hi]
                    out_data = out_data / self._flat
                    in_hdu_l.close()
                    out_hdu = fits.PrimaryHDU(out_data, header)
                    out_hdu.writeto(output_path / (prefix + candidate.name), overwrite=True)
                    break


if __name__ == '__main__':
    main = tk.Tk()
    main.wm_title("Spectra")
    main.eval('tk::PlaceWindow . center')

    def run_flat():
        flt = Flat(main, '/home/mgeselle/astrowrk/spectra/dark', 'rot-drk-flat')
        flt.apply(('rot-drk-flat'))

    button = ttk.Button(text='Flat', command=run_flat)
    button.pack(expand=True)

    tk.mainloop()




