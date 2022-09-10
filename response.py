import astropy.constants as ac
import astropy.io.fits as fits
import astropy.units as u
import numpy as np
import numpy.linalg as npl
import numpy.ma as ma
import numpy.polynomial as npp
import numpy.typing as npt
import scipy.optimize as sco
import scipy.signal as scs
import config

from astropy.coordinates import EarthLocation, SkyCoord
from astropy.time import Time
from astroquery.simbad import Simbad
from math import ceil
from pathlib import Path
from typing import Any


def resample_ref(rec_header: fits.Header, ref_header: fits.Header, ref_data: npt.NDArray[Any]) -> npt.NDArray[Any]:
    """Resamples a reference spectrum to match a recorded one in wavelength range and sampling.

    The reference spectrum is first Doppler-shifted to match the position of the spectral
    features to the recorded one. This relies on the header keywords AAV_SITE or SITELAT, SITELONG, and
    DATE_OBS in the header of the recorded spectrum.
    The object position is looked up from Simbad using the OBJECT header card from the reference file.

    Args:
        rec_header: header of the recorded FITS file
        ref_header: header of the reference FITS file
        ref_data: data from the reference FITS file

    Returns:
        Resampled reference data.
    """
    if 'AAV_SITE' in rec_header:
        location = config.Config.get().get_location(rec_header['AAV_SITE'])
    elif 'SITELAT' in rec_header and 'SITELONG' in rec_header:
        location = EarthLocation.from_geodetic(rec_header['SITELONG'] * u.deg, rec_header['SITELAT'] * u.deg)
    else:
        raise ValueError('No coordinate info in recorded FITS file')

    obs_time = Time(rec_header['DATE-OBS'], format='isot', scale='utc')

    if ref_data.shape[0] == 1:
        ref_data = ref_data[0]

    table = Simbad.query_object(ref_header['OBJECT'])
    if table is None:
        raise ValueError(f"Object {ref_header['OBJECT']} not found in Simbad")
    for ra_str, dec_str in table.iterrows('RA', 'DEC'):
        pos = SkyCoord(ra_str, dec_str, unit=(u.hourangle, u.deg))
        break

    # noinspection PyUnboundLocalVariable
    bary_ms = pos.radial_velocity_correction('barycentric', obs_time, location).to(u.m/u.s)
    # noinspection PyUnresolvedReferences
    corr = (1.0 - bary_ms / ac.c).value
    cr_step = ref_header['CDELT1']
    cr_lambda = ref_header['CRVAL1'] + (1 - ref_header['CRPIX1']) * cr_step
    ref_samples = ref_data.shape[0]
    ref_lambda = np.linspace(cr_lambda, cr_lambda + (ref_samples - 1) * cr_step, ref_samples) * corr

    rec_step = rec_header['CDELT1']
    rec_lambda_start = rec_header['CRVAL1'] + (1 - rec_header['CRPIX1']) * rec_step
    rec_samples = rec_header['NAXIS1']
    rec_lambda = np.linspace(rec_lambda_start, rec_lambda_start + (rec_samples - 1) * rec_step, rec_samples)

    interval = ref_samples >> 1
    ref_idx = interval
    while interval > 0:
        if ref_lambda[ref_idx] == rec_lambda[0] or (ref_lambda[ref_idx] < rec_lambda[0] < ref_lambda[ref_idx + 1]):
            break
        interval >>= 1
        if ref_lambda[ref_idx] > rec_lambda[0]:
            ref_idx -= interval
        else:
            ref_idx += interval
    while rec_lambda[0] < ref_lambda[ref_idx]:
        ref_idx -= 1
    while rec_lambda[0] > ref_lambda[ref_idx + 1]:
        ref_idx += 1

    result = np.empty(rec_samples)
    slope = None
    for rec_idx in range(0, rec_samples):
        if slope is None or rec_lambda[rec_idx] >= ref_lambda[ref_idx + 1]:
            while rec_lambda[rec_idx] >= ref_lambda[ref_idx + 1]:
                ref_idx += 1
            slope = (ref_data[ref_idx + 1] - ref_data[ref_idx]) / (ref_lambda[ref_idx + 1] / ref_lambda[ref_idx])
        result[rec_idx] = ref_data[ref_idx] + slope * (rec_lambda[rec_idx] - ref_lambda[ref_idx])

    return result


def fit_ref_to_recorded(ref_data: npt.NDArray[Any], rec_data: npt.NDArray[Any]) -> npt.NDArray:
    """Scales a reference spectrum such that the difference between this spectrum and a recorded one becomes minimal.

    Args:
        ref_data: reference spectrum
        rec_data: recorded spectrum

    Returns:
        scaled reference spectrum
    """
    # noinspection PyPep8Naming
    A = np.vstack([ref_data, np.ones(ref_data.size)]).T
    # Constraining vertical shift to zero
    sol = sco.lsq_linear(A, rec_data, ((-np.inf, 0), (np.inf, 0.000000001)))

    # noinspection PyUnresolvedReferences
    return ref_data * sol.x[0]


