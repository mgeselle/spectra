from astropy.io import fits
import numpy as np
import numpy.ma as ma
from numpy.polynomial import Polynomial
import numpy.typing as npt
from os import PathLike
from pathlib import Path
from time import time
from typing import Union, Tuple, Sequence, Any, Callable
from config import config, CameraConfig
from util import find_input_files

import tkinter as tk
from specview import Specview


def simple(input_dir: Union[str, bytes, PathLike], input_basename: str,
           limits: Union[Tuple[int, int],  Sequence[int]],
           output_dir: Union[None, str, bytes, PathLike] = None, prefix=''):
    input_files = find_input_files(input_dir, input_basename)
    headers = []
    out_data = None
    for i in range(len(input_files)):
        in_hdu_l = fits.open(input_files[i])
        headers.append(in_hdu_l[0].header)
        data: npt.NDArray[Any] = in_hdu_l[0].data
        if len(limits) != 2:
            raise ValueError('limits have wrong length')
        lower, upper = sorted(limits)
        if lower < 0 or upper > data.shape[0]:
            raise ValueError('limits are out of bounds')
        if out_data is None:
            out_data = np.empty((len(input_files), data.shape[1]), dtype=np.float32)
        spectrum = np.sum(data[lower:upper, :], axis=0, dtype=np.float32)
        in_hdu_l.close()
        out_data[i] = spectrum[:]
    out_spectrum = np.mean(out_data, axis=0)
    out_name = prefix + input_basename
    if not out_name.endswith('.fits') and not out_name.endswith('.fit'):
        out_name = out_name + input_files[0].suffix
    out_hdu = fits.PrimaryHDU(out_spectrum, headers[0])
    if output_dir is None:
        output_file = input_files[0].parent / out_name
    else:
        output_file = Path(output_dir) / out_name
    out_hdu.writeto(output_file, overwrite=True)


def optimal(input_dir: Union[str, bytes, PathLike], input_basename: str,
            config_name: str, output_dir: Union[None, str, bytes, PathLike] = None, prefix='',
            callback: Union[None, Callable[[str], None]] = None) -> Tuple[int, int]:
    input_files = find_input_files(input_dir, input_basename)
    cam_cfg = config.get_camera_config(config_name)
    headers = []
    out_data = None
    d_low = None
    d_high = None
    for i in range(len(input_files)):
        if callback is not None:
            msg = f'Extracting spectrum from {input_files[i]}.'
            callback(msg)
        in_hdu_l = fits.open(input_files[i])
        data = in_hdu_l[0].data
        headers.append(in_hdu_l[0].header)
        if out_data is None:
            out_data = np.empty((len(input_files), data.shape[1]))
            d_low = data.shape[0]
            d_high = 0
        spectrum, n_d_low, n_d_high = _optimal(data, cam_cfg, callback)
        in_hdu_l.close()
        out_data[i] = spectrum[:]
        if n_d_low < d_low:
            d_low = n_d_low
        if n_d_high > d_high:
            d_high = n_d_high

    out_spectrum = np.mean(out_data, axis=0)
    out_name = prefix + input_basename
    if not out_name.endswith('.fits') and not out_name.endswith('.fit'):
        out_name = out_name + input_files[0].suffix
    out_hdu = fits.PrimaryHDU(out_spectrum, headers[0])
    if output_dir is None:
        output_file = input_files[0].parent / out_name
    else:
        output_file = Path(output_dir) / out_name
    out_hdu.writeto(output_file, overwrite=True)
    return d_low, d_high


def _optimal(data: npt.NDArray[Any], cam_cfg: CameraConfig,
             callback: Union[None, Callable[[str], None]]) -> Tuple[npt.NDArray[Any], int, int]:
    before = time()
    d_low, d_high, sky_low, sky_high = _find_sky_and_signal(data)
    if callback is not None:
        elapsed = time() - before
        msg = f'Detected signal in {elapsed:5.3f}s. Signal: {d_low}..{d_high}, sky: 0..{sky_low}, {sky_high}..'
        callback(msg)

    before = time()
    var_img = np.abs(data) / cam_cfg.gain + (cam_cfg.ron / cam_cfg.gain)**2
    if callback is not None:
        elapsed = (time() - before) * 1000
        msg = f'Created initial variance image in {elapsed:7.3f}ms.'
        callback(msg)
    before = time()
    sky_img = _create_sky_image(data, sky_low, sky_high, var_img)
    if callback is not None:
        elapsed = time() - before
        msg = f'Created sky image in {elapsed:5.3f}s.'
        callback(msg)
    net_img = data - sky_img
    return _extract_spectrum(net_img, sky_img, var_img, d_low, d_high, cam_cfg, callback), d_low, d_high


