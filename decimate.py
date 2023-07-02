from pathlib import Path
from typing import Any, Union, Callable, Iterable

import numpy as np
import numpy.typing as npt
import skimage.util as sku
from astropy.io import fits


def decimate(input_files: Iterable[Path],
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
        out_data = _median_decimate(in_hdu_l[0].data)
        out_hdu = fits.PrimaryHDU(out_data, header)
        out_hdu.writeto(output_path / in_file.name, overwrite=True)


def _median_decimate(in_data: npt.NDArray[Any]) -> npt.NDArray[Any]:
    x_dim = int(in_data.shape[1] / 3.0)
    y_dim = int(in_data.shape[0] / 3.0)
    block_view = sku.view_as_blocks(in_data[0:y_dim * 3, 0:x_dim * 3], (3, 3))
    return np.median(block_view, axis=[2, 3])