def fit_continuum(data: npt.NDArray[Any], lambda_start: float, lambda_step: float) -> npt.NDArray[Any]:
    """Fits a continuum to a spectrum.

    This is looking for a self-consistent solution:
    Initially we are fitting a polynomial to the entire data. Big deviations from the
    fitted polynomial are usually due to absorption or emission lines. We exclude
    any data where the deviation is more than 3 times the RMS deviation and do the
     fit again. This is repeated until no more data are rejected.

     Args:
        data: spectrum data
        lambda_start: wavelength at index 0 - used for debugging
        lambda_step: wavelength step between two data elements.

    Returns:
          Fitted continuum
    """
    xdata = ma.asarray(np.linspace(lambda_start, lambda_start + (data.size - 1) * lambda_step, data.size))
    ydata = ma.asarray(data)

    # Look for self-consistent solution: big deviations from the continuum curve
    # are usually due to absorption or emission lines. Those are masked and
    # the fit done again until no more pixels are rejected.
    pixel_rejected = True
    poly = None
    while pixel_rejected:
        pixel_rejected = False
        if xdata.mask is ma.nomask:
            xfit = xdata
            yfit = ydata
        else:
            xfit = xdata[~xdata.mask]
            yfit = ydata[~ydata.mask]
        poly = npp.Polynomial.fit(xfit, yfit, 30)
        # noinspection PyCallingNonCallable
        residual = (ydata - poly(xdata))**2
        residual.mask = ydata.mask
        mean_var = ma.mean(residual)
        rej_idx = ma.nonzero(residual > 9 * mean_var)
        for idx in rej_idx[0]:
            pixel_rejected = True
            xdata[idx] = ma.masked
            ydata[idx] = ma.masked

    xdata.mask = ma.nomask
    # noinspection PyCallingNonCallable
    return np.asarray(poly(xdata))


def create_response(rec_file: Path, ref_file: Path, output_path: Path, mode='cont'):
    with fits.open(rec_file) as hdu:
        rec_header = hdu[0].header
        rec_data = hdu[0].data
    rec_step = rec_header['CDELT1']
    rec_lambda_start = rec_header['CRVAL1'] + (1 - rec_header['CRPIX1']) * rec_step

    with fits.open(ref_file) as hdu:
        ref_header = hdu[0].header
        ref_data = hdu[0].data

    ref_resampled = resample_ref(rec_header, ref_header, ref_data)
    ref_resampled = fit_ref_to_recorded(ref_resampled, rec_data)

    if mode == 'filt':
        response = _compute_response_filt(rec_data, ref_resampled, rec_lambda_start, rec_step)
    else:
        response = _compute_response_cont(rec_data, ref_resampled, rec_lambda_start, rec_step)

    resp_header = fits.Header()
    resp_header.add_comment(rec_header['COMMENT'][0])
    resp_header.add_comment(rec_header['COMMENT'][1])
    if 'OBJECT' in ref_header:
        resp_header['OBJNAME'] = ref_header['OBJECT']
    elif 'OBJNAME' in ref_header:
        resp_header['OBJNAME'] = ref_header['OBJNAME']
    resp_header.append(('DATE-OBS', rec_header['DATE-OBS'], 'Start of observation'))
    for kw in ('CRPIX1', 'CRVAL1', 'CDELT1', 'CTYPE1', 'CUNIT1'):
        resp_header[kw] = rec_header[kw]

    fits.PrimaryHDU(response, resp_header).writeto(output_path / 'response.fits', overwrite=True)

    corr_data = rec_data / response
    corr_header = fits.Header(rec_header, copy=True)
    corr_header.add_comment('Response-corrected using Spectra.')
    max_idx = corr_data.argmax()
    corr_data = corr_data / corr_data[max_idx]

    fits.PrimaryHDU(corr_data, corr_header).writeto(output_path / rec_file.name, overwrite=True)


def _compute_response_cont(rec_data: npt.NDArray[Any], ref_data: npt.NDArray[Any],
                           rec_lambda_start: float, rec_lambda_step: float) -> npt.NDArray[Any]:
    # Don't try to de-oxygenate the spectrum but rather replace the big peak
    # between 6863 and 6968 by a linear section.
    rec_lambda_end = rec_lambda_start + (rec_data.size - 1) * rec_lambda_step
    rec_data_cpy = None
    if rec_lambda_end > 6863 > rec_lambda_start:
        # O2 peak is in spectrum
        idx_6863 = int((6863 - rec_lambda_start) / rec_lambda_step)
        no_steps = idx_6863
        if no_steps > 9:
            no_steps = 9
        if no_steps > 2:
            x_data = np.linspace(rec_lambda_start + (idx_6863 - no_steps) * rec_lambda_step,
                                 rec_lambda_start + idx_6863 * rec_lambda_step, no_steps + 1)
            y_data = rec_data[idx_6863 - no_steps:idx_6863 + 1]
            A = np.vstack([x_data, np.ones(x_data.size)]).T
            m, c = npl.lstsq(A, y_data, rcond=None)[0]
            end_idx = int((6968 - rec_lambda_start) / rec_lambda_step)
            if end_idx > rec_data.size:
                end_idx = rec_data.size
            lambda_x = rec_lambda_start + idx_6863 * rec_lambda_step
            rec_data_cpy = np.copy(rec_data)
            for i in range(idx_6863, end_idx):
                rec_data_cpy[i] = m * lambda_x + c
                lambda_x += rec_lambda_step
    if rec_data_cpy is None:
        rec_data_cpy = rec_data
    rec_continuum = fit_continuum(rec_data_cpy, rec_lambda_start, rec_lambda_step)
    ref_continuum = fit_continuum(ref_data, rec_lambda_start, rec_lambda_step)
    return rec_continuum / ref_continuum