def _find_sky_and_signal(data: npt.NDArray[Any]) -> Tuple[int, int, int, int]:
    mean = np.mean(data, axis=1, dtype=np.int32)
    stddev = np.std(data, axis=1)
    max_data = 0
    max_idx = None
    for i in range(0, mean.shape[0]):
        if max_idx is None or mean[i] > max_data:
            max_idx = i
            max_data = mean[i]
    d_low = None
    for i in range(max_idx - 1, -1, -1):
        if mean[i] < 1.5 * stddev[i]:
            d_low = i
            break
    d_high = None
    for i in range(max_idx + 1, mean.shape[0]):
        if mean[i] < 1.5 * stddev[i]:
            d_high = i
            break
    if d_low > 20:
        sky_low = d_low - 10
    else:
        sky_low = d_low - 1
    if mean.shape[0] - d_high > 20:
        sky_high = d_high + 10
    else:
        sky_high = d_high + 1

    return d_low, d_high, sky_low, sky_high


def _create_sky_image(data: npt.NDArray[Any], sky_low: int, sky_high: int,
                      var_img: npt.NDArray[Any]) -> npt.NDArray[Any]:
    result = np.empty(data.shape, dtype=np.float64)
    y_vals = ma.arange(data.shape[0])
    img_vals = ma.empty(data.shape[0])
    inv_weights = ma.empty(data.shape[0])
    mask_low = sky_low + 1
    mask_high = sky_high - 1
    for x in range(data.shape[1]):
        y_vals.mask = ma.nomask
        y_vals[mask_low:mask_high] = ma.masked
        img_vals.mask = ma.nomask
        img_vals[:] = data[:, x]
        img_vals[mask_low:mask_high] = ma.masked
        inv_weights.mask = ma.nomask
        inv_weights[:] = var_img[:, x]
        inv_weights[mask_low:mask_high] = ma.masked

        val_rejected = True
        while val_rejected:
            y_fit = y_vals[~y_vals.mask]
            img_fit = img_vals[~img_vals.mask]
            weights = 1 / inv_weights[~inv_weights.mask]
            poly = Polynomial.fit(y_fit, img_fit, deg=3, w=weights)
            # noinspection PyCallingNonCallable
            residual = (img_vals - poly(y_vals))**2 / inv_weights
            val_rejected = False
            rej_idx = np.nonzero(residual > 16)
            if len(rej_idx[0]):
                val_rejected = True
                for y in rej_idx[0]:
                    y_vals[y] = ma.masked
                    img_vals[y] = ma.masked
                    inv_weights[y] = ma.masked

            if not val_rejected:
                y_vals.mask = ma.nomask
                # noinspection PyCallingNonCallable
                result[:, x] = poly(y_vals)

    return result


