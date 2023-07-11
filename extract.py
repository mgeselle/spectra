from dataclasses import dataclass
from math import sqrt, log
from pathlib import Path
from typing import Union, Tuple, Sequence, Any, Callable, Dict

import matplotlib.pyplot as plt
import numpy as np
import numpy.ma as ma
import numpy.polynomial as npp
import numpy.typing as npt
import scipy.ndimage as scn
import scipy.optimize as sco
import scipy.signal as scs
import wx
from astropy.io import fits
from astropy.time import Time, TimeDelta
from astropy.visualization import mpl_normalize as apn

from config import Config, CameraConfig


@dataclass
class ImageBounds:
    data_low: int
    data_high: int
    sky_low: int
    sky_high: int


def simple(input_files: Union[Path, Sequence[Path]],
           limits: Union[Tuple[int, int], Sequence[int]],
           output_path: Path):
    headers = []
    if isinstance(input_files, Path):
        input_files = [input_files]
    out_name = _get_common_name(input_files, 'simple-1d')
    out_data = None
    for i in range(len(input_files)):
        spectrum, header = simple_single(input_files[i], limits)
        headers.append(header)
        if out_data is None:
            out_data = np.empty((len(input_files), spectrum.shape[0]), dtype=np.float32)
        out_data[i] = spectrum[:]
    out_spectrum = np.mean(out_data, axis=0)
    out_hdu = fits.PrimaryHDU(out_spectrum, headers[0])
    output_file = output_path / out_name
    out_hdu.writeto(output_file, overwrite=True)


def simple_single(input_file: Path, limits: Union[Tuple[int, int], Sequence[int]]) -> Tuple[
    npt.NDArray[Any], fits.Header]:
    if len(limits) != 2:
        raise ValueError('limits have wrong length')
    lower, upper = sorted(limits)
    in_hdu_l = fits.open(input_file)
    data: npt.NDArray[Any] = in_hdu_l[0].data
    if lower < 0 or upper > data.shape[0]:
        raise ValueError('limits are out of bounds')
    spectrum = np.sum(data[lower:upper, :], axis=0, dtype=np.float32)
    header = in_hdu_l[0].header
    in_hdu_l.close()
    return spectrum, header


def optimal(input_files: Union[Path, Sequence[Path]],
            config_name: str, output_path: Path,
            header_overrides: Dict[str, str] = None,
            callback: Union[None, Callable[[int, str], bool]] = None,
            budget=100, start_with=0) -> Union[Tuple[int, int], Tuple[None, None]]:
    if isinstance(input_files, Path):
        input_files = [input_files]
    cam_cfg = Config.get().get_camera_config(config_name)
    headers = []
    out_data = None
    d_low = None
    d_high = None
    progress = start_with
    prog_step = int(budget / len(input_files))
    spectra = []
    for i in range(len(input_files)):
        if callback is not None:
            msg = f'Extracting spectrum from {input_files[i].name}.'
            if callback(progress, msg):
                return None, None
        in_hdu_l = fits.open(input_files[i])
        data = in_hdu_l[0].data
        headers.append(in_hdu_l[0].header)
        if out_data is None:
            out_data = np.empty((len(input_files), data.shape[1]))
            d_low = data.shape[0]
            d_high = 0
        spectrum, n_d_low, n_d_high = _optimal(data, cam_cfg)
        in_hdu_l.close()
        if spectrum is not None:
            spectra.append(spectrum)
        out_data[i] = spectrum[:]
        if n_d_low < d_low:
            d_low = n_d_low
        if n_d_high > d_high:
            d_high = n_d_high
        progress += prog_step

    if len(spectra) == 0:
        return None, None

    out_data = np.array(spectra)
    out_name = _get_common_name(input_files, 'optimal-1d')
    if out_name != 'optimal-1d':
        out_spectrum = np.mean(out_data, axis=0)
        min_time = None
        max_time = None
        end_time = None
        total_exptime = 0.0
        for header in headers:
            head_time = Time(header['DATE-OBS'], format='isot', scale='utc')
            total_exptime += float(header['EXPTIME'])
            if min_time is None or head_time < min_time:
                min_time = head_time
            if max_time is None or head_time > max_time:
                max_time = head_time
                end_time = max_time + TimeDelta(header['EXPTIME'], format='sec')
        header = fits.Header()
        header.add_comment("FITS (Flexible Image Transport System) is defined in 'Astronomy")
        header.add_comment("and Astrophysics', volume 376, page 359; bibcode: 2001A&A...376..359H")
        if out_data.shape[0] > 1:
            header.add_comment(f'Spectrum is average of {out_data.shape[0]} spectra.')
            header.add_comment('Spectra extracted by optimal method.')
        else:
            header.add_comment('Spectrum extracted by optimal method.')
        header.add_comment('See Horne K., PASP 1986, Vol. 98, p. 609, bibcode: 1986PASP...98..609H')
        header['DATE-OBS'] = str(min_time)
        header['DATE-END'] = str(end_time)
        # AAVSO requires this to be of type float
        header['EXPTIME'] = total_exptime
        jd = (min_time + (end_time - min_time) / 2).jd
        # AAVSO requires this to be of type float
        header['JD'] = jd
        if header_overrides is not None:
            for key in header_overrides.keys():
                header[key] = header_overrides[key]

        out_hdu = fits.PrimaryHDU(out_spectrum, header)
        output_file = output_path / out_name
        out_hdu.writeto(output_file, overwrite=True)
    else:
        for i in range(0, len(input_files)):
            out_name = input_files[i].name
            fits.PrimaryHDU(out_data[i, :], headers[i]).writeto(output_path / out_name, overwrite=True)
    return d_low, d_high


