import numpy as np
import numpy.typing as npt
import wx

from astropy.io import fits
from dataclasses import dataclass
from numpy.polynomial import Polynomial
from pathlib import Path
from typing import Union, Any, Tuple, Sequence

import matplotlib.pyplot as plt


@dataclass(frozen=True)
class FlatParam:
    flat: npt.NDArray[Any]
    x_lo: int
    y_lo: int
    x_hi: int
    y_hi: int


def auto_flat(flat_path: Path, input_files: Union[Path, Sequence[Path]], output_path: Path):
    flat_param = _compute_flat(flat_path)
    apply(flat_param, input_files, output_path)


def apply(param: FlatParam, input_files: Union[Path, Sequence[Path]], output_path: Path):
    if isinstance(input_files, Path):
        input_files = (input_files, )

    for input_file in input_files:
        in_hdu_l = fits.open(input_file)
        header = in_hdu_l[0].header
        data = in_hdu_l[0].data
        if param.x_lo == 0 and param.x_hi == 0 and param.y_lo == param.y_hi:
            out_data = data
        else:
            out_data = data[param.y_lo:param.y_hi, param.x_lo:param.x_hi]
        out_data = out_data / param.flat
        in_hdu_l.close()
        out_hdu = fits.PrimaryHDU(out_data, header)
        out_hdu.writeto(output_path / input_file.name, overwrite=True)


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


def _compute_flat(flat_path: Path) -> FlatParam:
    flat_hdu_l = fits.open(flat_path)
    data = flat_hdu_l[0].data
    x_lo, x_hi = _find_shortest_black(data[0, :])
    y_lo, y_hi = _find_shortest_black(data[:, 0])
    if x_lo == 0 and x_hi == 0 and y_lo == 0 and y_hi == 0:
        wx.LogMessage('Using full data for flat correction.')
        cropped_data = data
    else:
        wx.LogMessage(f'Cropping data to ({x_lo},{y_lo}), ({x_hi},{y_hi}) for flat correction.')
        cropped_data = data[y_lo:y_hi, x_lo:x_hi]
    flat_hdu_l.close()

    fitted = np.empty(cropped_data.shape, dtype=np.float64)
    xdata = np.arange(0, cropped_data.shape[1])
    for i in range(0, cropped_data.shape[0]):
        poly = Polynomial.fit(xdata, cropped_data[i, :], deg=5)
        # noinspection PyCallingNonCallable
        fitted[i, :] = poly(xdata)
        # plt.plot(xdata, cropped_data[i, :], 'b-')
        # plt.plot(xdata, fitted[i, :], 'r-')
        # plt.show()
    mean_signal = np.mean(cropped_data, axis=0)
    cropped_data = cropped_data / fitted
    x_min = 0
    for x in range(0, mean_signal.shape[0]):
        if mean_signal[x] > 10000:
            x_min = x
            break
    if x_min != 0:
        for y in range(0, cropped_data.shape[0]):
            cropped_data[y, :] = cropped_data[y, :] / cropped_data[y, x_min]
            cropped_data[y, 0:x_min] = 1.0

    return FlatParam(cropped_data, x_lo, y_lo, x_hi, y_hi)
