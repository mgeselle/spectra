from pathlib import Path
from typing import Any, Union, Callable, Iterable, Sequence

import numpy as np
import numpy.typing as npt
import skimage.util as sku
import wx
from astropy.io import fits


def _median_decimate(in_data: npt.NDArray[Any]) -> npt.NDArray[Any]:
    x_dim = int(in_data.shape[1] / 3.0)
    y_dim = int(in_data.shape[0] / 3.0)
    block_view = sku.view_as_blocks(in_data[0:y_dim * 3, 0:x_dim * 3], (3, 3))
    return np.median(block_view, axis=[2,3])


class Dark:
    def __init__(self, bias_path: Union[Path, None], dark_files: Sequence[Path]):
        self._bias = bias_path
        self._darks_by_exposure = dict()
        for dark in dark_files:
            hdu_l = fits.open(dark)
            header = hdu_l[0].header
            if header.count('EXPTIME') != 0:
                exptime = float(header['EXPTIME'])
                self._darks_by_exposure[exptime] = dark
                hdu_l.close()

    def correct(self, input_files: Iterable[Path],
                output_path: Path,
                callback: Union[Callable[[int, str], bool], None] = None,
                budget: int = 0, start_with=0):
        index = start_with
        input_list = list(input_files)
        step = int(budget / len(input_list))
        for in_file in input_list:
            if callback:
                in_name = in_file.name
                msg = f'Processing {in_name}'
                if callback(index, msg):
                    return
            in_hdu_l = fits.open(in_file)
            header = in_hdu_l[0].header
            if header.count('EXPTIME') == 0:
                in_hdu_l.close()
                continue
            exp_time = float(header['EXPTIME'])
            if exp_time in self._darks_by_exposure:
                wx.LogMessage(f'Dark-correcting {in_file.name} using direct method.')
                corrected_data = self._correct_direct(in_hdu_l[0].data, exp_time)
            else:
                wx.LogMessage(f'Dark-correcting {in_file.name} using scaled method.')
                corrected_data = self._correct_scaled(in_hdu_l[0].data, exp_time)
            corrected_data[corrected_data < 0] = 0
            out_file = output_path / in_file.name
            new_hdu = fits.PrimaryHDU(corrected_data, header)
            new_hdu.writeto(out_file, overwrite=True)
            in_hdu_l.close()
            index += step

        if callback:
            callback(start_with + budget, 'Dark correction complete')

    def _correct_direct(self, in_data: npt.NDArray[Any], exp_time: float) -> npt.NDArray[Any]:
        dark = self._darks_by_exposure[exp_time]
        dark_hdu_l = fits.open(dark)
        dark_data = dark_hdu_l[0].data
        result = np.asarray(in_data, dtype=np.float64) - np.asarray(dark_data, np.float64)
        dark_hdu_l.close()
        return result

    def _correct_scaled(self, in_data: npt.NDArray[Any], exp_time: float) -> npt.NDArray[Any]:
        if self._bias is None:
            wx.LogMessage('Cannot apply scaled dark correction: no bias file.')
            return in_data
        with fits.open(self._bias) as bias_hdu_l:
            bias_data = np.asarray(bias_hdu_l[0].data, dtype=np.float64)
        dark_path = self._pick_dark(exp_time)
        if dark_path is not None:
            with fits.open(dark_path) as dark_hdu_l:
                dark_data = np.asarray(dark_hdu_l[0].data, dtype=np.float64) - bias_data
                dark_header = dark_hdu_l[0].header
            scale = exp_time / float(dark_header['EXPTIME'])
            wx.LogMessage(f'Applying dark correction with scale {scale:.3f}.')
            dark_data = dark_data * scale
            result = np.asarray(in_data, dtype=np.float64) - dark_data - bias_data
        else:
            wx.LogMessage(f'No suitable dark file found for exposure time {exp_time:.4f}. Subtracting bias only.')
            result = np.asarray(in_data, dtype=np.float64) - bias_data
        return result

    def _pick_dark(self, exp_time: float) -> Union[Path, None]:
        delta = None
        last_cand_time = None
        for cand_time in sorted(self._darks_by_exposure.keys()):
            if cand_time < exp_time:
                continue
            if last_cand_time is None:
                last_cand_time = cand_time
            new_delta = abs(exp_time - cand_time)
            if delta is not None and new_delta > delta:
                break
            delta = new_delta
            last_cand_time = cand_time
        if last_cand_time is None:
            return None
        return self._darks_by_exposure[last_cand_time]