def _get_common_name(files: Sequence[Path], default_name: str) -> Union[str, None]:
    if len(files) == 1:
        return files[0].name

    min_len = min(len(files[0].stem), len(files[1].stem))
    common_idx = 0
    for common_idx in range(0, min_len + 1):
        if files[0].stem[common_idx] != files[1].stem[common_idx]:
            break
    if common_idx == 0:
        out_name = default_name
    else:
        out_name = files[0].stem[0:common_idx]
    return out_name + files[0].suffix


def _optimal(data: npt.NDArray[Any], config: CameraConfig) -> Union[
        Tuple[npt.NDArray[Any], int, int], Tuple[None, None, None]]:
    image_bounds = _find_image_bounds(data)
    if image_bounds is None:
        return None, None, None
    variance = (np.abs(data) + config.ron ** 2 / config.gain) / config.gain
    sky = _create_sky_image(data, variance, image_bounds)
    if sky is None:
        return None, None, None
    spectrum = _extract_spectrum(data, sky, variance, image_bounds, config)
    if spectrum is None:
        return None, None, None
    else:
        return spectrum, image_bounds.data_low, image_bounds.data_high


def _find_image_bounds(data: npt.NDArray[Any], plot: bool = False) -> Union[None, ImageBounds]:
    x_avg = np.average(data, axis=1)
    # plt.plot(np.arange(0, x_avg.shape[0]), x_avg)
    # plt.show()
    peaks, _ = scs.find_peaks(x_avg, prominence=400, width=4)
    if len(peaks) == 0:
        peaks, _ = scs.find_peaks(x_avg, prominence=400, width=2)
        if len(peaks) == 0:
            wx.LogMessage('No signal found.')
            return None
    if len(peaks) > 1:
        peak = None
        max_peak = None
        for c_peak in peaks:
            if max_peak is None or x_avg[c_peak] > max_peak:
                peak = c_peak
                max_peak = x_avg[c_peak]
    else:
        peak = peaks[0]

    # Attempt to fit gaussian to first approximation peak
    # y = a + b * exp(-0.5 * [(x - c) / d]**2)
    a_0 = (x_avg[0] + x_avg[-1]) / 2.0
    b_0 = x_avg[peak]
    c_0 = peak
    # Assuming initial FWHM of 4
    d_0 = 2.0 / sqrt(2 * log(2))

    def model(x, a, b, c, d):
        return a + b * np.exp(-0.5 * ((x - c) / d) ** 2)

    y_vals = np.arange(0, x_avg.shape[0])
    try:
        popt, _ = sco.curve_fit(model, y_vals, x_avg, p0=(a_0, b_0, c_0, d_0))
    except RuntimeError as ex:
        wx.LogMessage(f'Runtime error fitting signal peak: {ex}')
        return None

    data_low = int(popt[2] - 5 * popt[3])
    data_high = int(popt[2] + 5 * popt[3])

    sky_low = int(popt[2] - 8 * popt[3])
    sky_high = int(popt[2] + 8 * popt[3])

    if plot:
        plt.plot([peak], [x_avg[peak]], 'ro')
        plt.plot(y_vals, model(y_vals, *popt), 'g:')
        plt.plot([data_low, data_high], [x_avg[data_low], x_avg[data_high]], 'rv')
        plt.plot([sky_low, sky_high], [x_avg[sky_low], x_avg[sky_high]], 'r*')
        plt.show()
    return ImageBounds(data_low, data_high, sky_low, sky_high)


