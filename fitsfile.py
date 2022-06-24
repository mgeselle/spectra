from astropy.io import fits
import numpy as np
from PIL import Image, ImageOps


class FitsImageFile:
    def __init__(self, file: str):
        self._file_name = file
        self._scaled = None
        with fits.open(file) as hdul:
            self._header = hdul[0].header
            if self._header['NAXIS'] != 2:
                raise RuntimeError('Not an image file')
            self._bitpix: int = self._header['BITPIX']
            self._width: int = self._header['NAXIS1']
            self._height: int = self._header['NAXIS2']

            # Need to convert manually to L, because otherwise PhotoImage
            # won't recognise the format.
            self._data = hdul[0].data
            tmpdata = hdul[0].data.astype(float)
            min_adu = np.min(tmpdata)
            max_adu = np.max(tmpdata)
            print(f'Min: {min_adu:6.1f}, max: {max_adu:6.1f}')
            tmpdata = tmpdata - min_adu
            tmpdata = tmpdata * (255.0 / (max_adu - min_adu))
            self._imgdata = tmpdata.astype(np.byte)
            self._image = Image.fromarray(self._imgdata, 'L')

    @property
    def bitpix(self):
        return self._bitpix

    @property
    def width(self):
        return self._width

    @property
    def height(self):
        return self._height

    def as_image(self, size=None):
        if size is None:
            return self._image

        (w, h) = size
        wscale = w / self._width
        hscale = h / self._height
        return ImageOps.scale(self._image, min(wscale, hscale))

    def adu(self, x, y):
        xi = x
        if xi < 0:
            xi = 0
        elif xi >= self._width:
            xi = self._width - 1
        yi = y
        if yi < 0:
            yi = 0
        elif yi >= self._height:
            yi = self._height - 1
        return self._data[yi, xi]