def _extract_spectrum(net_img: npt.NDArray[Any], sky_img: npt.NDArray[Any], var_img: npt.NDArray[Any],
                      d_low: int, d_high: int, cam_cfg: CameraConfig,
                      callback: Union[None, Callable[[str], None]]) -> npt.NDArray[Any]:
    start = time()
    if callback is not None:
        callback('Extracting spectrum...')
    n_img = ma.asarray(net_img[d_low:d_high, :])
    f_lam = np.sum(n_img, axis=0)
    f_lam_sq = f_lam**2
    v_img = ma.asarray(var_img[d_low:d_high, :])
    s_img = ma.asarray(sky_img[d_low:d_high, :])
    p_x_lam = n_img / f_lam
    x_val = ma.arange(n_img.shape[1])
    p_lam = ma.empty(n_img.shape, dtype=np.float64)
    p_sum = np.empty(n_img.shape[1], dtype=np.float64)
    v_0 = (cam_cfg.ron / cam_cfg.gain)**2

    # Iterate for profile (p_lam, p_sum)
    pixel_rejected = True
    while pixel_rejected:
        weights = 1 / v_img * f_lam_sq
        for i in range(0, n_img.shape[0]):
            p_slice = p_x_lam[i, :]
            w_slice = weights[i, :]
            if p_slice.mask is ma.nomask:
                x_val_fit = x_val
                p_x_fit = p_slice
                w_fit = w_slice
            else:
                x_val_fit = x_val[~p_slice.mask]
                p_x_fit = p_slice[~p_slice.mask]
                w_fit = w_slice[~p_slice.mask]
            poly = Polynomial.fit(x_val_fit, p_x_fit, deg=30, w=w_fit)
            # noinspection PyCallingNonCallable
            p_lam[i, :] = poly(x_val)
        p_lam[p_lam < 0] = 0
        p_sum = ma.sum(p_lam, axis=0)
        pixel_rejected = False
        f_by_p = p_lam * f_lam / p_sum
        v_img = ma.abs(s_img + f_by_p) / cam_cfg.gain + v_0
        residual = (n_img - f_by_p)**2 / v_img
        residual.mask = p_x_lam.mask
        rej_idx = ma.nonzero(residual > 16)
        if len(rej_idx[0]) > 0:
            pixel_rejected = True
            for y, x in zip(rej_idx[0], rej_idx[1]):
                p_x_lam[y, x] = ma.masked
    if callback is not None:
        elapsed = time() - start
        callback(f'Computed profile in {elapsed:5.3f}s.')

    # Reject cosmic ray hits
    start = time()
    pixel_rejected = True
    variance = None
    while pixel_rejected:
        p_lam_norm = p_lam / p_sum
        enumerator = ma.sum((p_lam_norm * n_img) / v_img, axis=0)
        variance = ma.sum(p_lam_norm**2 / v_img, axis=0)
        f_lam = enumerator / variance
        f_by_p = p_lam_norm * f_lam
        v_img = ma.abs(s_img + f_by_p) / cam_cfg.gain + v_0
        residual = (n_img - f_by_p)**2 / v_img
        pixel_rejected = False
        rej_idx = np.nonzero(residual > 25)
        max_res = None
        x_max = None
        y_max = None
        for y, x in zip(rej_idx[0], rej_idx[1]):
            res = residual[y, x]
            if max_res is None or res > max_res:
                max_res = res
                y_max = y
                x_max = x
        if max_res is not None:
            pixel_rejected = True
            p_lam[y_max, x_max] = ma.masked
            p_sum = ma.sum(p_lam, axis=0)
            n_img[y_max, x_max] = ma.masked
            v_img[y_max, x_max] = ma.masked
            s_img[y_max, x_max] = ma.masked

    if callback is not None:
        elapsed = time() - start
        sigma = ma.sqrt(variance)
        snr = f_lam / sigma
        min_snr = ma.min(snr)
        callback(f'Rejected cosmic ray hits in {elapsed:5.3f}s. SNR >= {min_snr:6.0f}.')
    return np.asarray(f_lam)


if __name__ == '__main__':
    g_input_dir = '/home/mgeselle/astrowrk/spectra/reduced'
    # g_input_basename = 'slt-flt-rot-drk-Neon_Castor_001.fits'
    g_input_basename = 'slt-flt-rot-drk-Castor'
    # g_limits = (390, 430)
    # g_prefix = 'c1d-'
    g_prefix = 'p1d-'
    # simple(g_input_dir, g_input_basename, g_limits, prefix=g_prefix)
    optimal(g_input_dir, g_input_basename, 'ST10XME', prefix=g_prefix, callback=print)

    main = tk.Tk()
    sv = Specview(main, width=1200, height=1100)
    sv.pack(side=tk.TOP, fill=tk.BOTH)

    g_in_hdu_l = fits.open(g_input_dir + '/' + g_prefix + g_input_basename + '.fits')
    g_data = g_in_hdu_l[0].data
    sv.add_spectrum(g_data)

    main.eval('tk::PlaceWindow . center')
    tk.mainloop()