def _create_sky_image(data: npt.NDArray[Any], variance: npt.NDArray[Any],
                      bounds: Union[None, ImageBounds], plot: bool = False) -> Union[None, npt.NDArray[Any]]:
    if bounds is None:
        return None
    masked_data = data.view(ma.MaskedArray)
    masked_variance = variance.view(ma.MaskedArray)
    weights = 1.0 / masked_variance
    if bounds.sky_high < bounds.data_low:
        # spectrum trace is on the upper edge of the image
        masked_data[bounds.sky_high:, :] = ma.masked
    elif bounds.data_high < bounds.sky_low:
        # spectrum trace is on the lower edge of the image
        masked_data[0:bounds.sky_low, :] = ma.masked
    else:
        # well-behaved image
        masked_data[bounds.sky_low:bounds.sky_high] = ma.masked
    weights.mask = masked_data.mask

    result = np.empty(data.shape)
    for x in range(0, data.shape[1]):
        x_data = ma.arange(0, data.shape[0])
        x_data.mask = masked_data.mask[:, x]
        y_data = masked_data[:, x]
        y_data.mask = x_data.mask
        y_weights = weights[:, x]
        y_weights.mask = y_data.mask

        rejected = True
        while rejected:
            poly = npp.Polynomial.fit(x_data, y_data, deg=2, w=y_weights)
            residual = (y_data - poly(x_data)) ** 2 * y_weights
            rej_idx = ma.nonzero(residual > 16)
            rejected = False
            if len(rej_idx[0]):
                rejected = True
                for idx in rej_idx[0]:
                    x_data[idx] = ma.masked
                y_data.mask = x_data.mask
                y_weights.mask = y_data.mask

        x_data.mask = ma.nomask
        result[:, x] = poly(x_data)

    if plot:
        p_img = result
        norm = apn.ImageNormalize(p_img, interval=apn.PercentileInterval(95.0), stretch=apn.AsinhStretch())
        plt.imshow(p_img, origin='lower', norm=norm)
        plt.show()

    return result


