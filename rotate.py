from astropy.io import fits
from math import asin, sqrt, degrees
import numpy.typing as npt
from os import PathLike
from pathlib import Path
from scipy.ndimage import rotate
from scipy.signal import find_peaks
from typing import Union, Any, Iterable


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
    def __init__(self, in_dir: Union[str, bytes, PathLike], in_file_basename: str):
        input_path = None
        for cand in sorted(Path(in_dir).glob(in_file_basename + '*.*')):
            if cand.suffix in ('.fits', '.fts'):
                input_path = cand
                break
        if input_path is None:
            raise FileNotFoundError(f'File matching {in_file_basename} not found in {in_dir}')
        in_hdu_l = fits.open(input_path)
        data = in_hdu_l[0].data
        x_dim = data.shape[1]
        x_low = int(x_dim / 4)
        x_hi = x_low * 3

        peak_low = _find_peak(data[:, x_low])
        peak_hi = _find_peak(data[:, x_hi])
        in_hdu_l.close()

        self._angle = degrees(asin((peak_hi - peak_low) / sqrt((x_hi - x_low)**2 + (peak_hi - peak_low)**2)))

    def rotate(self, input_dir: Union[str, bytes, PathLike], basenames: Iterable[str],
               output_dir: Union[str, bytes, PathLike], prefix: Union[str, None] = None):
        input_path = Path(input_dir)
        if not input_path.exists():
            raise FileNotFoundError(f'Input directory {input_path} does not exist')
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        if prefix is None:
            pref = ''
        else:
            pref = prefix

        for input_file in sorted(input_path.iterdir()):
            if not input_file.is_file() or input_file.suffix not in ('.fits', '.fit'):
                continue
            for basename in basenames:
                if input_file.name.startswith(basename):
                    self._do_rotate(input_file, output_path, pref)
                    break

    def _do_rotate(self, input_file: Path, output_path: Path, prefix: str):
        in_hdu_l = fits.open(input_file)
        header = in_hdu_l[0].header
        data = in_hdu_l[0].data
        data_new = rotate(data, self._angle, reshape=False)
        hdu_new = fits.PrimaryHDU(data_new, header)
        output_file = output_path / (prefix + input_file.name)
        hdu_new.writeto(output_file, overwrite=True)
        in_hdu_l.close()
