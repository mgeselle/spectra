from math import floor, ceil
from os import PathLike
from pathlib import Path
from typing import Union, SupportsInt, SupportsFloat, Iterable, Any

import numpy as np
import numpy.typing as npt
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
    return float(result)


def _move_row(in_row: npt.NDArray[Any], offset: float, x_0: int, out_row: npt.NDArray[Any]):
    for x_target in range(0, out_row.shape[0]):
        x_src0 = int(floor(x_0 + x_target + offset))
        x_src1 = ceil(x_0 + x_target + offset)
        w_0 = 1.0 - (x_0 + x_target + offset - x_src0)
        w_1 = 1.0 - (x_src1 - x_0 - x_target - offset)
        out_row[x_target] =  w_0 * in_row[x_src0] + w_1 * in_row[x_src1]


class Slant:
    def __init__(self, input_dir: [str, bytes, PathLike], calib_basename: str):
        self._input_path = Path(input_dir)
        if not self._input_path.exists():
            raise FileNotFoundError(f"Input directory '{self._input_path}' doesn't exist")
        self._calib = None
        for candidate in self._input_path.glob(calib_basename + '*.*'):
            if candidate.suffix in ('.fits', '.fit'):
                self._calib = candidate
                break
        if self._calib is None:
            raise FileNotFoundError(f"Calibration file '{calib_basename}*.*' not found")
        in_hdu_l = fits.open(self._calib)
        data = in_hdu_l[0].data
        y_cent = int(data.shape[0] / 2)
        x_cent = int(data.shape[1] / 2)
        peak_x = np.empty(data.shape[0], np.float32)
        peak_x[y_cent] = _find_next_peak(x_cent, data[y_cent, :])
        for y in range(y_cent + 1, data.shape[0]):
            peak_x[y] = _find_next_peak(peak_x[y - 1], data[y, :])
        for y in range(y_cent - 1, -1, -1):
            peak_x[y] = _find_next_peak(peak_x[y + 1], data[y, :])
        peak_x = peak_x - peak_x[y_cent]
        peak_y = np.arange(data.shape[0])
        self._fit = Polynomial.fit(peak_y, peak_x, deg=2)
        # noinspection PyCallingNonCallable
        x_off_0 = self._fit(0)
        # noinspection PyCallingNonCallable
        x_off_1 = self._fit(data.shape[0] - 1)
        if x_off_0 > x_off_1:
            self._x_0 = int(-floor(x_off_1))
            self._dim_x = data.shape[1] - self._x_0 - int(ceil(x_off_0))
        elif x_off_0 < x_off_1:
            self._x_0 = int(-floor(x_off_0))
            self._dim_x = data.shape[1] - int(ceil(x_off_1)) - self._x_0

        in_hdu_l.close()

    def apply(self, basenames: Iterable[str], output_dir: Union[str, bytes, PathLike] = None, prefix: str = ''):
        if output_dir is None:
            output_path = self._input_path
        else:
            output_path = Path(output_dir)
        if not output_path.exists():
            raise FileNotFoundError("Output directory doesn't exist")
        input_files = []
        for candidate in self._input_path.iterdir():
            if not candidate.is_file() or candidate.suffix not in ('.fits', '.fit'):
                continue
            for basename in basenames:
                if candidate.name.startswith(basename):
                    input_files.append(candidate)
                    break
        for input_file in input_files:
            in_hdu_l = fits.open(input_file)
            header = in_hdu_l[0].header
            data = in_hdu_l[0].data
            new_data = np.empty((data.shape[0], self._dim_x), data.dtype)
            for y in range(0, data.shape[0]):
                # noinspection PyCallingNonCallable
                offset = self._fit(y)
                _move_row(data[y, :], offset, self._x_0, new_data[y, :])
            out_hdu = fits.PrimaryHDU(new_data, header)
            out_hdu.writeto(output_path / (prefix + input_file.name), overwrite=True)
            in_hdu_l.close()


if __name__ == '__main__':
    slt = Slant('/home/mgeselle/astrowrk/spectra/reduced', 'flt-rot-drk-Neon')
    slt.apply(('flt-rot-drk-Neon',), prefix='slt-')