def _extract_spectrum(data: npt.NDArray[Any], sky: npt.NDArray[Any], init_variance: npt.NDArray[Any],
                      bounds: ImageBounds, config: CameraConfig, plot: bool = False) -> npt.NDArray[Any]:
    masked_data = ma.asarray(data[bounds.data_low:bounds.data_high, :])
    for xd in range(0, masked_data.shape[1]):
        if masked_data[0, xd] != 0:
            break
        masked_data[:, xd] = ma.masked
    for xd in range(-1, -masked_data.shape[1], -1):
        if masked_data[0, xd] != 0:
            break
        masked_data[:, xd] = ma.masked
    masked_sky = ma.asarray(sky[bounds.data_low:bounds.data_high, :])
    masked_var = ma.asarray(init_variance[bounds.data_low:bounds.data_high, :])
    net_img = masked_data - masked_sky
    f_raw = ma.sum(net_img, axis=0)
    w = f_raw ** 2 / masked_var
    # smooth continuum by median filtering
    p_d = scn.median_filter(net_img / f_raw, size=(1, 8))
    p_d = ma.asarray(p_d)
    # Mask any zero values at the borders of the spectrum image:
    # These are bound to be artifacts from rotation/slant correction
    for y in range(0, p_d.shape[0]):
        for xd in range(0, p_d.shape[1]):
            if p_d[0, xd] != 0:
                break
            p_d[:, xd] = ma.masked
        for xd in range(-1, -masked_data.shape[1], -1):
            if p_d[0, xd] != 0:
                break
            p_d[:, xd] = ma.masked

    p_r = ma.empty(p_d.shape)
    x = ma.arange(0, masked_data.shape[1])

    rejected = True
    while rejected:
        for y in range(0, masked_data.shape[0]):
            # tck = interpolate.splrep(x, p_d[y, :], w=w[y, :], k=4, s=p_d.shape[1])
            # p_r[y, :] = interpolate.splev(x, tck, der=0)
            # poly = npp.Chebyshev.fit(x, p_d[y, :], deg=5, w=w[y, :])
            # p_r[y, :] = poly(x)
            poly = npp.Polynomial.fit(x, p_d[y, :], deg=15, w=w[y, :])
            p_r[y, :] = poly(x)
        p_r[p_r < 0] = 0
        p_r = p_r / ma.sum(p_r, axis=0)
        f = ma.sum(p_r * net_img / masked_var, axis=0) / ma.sum(p_r ** 2 / masked_var, axis=0)
        f_by_p = f * p_r
        masked_var = (ma.abs(f_by_p + masked_sky) + config.ron ** 2 / config.gain) / config.gain
        residual = (net_img - f_by_p) ** 2 / masked_var
        residual.mask = p_d.mask
        rej_idx = np.nonzero(residual > 16)
        wx.LogMessage(f'stage 1 len rej_idx = {len(rej_idx[0])}')
        rejected = len(rej_idx[0]) > 0
        if rejected:
            for y_r, x_r in zip(rej_idx[0], rej_idx[1]):
                p_d[y_r, x_r] = ma.masked
        w = f ** 2 / masked_var
    p_d.mask = ma.nomask

    if plot:
        for y in range(0, net_img.shape[0]):
            fig, (ax1, ax2, ax3) = plt.subplots(3, 1)
            ax1.plot(x, net_img[y])
            ax2.plot(x, p_d[y], 'ro')
            ax2.plot(x, p_r[y])
            ax3.plot(x, (net_img[y] - f_by_p[y]) ** 2 / masked_var[y])
            plt.show()
    else:
        wx.LogMessage('Extracted raw spectrum.')

    residual.mask = ma.nomask
    rej_idx = None
    limit = 25
    rej_cutoff = 100
    while rej_idx is None or len(rej_idx[0] > rej_cutoff):
        rej_idx = np.nonzero(residual > limit)
        if len(rej_idx[0] > rej_cutoff):
            limit += 10
    wx.LogMessage(f'For cosmic rays rejecting residuals >= {limit}')
    while True:
        rej_idx = np.nonzero(residual > limit)
        if len(rej_idx[0]) == 0:
            break
        wx.LogMessage(f'len rej_idx = {len(rej_idx[0])}')
        max_res = 0
        for y_r, x_r in zip(rej_idx[0], rej_idx[1]):
            if residual[y_r, x_r] > max_res:
                max_res = residual[y_r, x_r]
                y_max = y_r
                x_max = x_r
        p_r[y_max, x_max] = ma.masked
        p_r = p_r / ma.sum(p_r, axis=0)
        f = ma.sum(p_r * net_img / masked_var, axis=0) / ma.sum(p_r ** 2 / masked_var, axis=0)
        f_by_p = f * p_r
        masked_var = (ma.abs(f_by_p + masked_sky) + config.ron ** 2 / config.gain) / config.gain
        residual = (net_img - f_by_p) ** 2 / masked_var
        residual.mask = p_r.mask

    if plot:
        plt.plot(x, f)
        plt.plot(x, ma.sum(net_img, axis=0) - 20000, 'r-')
        plt.show()

    return f


if __name__ == '__main__':
    app = wx.App()
    app.SetAppName('spectra')

    base_dir = Path.home() / 'astrowrk/spectra/anal'
    in_file = base_dir / 'in/Dubhe.fits'
    optimal(in_file, 'ST10XME', base_dir)
