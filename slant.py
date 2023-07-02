from math import floor, ceil
from pathlib import Path
from typing import Union, SupportsInt, SupportsFloat, Iterable, Any

import numpy as np
import numpy.typing as npt
import wx
from astropy.io import fits
from numpy.polynomial import Polynomial
from scipy.signal import find_peaks


def _find_next_peak(x_ref: Union[SupportsInt, SupportsFloat], x_data: npt.NDArray[Any]):
    peaks, _ = find_peaks(x_data, prominence=2000)
    result = None
    last_delta = None
    for x in peaks:
        new_delta = abs(x - x_ref)
        if last_delta is None or new_delta < last_delta:
            last_delta = new_delta
            result = x
        elif new_delta > last_delta:
            break
    if result is None:
        return -1.0
    else:
        return float(result)


def _move_row(in_row: npt.NDArray[Any], offset: float, x_0: int, out_row: npt.NDArray[Any]):
    for x_target in range(0, out_row.shape[0]):
        x_src0 = int(floor(x_0 + x_target + offset))
        x_src1 = ceil(x_0 + x_target + offset)
        if x_src1 >= in_row.size or x_src0 > in_row.size:
            out_row[x_target] = 0
        else:
            w_0 = 1.0 - (x_0 + x_target + offset - x_src0)
            w_1 = 1.0 - (x_src1 - x_0 - x_target - offset)
            out_row[x_target] =  w_0 * in_row[x_src0] + w_1 * in_row[x_src1]


class Slant:
    def __init__(self, calib: Path):
        in_hdu_l = fits.open(calib)
        data = in_hdu_l[0].data
        y_cent = int(data.shape[0] / 2)
        x_cent = int(data.shape[1] / 2)
        peak_x = np.empty(data.shape[0], np.float32)
        peak_x[y_cent] = -1.0
        while peak_x[y_cent] == -1.0 and x_cent < data.shape[1] - 10:
            peak_x[y_cent] = _find_next_peak(x_cent, data[y_cent, :])
            if peak_x[y_cent] == -1.0:
                x_cent = x_cent + 10
        if peak_x[y_cent] == -1.0:
            self._fit = None
            wx.LogMessage('Slant: No peak found in calibration image.')
            return
        y_hi = y_cent
        for y in range(y_cent + 1, data.shape[0]):
            peak_x[y] = _find_next_peak(peak_x[y - 1], data[y, :])
            if peak_x[y] == -1.0:
                y_hi = y - 1
                break
            y_hi = y
        y_lo = y_cent
        for y in range(y_cent - 1, -1, -1):
            peak_x[y] = _find_next_peak(peak_x[y + 1], data[y, :])
            if peak_x[y] == -1.0:
                y_lo = y + 1
                break
            y_lo = y
        if y_hi - y_lo < 4:
            wx.LogMessage('Too few point for slant fit.')
            self._fit = None
            return
        wx.LogMessage(f'y range for slant fit: {y_lo}..{y_hi} of {data.shape[0]}.')
        peak_x = peak_x - peak_x[y_cent]
        peak_x = peak_x[y_lo:y_hi + 1]
        peak_y = np.arange(y_lo, y_hi + 1)
        self._fit = Polynomial.fit(peak_y, peak_x, deg=2)
        wx.LogMessage(f'Fitted polynom {self._fit} for slant correction.')
        # noinspection PyCallingNonCallable
        x_off_0 = self._fit(0)
        # noinspection PyCallingNonCallable
        x_off_1 = self._fit(data.shape[0] - 1)
        wx.LogMessage(f'Fitted offsets at boundaries are {x_off_0:.0f}, {x_off_1:.0f}')
        if x_off_0 > x_off_1:
            self._x_0 = int(-floor(x_off_1))
            self._dim_x = data.shape[1] - self._x_0 - int(ceil(x_off_0))
        elif x_off_0 < x_off_1:
            self._x_0 = int(-floor(x_off_0))
            self._dim_x = data.shape[1] - int(ceil(x_off_1)) - self._x_0

        in_hdu_l.close()

    def apply(self, input_files: Iterable[Path], output_path: Path):
        if not output_path.exists():
            raise FileNotFoundError("Output directory doesn't exist")
        for input_file in input_files:
            in_hdu_l = fits.open(input_file)
            header = in_hdu_l[0].header
            data = in_hdu_l[0].data
            if self._fit is None:
                new_data = data
            else:
                new_data = np.empty((data.shape[0], self._dim_x), data.dtype)
                for y in range(0, data.shape[0]):
                    # noinspection PyCallingNonCallable
                    offset = self._fit(y)
                    _move_row(data[y, :], offset, self._x_0, new_data[y, :])
            out_hdu = fits.PrimaryHDU(new_data, header)
            out_hdu.writeto(output_path / input_file.name, overwrite=True)
            in_hdu_l.close()


if __name__ == '__main__':
    in_dir = Path.home() / 'astrowrk/spectra/reduced'
    out_dir = in_dir.parent / 'slant'
    out_dir.mkdir(exist_ok=True)
    in_file = next(f for f in in_dir.glob('flt-rot-drk-Neon*.*'))
    slt = Slant(in_file)
    slt.apply([in_file], out_dir)
