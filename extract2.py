import math
from dataclasses import dataclass
from math import sqrt, log
from pathlib import Path
from typing import Any, Tuple, Union

import matplotlib.pyplot as plt
import numpy as np
import numpy.ma as ma
import numpy.polynomial as npp
import numpy.typing as npt
import scipy.ndimage as scn
import scipy.optimize as sco
import scipy.signal as scs
from astropy.io import fits
from astropy.visualization import mpl_normalize as apn
from scipy import interpolate

from config import CameraConfig


@dataclass
class ImageBounds:
    data_low: int
    data_high: int
    sky_low: int
    sky_high: int


def optimal(image: Path, config: CameraConfig) -> Union[None, Tuple[int]]:
    hdu = fits.open(image)
    data = hdu[0].data
    image_bounds = _find_image_bounds(data)
    variance = (np.abs(data) + config.ron**2 / config.gain) / config.gain
    sky = _create_sky_image(data, variance, image_bounds)
    _extract_spectrum(data, sky, variance, image_bounds, config)
    return None


def _find_image_bounds(data: npt.NDArray[Any]) -> Union[None, ImageBounds]:
    x_avg = np.average(data, axis=1)
    #plt.plot(np.arange(0, x_avg.shape[0]), x_avg)
    #plt.show()
    peaks, _ = scs.find_peaks(x_avg, prominence=400, width=4)
    if len(peaks) == 0:
        peaks, _ = scs.find_peaks(x_avg, prominence=400, width=2)
        if len(peaks) == 0:
            print('No signal found.')
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
        return a + b * np.exp(-0.5 * ((x - c) / d)**2)

    y_vals = np.arange(0, x_avg.shape[0])
    try:
        popt, _ = sco.curve_fit(model, y_vals, x_avg, p0=(a_0, b_0, c_0, d_0))
    except RuntimeError as ex:
        print(f'Runtime error fitting signal peak: {ex}')
        return None

    data_low = int(popt[2] - 5 * popt[3])
    data_high = int(popt[2] + 5 * popt[3])

    sky_low = int(popt[2] - 8 * popt[3])
    sky_high = int(popt[2] + 8 * popt[3])

    plt.plot([peak], [x_avg[peak]], 'ro')
    plt.plot(y_vals, model(y_vals, *popt), 'g:')
    plt.plot([data_low, data_high], [x_avg[data_low], x_avg[data_high]], 'rv')
    plt.plot([sky_low, sky_high], [x_avg[sky_low], x_avg[sky_high]], 'r*')
    plt.show()
    return ImageBounds(data_low, data_high, sky_low, sky_high)


def _create_sky_image(data: npt.NDArray[Any], variance: npt.NDArray[Any],
                      bounds: Union[None, ImageBounds]) -> Union[None, npt.NDArray[Any]]:
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
            residual = (y_data - poly(x_data))**2 * y_weights
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

    #p_img = data - result
    p_img = result
    norm = apn.ImageNormalize(p_img, interval=apn.PercentileInterval(95.0), stretch=apn.AsinhStretch())
    plt.imshow(p_img, origin='lower', norm=norm)
    plt.show()

    return result


def _extract_spectrum(data: npt.NDArray[Any], sky: npt.NDArray[Any], init_variance: npt.NDArray[Any],
                      bounds: ImageBounds, config: CameraConfig) -> npt.NDArray[Any]:
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
    p_d = net_img / f_raw
    w = f_raw**2 / masked_var
    p_d = scn.median_filter(net_img / f_raw, size=(1, 8))
    p_d = ma.asarray(p_d)
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
    y_plt = int(p_d.shape[0] / 2)

    rejected = True
    while rejected:
        for y in range(0, masked_data.shape[0]):
            #tck = interpolate.splrep(x, p_d[y, :], w=w[y, :], k=4, s=p_d.shape[1])
            #p_r[y, :] = interpolate.splev(x, tck, der=0)
            #poly = npp.Chebyshev.fit(x, p_d[y, :], deg=5, w=w[y, :])
            #p_r[y, :] = poly(x)
            poly = npp.Polynomial.fit(x, p_d[y, :], deg=15, w=w[y, :])
            p_r[y, :] = poly(x)
        p_r[p_r < 0] = 0
        p_r = p_r / ma.sum(p_r, axis=0)
        f = ma.sum(p_r * net_img / masked_var, axis=0) / ma.sum(p_r**2 / masked_var, axis=0)
        f_by_p = f * p_r
        masked_var = (ma.abs(f_by_p + masked_sky) + config.ron**2 / config.gain) / config.gain
        residual = (net_img - f_by_p)**2 / masked_var
        residual.mask = p_d.mask
        rej_idx = np.nonzero(residual > 16)
        print(f'stage 1 len rej_idx = {len(rej_idx[0])}')
        rejected = len(rej_idx[0]) > 0
        if rejected:
            for y_r, x_r in zip(rej_idx[0], rej_idx[1]):
                p_d[y_r, x_r] = ma.masked
        w = f**2 / masked_var
    p_d.mask = ma.nomask
    for y in range(0, net_img.shape[0]):
        fig, (ax1, ax2, ax3) = plt.subplots(3, 1)
        ax1.plot(x, net_img[y])
        ax2.plot(x, p_d[y], 'ro')
        ax2.plot(x, p_r[y])
        ax3.plot(x, (net_img[y] - f_by_p[y])**2 / masked_var[y])
        plt.show()

    residual.mask = ma.nomask
    rej_idx = None
    limit = 25
    rej_cutoff = 100
    while rej_idx is None or len(rej_idx[0] > rej_cutoff):
        rej_idx = np.nonzero(residual > limit)
        if len(rej_idx[0] > rej_cutoff):
            limit += 10
    print(f'Rejecting residuals >= {limit}')
    while True:
        rej_idx = np.nonzero(residual > limit)
        if len(rej_idx[0]) == 0:
            break
        print(f'len rej_idx = {len(rej_idx[0])}')
        max_res = 0
        for y_r, x_r in zip(rej_idx[0], rej_idx[1]):
            if residual[y_r, x_r] > max_res:
                max_res = residual[y_r, x_r]
                y_max = y_r
                x_max = x_r
        p_r[y_max, x_max] = ma.masked
        p_r = p_r / ma.sum(p_r, axis=0)
        f = ma.sum(p_r * net_img / masked_var, axis=0) / ma.sum(p_r**2 / masked_var, axis=0)
        f_by_p = f * p_r
        mask = f_by_p.mask[y_max, x_max]
        masked_var = (ma.abs(f_by_p + masked_sky) + config.ron**2 / config.gain) / config.gain
        residual = (net_img - f_by_p)**2 / masked_var
        residual.mask = p_r.mask

    plt.plot(x, f)
    plt.plot(x, ma.sum(net_img, axis=0) - 20000, 'r-')
    plt.show()

    return f


if __name__ == '__main__':
    #input_file = Path.home() / 'astrowrk/spectra/uvex4/20230610/slant-corr/Castor_Light_001.fits'
    input_file = Path.home() / 'astrowrk/spectra/uvex4/20230610/slant-corr/Sheliak_Light_60_secs_001.fits'
    #input_file = Path.home() / 'astrowrk/spectra/uvex4/20230610/rot-corr/Sheliak_Light_60_secs_001.fits'
    # ASI294MM Pro at gain 200, according to http://www.astrosurf.com/buil/asi294mm.html
    cam_cfg = CameraConfig(1.89, 0.0864)
    # ST10 XME
    #cam_cfg = CameraConfig(13, 1.3)
    optimal(input_file, cam_cfg)