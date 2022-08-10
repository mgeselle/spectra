from astropy.io import fits
import functools
from math import asin, sqrt, degrees
import numpy.typing as npt
from os import PathLike
from pathlib import Path
from scipy.ndimage import rotate
from scipy.signal import find_peaks
from typing import Union, Any, Iterable, Callable


def _find_peak(column: npt.NDArray[Any]):
    min_dist = int(column.shape[0] / 10)
    peaks, _ = find_peaks(column, distance=min_dist)
    peak_idx = None
    max_peak = None
    for index in peaks:
        if peak_idx is None or column[index] > max_peak:
            peak_idx = index
            max_peak = column[index]
    return peak_idx


class Rotate:
    def __init__(self, pgm_file: Path):
        in_hdu_l = fits.open(pgm_file)
        data = in_hdu_l[0].data
        x_dim = data.shape[1]
        x_low = int(x_dim / 4)
        x_hi = x_low * 3

        peak_low = _find_peak(data[:, x_low])
        peak_hi = _find_peak(data[:, x_hi])
        in_hdu_l.close()

        self._angle = degrees(asin((peak_hi - peak_low) / sqrt((x_hi - x_low)**2 + (peak_hi - peak_low)**2)))

    def rotate(self, input_files: Iterable[Path], output_dir: Path,
               callback: Union[Callable[[int, str], bool], None] = None,
               budget=100, start_with=0):
        index = start_with
        num_files = functools.reduce(lambda x, y: x + 1, input_files, 0)
        step = int(budget / num_files)
        for input_file in input_files:
            if callback:
                if callback(index, f'Rotating {input_file.name}.'):
                    return
            self._do_rotate(input_file, output_dir)
            index += step

        if callback:
            callback(start_with + budget, f'Rotated {num_files} file(s) by {self._angle:.2f} degrees.')

    def _do_rotate(self, input_file: Path, output_path: Path):
        in_hdu_l = fits.open(input_file)
        header = in_hdu_l[0].header
        data = in_hdu_l[0].data
        data_new = rotate(data, self._angle, reshape=False)
        hdu_new = fits.PrimaryHDU(data_new, header)
        output_file = output_path / input_file.name
        hdu_new.writeto(output_file, overwrite=True)
        in_hdu_l.close()
