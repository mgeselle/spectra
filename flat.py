import numpy as np
import numpy.typing as npt

from astropy.io import fits
from dataclasses import dataclass
from numpy.polynomial import Polynomial
from pathlib import Path
from typing import Union, Any, Tuple, Sequence


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
    cropped_data = data[y_lo:y_hi, x_lo:x_hi]
    flat_hdu_l.close()

    xdata = np.arange(0, cropped_data.shape[1])
    fitted = np.empty(cropped_data.shape, dtype=np.float64)
    for i in range(0, cropped_data.shape[0]):
        poly = Polynomial.fit(xdata, cropped_data[i, :], deg=4)
        # noinspection PyCallingNonCallable
        fitted[i, :] = poly(xdata)
    cropped_data = cropped_data - fitted
    min_d = np.min(cropped_data)
    if min_d < 0:
        cropped_data = cropped_data + min_d
    cropped_data = cropped_data / np.max(cropped_data)
    return FlatParam(cropped_data, x_lo, y_lo, x_hi, y_hi)