def _compute_response_filt(rec_data: npt.NDArray[Any], ref_data: npt.NDArray[Any],
                           rec_lambda_start: float, rec_lambda_step: float) -> npt.NDArray[Any]:
    raw_response = rec_data / ref_data
    return scs.medfilt(raw_response, 31)


def apply_response(resp_path: Path, pgm_path: Path, output_path: Path):
    with fits.open(resp_path) as resp:
        resp_header = resp[0].header
        resp_data = resp[0].data

    resp_lam_step = resp_header['CDELT1']
    resp_lam_start = resp_header['CRVAL1'] + (1 - resp_header['CRPIX1']) * resp_lam_step
    resp_lam_end = resp_lam_start + (resp_data.size - 1) * resp_lam_step

    with fits.open(pgm_path) as pgm:
        pgm_header = pgm[0].header
        pgm_data = pgm[0].data

    pgm_lam_step = pgm_header['CDELT1']
    pgm_lam_start = pgm_header['CRVAL1'] + (1 - pgm_header['CRPIX1']) * pgm_lam_step
    pgm_lam_end = pgm_lam_start + (pgm_data.size - 1) * pgm_lam_step

    if pgm_lam_start >= resp_lam_start:
        pgm_idx = 0
    else:
        pgm_idx = int(ceil(resp_lam_start - pgm_lam_start) / pgm_lam_step)
        pgm_lam_start += pgm_idx * pgm_lam_step
    resp_idx = int((pgm_lam_start - resp_lam_start) / resp_lam_step)

    if resp_lam_end < pgm_lam_end:
        pgm_lam_end = pgm_lam_start + int((resp_lam_end - pgm_lam_start) / pgm_lam_step) * pgm_lam_step
        pgm_end_idx = int(pgm_lam_end - pgm_lam_start) / pgm_lam_step
    else:
        pgm_end_idx = int((pgm_lam_end - pgm_lam_start) / pgm_lam_step)

    pgm_data = pgm_data[pgm_idx:pgm_end_idx]
    slope = None
    resp_res = np.empty(pgm_data.shape)
    pgm_lam = pgm_lam_start
    resp_lam = resp_lam_start + resp_idx * resp_lam_step
    for pgm_idx in range(0, pgm_data.size):
        if slope is None or resp_lam + resp_lam_step < pgm_lam:
            while resp_lam + resp_lam_step < pgm_lam:
                resp_lam += resp_lam_step
                resp_idx += 1
            slope = (resp_data[resp_idx + 1] - resp_data[resp_idx]) / resp_lam_step
        resp_res[pgm_idx] = resp_data[resp_idx] + slope * (pgm_lam - resp_lam)
        pgm_lam += pgm_lam_step

    result = pgm_data / resp_res
    result = result / np.max(result)
    out_header = fits.Header(pgm_header)
    out_header['CRPIX1'] = 1.0
    out_header['CRVAL1'] = pgm_lam_start
    out_header.add_history(f"Response corrected using response generated from {resp_header['OBJNAME']}")

    fits.PrimaryHDU(result, out_header).writeto(output_path / pgm_path.name, overwrite=True)


if __name__ == '__main__':
    import matplotlib.pyplot as plt

    in_dir = Path.home() / 'astrowrk/spectra/calibrated'
    out_dir = Path.home() / 'astrowrk/spectra/response-corrected'
    rec = list(in_dir.glob('Castor_L*'))[0]
    ref = list(in_dir.glob('Castor-M*'))[0]

    create_response(rec, ref, out_dir, mode='cont')

    with fits.open(out_dir / rec.name) as r_hdu:
        r_data = r_hdu[0].data
        r_header = r_hdu[0].header
    r_step = r_header['CDELT1']
    r_lambda_start = r_header['CRVAL1'] + (1 - r_header['CRPIX1']) * r_step
    r_samples = r_header['NAXIS1']
    r_lambda = np.linspace(r_lambda_start, r_lambda_start + (r_samples - 1) * r_step, r_samples)

    with fits.open(ref) as ref_hdu:
        ref_hdr = ref_hdu[0].header
        ref_dta = ref_hdu[0].data
    ref_rescaled = resample_ref(r_header, ref_hdr, ref_dta)
    ref_max = ref_rescaled.argmax()
    ref_rescaled = ref_rescaled / ref_rescaled[ref_max]

    fig, ax = plt.subplots()
    ax.plot(r_lambda, ref_rescaled)
    ax.plot(r_lambda, r_data)
    plt.show()
