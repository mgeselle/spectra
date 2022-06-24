from astropy.io import fits
import numpy.typing as npt
from os import PathLike
from pathlib import Path
from typing import Any, Union, Callable


class Dark:
    def __init__(self, master_dir: Union[str, bytes, PathLike], bias_basename: str, dark_basename: str):
        master_path = Path(master_dir)
        for bias in master_path.glob(bias_basename + '*.*'):
            if bias.suffix in ('.fits', '.fit'):
                self._bias = bias
                break
        self._darks_by_exposure = dict()
        for dark in master_path.glob(dark_basename + '*.*'):
            if dark.suffix not in ('.fits', '.fit'):
                continue
            hdu_l = fits.open(dark)
            header = hdu_l[0].header
            if header.count('EXPTIME') != 0:
                exptime = float(header['EXPTIME'])
                self._darks_by_exposure[exptime] = dark
                hdu_l.close()

    def correct(self, input_dir: Union[str, bytes, PathLike], output_dir: Union[str, bytes, PathLike, None] = None,
                prefix: Union[str, None] = None, callback: Union[Callable[[str], None], None] = None):
        input_path = Path(input_dir)
        if output_dir is None:
            output_path = input_path
        else:
            output_path = Path(output_dir)
        exclusions = []
        if input_path == self._bias.parent:
            exclusions.append(self._bias)
            exclusions.extend(self._darks_by_exposure.values())

        if prefix is None:
            pref = ''
        else:
            pref = prefix

        for in_file in sorted(input_path.iterdir()):
            if not in_file.is_file() or in_file.suffix not in ('.fits', '.fit'):
                continue
            if in_file in exclusions:
                continue
            if callback is not None:
                in_name = in_file.name
                msg = f'Processing {in_name}'
                callback(msg)
            in_hdu_l = fits.open(in_file)
            header = in_hdu_l[0].header
            if header.count('EXPTIME') == 0:
                in_hdu_l.close()
                continue
            exp_time = float(header['EXPTIME'])
            if exp_time in self._darks_by_exposure:
                corrected_data = self._correct_direct(in_hdu_l[0].data, exp_time)
            else:
                corrected_data = self._correct_scaled(in_hdu_l[0].data, exp_time)
            corrected_data[corrected_data < 0] = 0
            out_file = output_path / (pref + in_file.name)
            new_hdu = fits.PrimaryHDU(corrected_data, header)
            new_hdu.writeto(out_file, overwrite=True)
            in_hdu_l.close()

    def _correct_direct(self, in_data: npt.NDArray[Any], exp_time: float) -> npt.NDArray[Any]:
        dark = self._darks_by_exposure[exp_time]
        dark_hdu_l = fits.open(dark)
        dark_data = dark_hdu_l[0].data
        result = in_data - dark_data
        dark_hdu_l.close()
        return result

    def _correct_scaled(self, in_data: npt.NDArray[Any], exp_time: float) -> npt.NDArray[Any]:
        bias_hdu_l = fits.open(self._bias)
        bias_data = bias_hdu_l[0].data
        dark_path = self._pick_dark(exp_time)
        dark_hdu_l = fits.open(dark_path)
        dark_data = dark_hdu_l[0].data - bias_data
        dark_header = dark_hdu_l[0].header
        scale = exp_time / float(dark_header['EXPTIME'])
        dark_data = dark_data * scale
        result = in_data - dark_data - bias_data
        dark_hdu_l.close()
        bias_hdu_l.close()
        return result

    def _pick_dark(self, exp_time: float) -> Path:
        delta = None
        last_cand_time = None
        for cand_time in sorted(self._darks_by_exposure.keys()):
            new_delta = abs(exp_time - cand_time)
            if delta is not None and new_delta > delta:
                break
            delta = new_delta
            last_cand_time = cand_time
        return self._darks_by_exposure[last_cand_time]
