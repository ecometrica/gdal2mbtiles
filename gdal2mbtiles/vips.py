# -*- coding: utf-8 -*-

# Licensed to Ecometrica under one or more contributor license
# agreements.  See the NOTICE file distributed with this work
# for additional information regarding copyright ownership.
# Ecometrica licenses this file to you under the Apache
# License, Version 2.0 (the "License"); you may not use this
# file except in compliance with the License.  You may obtain a
# copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

from contextlib import contextmanager
from ctypes import c_double, c_int, c_void_p, cdll
from ctypes.util import find_library
from itertools import groupby
import logging
from math import ceil
from multiprocessing import cpu_count
from operator import itemgetter
from tempfile import NamedTemporaryFile

import numexpr
import numpy

from vipsCC.VError import VError
import vipsCC.VImage

from .constants import TILE_SIDE
from .gdal import Dataset, Band
from .types import rgba, XY
from .utils import tempenv


logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


class LibTiff(object):
    def __init__(self, version=None):
        if version is not None:
            library = 'libtiff.so.{0:d}'.format(version)
        else:
            library = find_library('tiff')
        self.libtiff = cdll.LoadLibrary(library)
        self.functions = {}

    @contextmanager
    def disable_warnings(self):
        function = self.functions.get('TIFFSetWarningHandler', None)
        if function is None:
            function = self.libtiff.TIFFSetWarningHandler
            function.argtypes = [c_void_p]
            function.restype = c_void_p
            self.functions['TIFFSetWarningHandler'] = function

        error_handler = function(None)
        yield
        function(error_handler)

TIFF = LibTiff()


class LibVips(object):
    """Wrapper object around C library."""

    def __init__(self, version=None):
        if version is not None:
            library = 'libvips.so.{0:d}'.format(version)
        else:
            library = find_library('vips')
        self.libvips = cdll.LoadLibrary(library)
        self.functions = {}

    @classmethod
    def disable_warnings(cls):
        """Context manager to disable VIPS warnings."""
        return tempenv('IM_WARNING', '0')

    @property
    def vips_interpolate_bilinear_static(self):
        """Returns VIPS's Bilinear interpolator"""
        function = self.functions.get('vips_interpolate_bilinear_static',
                                      None)

        if function is None:
            function = self.libvips.vips_interpolate_bilinear_static
            function.argtypes = []
            function.restype = c_void_p
            self.functions['vips_interpolate_bilinear_static'] = function
        return function()

    @property
    def vips_interpolate_nearest_static(self):
        """Returns VIPS's Nearest Neighbour interpolator"""
        function = self.functions.get('vips_interpolate_nearest_static', None)

        if function is None:
            function = self.libvips.vips_interpolate_nearest_static
            function.argtypes = []
            function.restype = c_void_p
            self.functions['vips_interpolate_nearest_static'] = function
        return function()

    def im_affinei(self, input, output, interpolate, a, b, c, d, dx, dy,
                   ox, oy, ow, oh):
        """
        This operator performs an affine transform on the image `input` using
        `interpolate`.

        The transform is:
          X = `a` * x + `b` * y + `dx`
          Y = `c` * x + `d` * y + `dy`

          x and y are the coordinates in input image.
          X and Y are the coordinates in output image.
          (0,0) is the upper left corner.

        The section of the output space defined by `ox`, `oy`, `ow`, `oh` is
        written to `out`.

        input: input VipsImage
        output: output VipsImage
        interpolate: interpolation method
        a: transformation matrix
        b: transformation matrix
        c: transformation matrix
        d: transformation matrix
        dx: output offset
        dy: output offset
        ox: output region
        oy: output region
        ow: output region
        oh: output region
        """
        im_affinei = self.functions.get('im_affinei', None)
        if im_affinei is None:
            def errcheck(result, func, args):
                if result != 0:
                    raise VError()
                return result

            im_affinei = self.libvips.im_affinei
            im_affinei.argtypes = [c_void_p, c_void_p, c_void_p,
                                   c_double, c_double, c_double, c_double,
                                   c_double, c_double,
                                   c_int, c_int, c_int, c_int]
            im_affinei.errcheck = errcheck
            im_affinei.restype = c_int
            self.functions['im_affinei'] = im_affinei

        return im_affinei(c_void_p(long(input)), c_void_p(long(output)),
                          interpolate,
                          a, b, c, d, dx, dy,
                          ox, oy, ow, oh)

    def get_concurrency(self):
        """Returns the number of threads used for computations."""
        return c_int.in_dll(self.libvips, 'vips__concurrency').value

    def set_concurrency(self, processes):
        """Sets the number of threads used for computations."""
        if not isinstance(processes, (int, long)) or processes < 0:
            raise ValueError(
                'Must provide a positive integer for processes: {0}'.format(
                    processes
                )
            )

        vips_concurrency_set = self.functions.get('vips_concurrency_set', None)
        if vips_concurrency_set is None:
            vips_concurrency_set = self.libvips.vips_concurrency_set
            vips_concurrency_set.argtypes = [c_int]
            vips_concurrency_set.restype = None
            self.functions['vips_concurrency_set'] = vips_concurrency_set
        vips_concurrency_set(processes)

VIPS = LibVips()


class VImage(vipsCC.VImage.VImage):
    FILL_OPTIONS = {
        'black': 0,                 # Fill bands with 0
        'extend': 1,                # Extend bands from image to edge
        'tile': 2,                  # Tile bands from image
        'mirror': 3,                # Mirror bands from image
        'white': 4,                 # Fill bands with 255
    }

    NUMPY_TYPES = {
        vipsCC.VImage.VImage.FMTCHAR: numpy.int8,
        vipsCC.VImage.VImage.FMTUCHAR: numpy.uint8,
        vipsCC.VImage.VImage.FMTSHORT: numpy.int16,
        vipsCC.VImage.VImage.FMTUSHORT: numpy.uint16,
        vipsCC.VImage.VImage.FMTINT: numpy.int32,
        vipsCC.VImage.VImage.FMTUINT: numpy.uint32,
        vipsCC.VImage.VImage.FMTFLOAT: numpy.float32,
        vipsCC.VImage.VImage.FMTDOUBLE: numpy.float64,
        vipsCC.VImage.VImage.FMTCOMPLEX: numpy.complex64,
        vipsCC.VImage.VImage.FMTDPCOMPLEX: numpy.complex128,
    }

    def __init__(self, *args, **kwargs):
        if VIPS.get_concurrency() == 0:
            # Override auto-detection from environ and argv.
            VIPS.set_concurrency(processes=cpu_count())
        args = [a.encode('utf-8') if isinstance(a, unicode) else a
                for a in args]
        with TIFF.disable_warnings():
            super(VImage, self).__init__(*args, **kwargs)

    @classmethod
    def new_rgba(cls, width, height, ink=None):
        """Creates a new transparent RGBA image sized width × height."""
        image = cls(b"", b"p")          # Working buffer
        image.initdesc(width=width, height=height,
                       bands=4,                 # RGBA
                       bandfmt=cls.FMTUCHAR,    # 8-bit unsigned
                       coding=cls.NOCODING,     # No coding and no compression
                       type=cls.sRGB,
                       xres=2.835, yres=2.835,  # Arbitrary 600 dpi
                       xoffset=0, yoffset=0)

        if ink is not None:
            image.draw_rect(left=0, top=0, width=width, height=height,
                            fill=True, ink=ink)
        return image

    @classmethod
    def from_vimage(cls, other):
        """Creates a new image from another VImage."""
        new = cls()
        new.__dict__.update(other.__dict__)
        return new

    @classmethod
    def from_gdal_dataset(cls, dataset, band):
        """
        Creates a new 1-band VImage from `dataset` at `band`

        dataset: GDAL Dataset
        band: Number of the band, starting from 1
        """
        with LibVips.disable_warnings():
            filename = dataset.GetFileList()[0]
            image1 = VImage(filename)

            # Extract the band
            image2 = image1.extract_bands(band=(band - 1), nbands=1)

            # Cast to the right datatype, if necessary
            datatype = dataset.GetRasterBand(band).NumPyDataType
            if image2.NumPyType == datatype:
                return image2
            types = dict((v, k) for k, v in cls.NUMPY_TYPES.iteritems())
            image3 = VImage.frombuffer(image2.tobuffer(),
                                       width=image2.Xsize(),
                                       height=image2.Ysize(),
                                       bands=1, format=types[datatype])
            image3._buf = image2
            return image3

    @classmethod
    def frombuffer(cls, buffer, width, height, bands, format):
        """
        Returns a new VImage created from a `buffer` of pixel data.

        buffer: The raw buffer
        width: Integer dimension
        height: Integer dimension
        bands: Number of bands in the buffer
        format: Band format (all bands must be the same format)
        """
        return cls.from_vimage(
            super(VImage, cls).frombuffer(buffer, width, height, bands, format)
        )

    @classmethod
    def from_numpy_array(cls, array, width, height, bands, format):
        """
        Returns a new VImage created from a NumPy `array` of pixel data.

        array: The NumPy array
        width: Integer dimension
        height: Integer dimension
        bands: Number of bands in the buffer
        format: Band format (all bands must be the same format)
        """
        array = array.astype(cls.NUMPY_TYPES[format])
        buf = numpy.getbuffer(array)
        image = cls.from_vimage(
            super(VImage, cls).frombuffer(buf, width, height, bands, format)
        )
        # Hold on to the numpy array to prevent garbage collection
        image._numpy_array = array
        return image

    @classmethod
    def gbandjoin(cls, bands):
        """
        Returns a new VImage that is a bandwise join of `bands`.

        bands: Sequence of VImage objects.
        """
        image = cls.from_vimage(
            super(VImage, cls).gbandjoin(bands)
        )
        # Hold on to the other band to prevent garbage collection
        image._buf = bands
        return image

    def initdesc(self, width, height, bands, bandfmt, coding, type, xres,
                 yres, xoffset, yoffset):
        """Initializes the descriptor for this VImage."""
        super(VImage, self).initdesc(width, height, bands, bandfmt, coding,
                                     type, xres, yres, xoffset, yoffset)

    def bandjoin(self, other):
        image = self.from_vimage(
            super(VImage, self).bandjoin(other)
        )
        # Hold on to the other band to prevent garbage collection
        image._buf = other
        return image

    def draw_rect(self, left, top, width, height, fill, ink):
        return super(VImage, self).draw_rect(left, top, width, height,
                                             int(fill), ink)

    def embed(self, fill, left, top, width, height):
        """Returns a new VImage with this VImage embedded within it."""
        if isinstance(fill, basestring):
            if fill not in self.FILL_OPTIONS:
                raise ValueError('Invalid fill: {0!r}'.format(fill))
            fill = self.FILL_OPTIONS[fill]
        image = self.from_vimage(
            super(VImage, self).embed(fill, left, top, width, height)
        )
        image._buf = self
        return image

    def extract_area(self, left, top, width, height):
        """Returns a new VImage with a region cropped out of this VImage."""
        return self.from_vimage(
            super(VImage, self).extract_area(left, top, width, height)
        )

    def extract_bands(self, band, nbands):
        """
        Returns a new VImage with a reduced number of bands.

        band: First band to extract.
        nbands: Number of bands to extract.
        """
        image = self.from_vimage(
            super(VImage, self).extract_bands(band, nbands)
        )
        # Hold on to the other band to prevent garbage collection
        image._buf = self
        return image

    def affine(self, a, b, c, d, dx, dy, ox, oy, ow, oh,
               interpolate=None):
        """
        Returns a new VImage that is affine transformed from this image.
        Uses `interpolate` as the interpolation method.

        interpolate: interpolation method (near, bilinear). Default: bilinear

        For other parameters, see LibVips.im_affinei()
        """
        if interpolate is None or interpolate == 'bilinear':
            interpolate = VIPS.vips_interpolate_bilinear_static
        elif interpolate == 'near':
            interpolate = VIPS.vips_interpolate_nearest_static
        else:
            raise ValueError(
                'interpolate must be near or bilinear, not {0!r}'.format(
                    interpolate
                )
            )

        # Link output to self, because its buffer is related to self.image()
        # We don't want self to get destructed in C++ when Python garbage
        # collects self if it falls out of scope.
        output = VImage()
        output.__inputref = self

        VIPS.im_affinei(self.image(), output.image(), interpolate,
                        a, b, c, d, dx, dy, ox, oy, ow, oh)

        return output

    def _scale(self, xscale, yscale, interpolate):
        """
        Returns a new VImage that has been scaled by `xscale` and `yscale`.

        xscale: floating point scaling value for image
        yscale: floating point scaling value for image
        interpolate: intepolation method (near, bilinear)
        """
        # Shrink by aligning the corners of the input and output images.
        #
        # See the following blog post, written by the VIPS people:
        # http://libvips.blogspot.ca/2011/12/task-of-day-resize-image-with-align.html
        #
        # This is the image size convention which is ideal for reducing the
        # number of pixels in each direction by an exact fraction (with box
        # filtering, for example). With this convention, there is no
        # extrapolation near the boundary when downsampling.

        # The corners of input.img are located at:
        #     (-.5,-.5), (-.5,m-.5), (n-.5,-.5) and (n-.5,m-.5).
        # The corners of output.img are located at:
        #     (-.5,-.5), (-.5,M-.5), (N-.5,-.5) and (N-.5,M-.5).

        output_width = int(ceil(self.Xsize() * xscale))
        output_height = int(ceil(self.Ysize() * yscale))

        # The affine transformation that sends each input corner to the
        # corresponding output corner is:
        #     X = (M / m) * x + (M / m - 1) / 2
        #     Y = (N / n) * y + (N / n - 1) / 2
        #
        # Since M = m * xscale and N = n * yscale
        #     X = xscale * x + (xscale - 1) / 2
        #     Y = yscale * y + (yscale - 1) / 2
        #
        # Use the transformation matrix:
        #     [[xscale,      0],
        #      [     0, yscale]]
        a, b, c, d = xscale, 0, 0, yscale

        if interpolate == 'near':
            # We don't offset when using Nearest Neighbour
            offset_x = offset_y = 0
        else:
            # Align the corners with the constant term of X and Y
            offset_x = (a - 1) / 2
            offset_y = (d - 1) / 2

        # No translation, so top-left corners match.
        output_x, output_y = 0, 0

        return self.affine(a=a, b=b, c=c, d=d, dx=offset_x, dy=offset_y,
                           ox=output_x, oy=output_y,
                           ow=output_width, oh=output_height,
                           interpolate=interpolate)

    def shrink(self, xscale, yscale):
        """
        Returns a new VImage that has been shrunk by `xscale` and `yscale`.

        xscale: floating point scaling value for image
        yscale: floating point scaling value for image
        """
        if not 0.0 < xscale <= 1.0:
            raise ValueError(
                'xscale {0!r} be between 0.0 and 1.0'.format(xscale)
            )
        if not 0.0 < yscale <= 1.0:
            raise ValueError(
                'yscale {0!r} be between 0.0 and 1.0'.format(yscale)
            )
        return self._scale(xscale=xscale, yscale=yscale,
                           interpolate='bilinear')

    def stretch(self, xscale, yscale):
        """
        Returns a new VImage that has been stretched by `xscale` and `yscale`.

        xscale: floating point scaling value for image
        yscale: floating point scaling value for image
        """
        if xscale < 1.0:
            raise ValueError(
                'xscale {0!r} cannot be less than 1.0'.format(xscale)
            )
        if yscale < 1.0:
            raise ValueError(
                'yscale {0!r} cannot be less than 1.0'.format(yscale)
            )
        return self._scale(xscale=xscale, yscale=yscale, interpolate='near')

    def tms_align(self, tile_width, tile_height, offset):
        """
        Pads and aligns the VIPS Image object to the TMS grid.

        tile_width: Number of pixels for each tile
        tile_height: Number of pixels for each tile
        offset: TMS offset for the lower-left tile
        """
        # Pixel offset from top-left of the aligned image.
        #
        # The y value needs to be converted from the lower-left corner to the
        # top-left corner.
        x = int(round(offset.x * tile_width)) % tile_width
        y = int(round(self.Ysize() - offset.y * tile_height)) % tile_height

        # Number of tiles for the aligned image, rounded up to provide
        # right and bottom borders.
        tiles_x = ceil((self.Xsize() + x / 2) / tile_width)
        tiles_y = ceil((self.Ysize() + y / 2) / tile_height)

        # Pixel width and height for the aligned image.
        width = int(tiles_x * tile_width)
        height = int(tiles_y * tile_height)

        if width == self.Xsize() and height == self.Ysize():
            # No change
            assert x == y == 0
            return self

        # Resize
        return self.from_vimage(
            self.embed(fill=0,  # Transparent
                       left=x, top=y, width=width, height=height)
        )

    def BufferSize(self):
        """Return the size of the buffer in bytes if it were rendered."""
        data_size = self.NumPyType()().itemsize
        return (self.Xsize() * self.Ysize() * self.Bands() * data_size)

    def NumPyType(self):
        """Return the NumPy data type."""
        return self.NUMPY_TYPES[self.BandFmt()]

    def vips2jpeg(self, out):
        if isinstance(out, unicode):
            out = out.encode('utf-8')
        return super(VImage, self).vips2jpeg(out)

    def vips2png(self, out):
        if isinstance(out, unicode):
            out = out.encode('utf-8')
        return super(VImage, self).vips2png(out)

    def write(self, *args):
        args = [a.encode('utf-8') if isinstance(a, unicode) else a
                for a in args]
        return super(VImage, self).write(*args)

    def write_to_memory(self):
        image = VImage('', 't')
        return self.from_vimage(self.write(image))

    def write_to_tempfile(self, prefix='tmp', dir=None, delete=True):
        vipsfile = NamedTemporaryFile(suffix='.v',
                                      prefix=prefix, dir=dir, delete=delete)
        image = self.from_vimage(self.write(vipsfile.name))
        image._buf = vipsfile
        return image


class VipsBand(Band):
    def __init__(self, band, dataset, band_no):
        """
        Refers to a Band in a VipsDataset.

        band: A gdal's Band that holds the SWIG object
        dataset: The VipsDataset that this band belongs to
        band_no: The number of the band in the dataset, 0 based
        """
        super(VipsBand, self).__init__(band, dataset)

        self._band_no = band_no

    @property
    def XSize(self):
        return self._dataset.RasterXSize

    @property
    def YSize(self):
        return self._dataset.RasterYSize

    def ReadAsArray(self, xoff=0, yoff=0, win_xsize=None, win_ysize=None,
                    buf_xsize=None, buf_ysize=None, buf_obj=None):
        """
        Reads from the VIPS buffer into a NumPy array.

        buf parameters are ignored. We always return a new ndarray.
        """
        if any((buf_xsize, buf_ysize, buf_obj)):
            raise ValueError('Cannot handle buf-related parameters')

        image = self._dataset.image

        if win_xsize is None:
            win_xsize = image.Xsize() - xoff

        if win_ysize is None:
            win_ysize = image.Ysize() - yoff

        band = image.extract_bands(band=self._band_no, nbands=1)
        area = band.extract_area(left=xoff, top=yoff,
                                 width=win_xsize, height=win_ysize)

        return numpy.ndarray(shape=(win_xsize, win_ysize),
                             buffer=bytes(area.tobuffer()),
                             dtype=band.NumPyType()).copy()

    # The next methods are there to prevent you from shooting yourself in the
    # foot.
    def ReadRaster(self, *args, **kwargs):
        raise NotImplementedError(
            "Use ReadAsArray or a gdal.Band if you want to read from a band."
        )

    def ReadRaster1(self, *args, **kwargs):
        raise NotImplementedError(
            "Use ReadAsArray or a gdal.Band if you want to read from a band."
        )


class VipsDataset(Dataset):
    def __init__(self, inputfile, *args, **kwargs):
        """
        Opens a GDAL-readable file and holds a VImage for scaling and aligning.
        """
        super(VipsDataset, self).__init__(inputfile, *args, **kwargs)

        self.inputfile = inputfile
        self._image = None

    @property
    def image(self):
        if self._image is None:
            self._image = VImage(self.inputfile)
        return self._image

    def GetRasterBand(self, i):
        return VipsBand(band=super(VipsDataset, self).GetRasterBand(i),
                        dataset=self, band_no=(i - 1))

    def ReadAsArray(self, xoff=0, yoff=0, xsize=None, ysize=None,
                    buf_obj=None):
        """
        Reads from the VIPS buffer at offset (xoff, yoff) into a numpy array.
        """
        if buf_obj is not None:
            raise ValueError('Cannot handle buf-related parameters')

        if xsize is None:
            xsize = self.RasterXSize - xoff

        if ysize is None:
            ysize = self.RasterYSize - yoff

        area = self.image.extract_area(left=xoff, top=yoff,
                                       width=xsize, height=ysize)

        # Get the first band's datatype to be consistent with GDAL's behavior
        datatype = self.GetRasterBand(1).NumPyDataType

        return numpy.ndarray(shape=(self.RasterCount, ysize, xsize),
                             buffer=bytes(area.tobuffer()),
                             dtype=datatype)

    def colorize(self, colors):
        """Replaces this image with a colorized version."""
        with LibVips.disable_warnings():
            nodata = self.GetRasterBand(1).GetNoDataValue()
            self._image = colors.colorize(image=self.image, nodata=nodata)

    def _upsample(self, ratios):
        if ratios == XY(x=1.0, y=1.0):
            # No upsampling needed
            return

        extents = self.GetExtents()
        width, height = extents.dimensions

        logger.debug(
            'Resizing from {src_width} × {src_height} '
            'to {dst_width} × {dst_height}'.format(
                src_width=self.RasterXSize,
                src_height=self.RasterYSize,
                dst_width=int(ceil(self.RasterXSize * ratios.x)),
                dst_height=int(ceil(self.RasterYSize * ratios.y))
            )
        )

        with LibVips.disable_warnings():
            self._image = self.image.stretch(xscale=ratios.x,
                                             yscale=ratios.y)
            # Fix the dataset's metadata
            geotransform = list(self.GetGeoTransform())
            geotransform[1] = width / self._image.Xsize()    # pixel width
            geotransform[5] = -height / self._image.Ysize()  # pixel height
            self.SetGeoTransform(geotransform, local=True)
            self.SetLocalSizes(xsize=self._image.Xsize(),
                               ysize=self._image.Ysize())

    def upsample(self, resolution=None):
        """Upsamples the image to `resolution`."""
        return self._upsample(
            ratios=self.GetScalingRatios(resolution=resolution, places=5)
        )

    def upsample_to_world(self):
        """Upsamples the image to native TMS resolution for the whole world."""
        ratios = self.GetWorldScalingRatios()
        if ratios == XY(x=1.0, y=1.0):
            # No upsampling needed
            return

        result = self._upsample(ratios=ratios)

        # Force world to be full width by changing pixel width
        world = self.GetSpatialReference().GetWorldExtents()
        geotransform = list(self.GetGeoTransform())
        geotransform[1] = world.dimensions.x / self._image.Xsize()
        self.SetGeoTransform(geotransform, local=True)

        return result

    def align_to_grid(self, resolution=None):
        """Aligns the image to the TMS tile grid."""
        if resolution is None:
            resolution = self.GetNativeResolution()
        spatial_ref = self.GetSpatialReference()
        pixel_sizes = spatial_ref.GetPixelDimensions(resolution=resolution)

        # Assume the image is already in the right projection
        extents = self.GetExtents(transform=None)
        tile_extents = self.GetTiledExtents(transform=None)

        left = int(round(
            ((extents.lower_left.x - tile_extents.lower_left.x) /
             pixel_sizes.x)
        ))
        top = int(round(
            ((tile_extents.upper_right.y - extents.upper_right.y) /
             pixel_sizes.y)
        ))

        # Defining
        epsilon_lower = 1e-4
        epsilon_higher = 1 - epsilon_lower

        # Verifying that the width and height are within an acceptable
        # floating point error.
        width = tile_extents.dimensions.x / pixel_sizes.x
        height = tile_extents.dimensions.y / pixel_sizes.y
        if epsilon_lower < (width % 1) < epsilon_higher:
            raise AssertionError(
                'width {0!r} is not within an acceptable range of '
                'an integer'.format(width)
            )
        if epsilon_lower < (height % 1) < epsilon_higher:
            raise AssertionError(
                'height {0!r} is not within an acceptable range of '
                'an integer'.format(height)
            )

        width = int(round(width))
        height = int(round(height))

        if left == top == 0 and \
           width == self.RasterXSize and \
           height == self.RasterYSize:
            # No alignment needed
            return

        if width % TILE_SIDE != 0:
            raise AssertionError(
                'width {0} is not an integer multiple of {1}'.format(
                    width,
                    TILE_SIDE
                )
            )
        if height % TILE_SIDE != 0:
            raise AssertionError(
                'height {0} is not an integer multiple of {1}'.format(
                    height,
                    TILE_SIDE
                )
            )

        logger.debug(
            'Tile aligned at ({longitude}, {latitude})'.format(
                longitude=tile_extents.lower_left.x,
                latitude=tile_extents.upper_right.y,
                x=((tile_extents.lower_left.x / pixel_sizes.x) +
                   (256 << (resolution))),
                y=((256 << (resolution)) +
                   tile_extents.upper_right.y / pixel_sizes.y)
            )
        )
        logger.debug(
            'Aligning within {width} × {height} at ({left}, {top})'.format(
                width=width, height=height, left=left, top=top
            )
        )

        with LibVips.disable_warnings():
            self._image = self.image.embed(fill='black',
                                           left=left, top=top,
                                           width=width, height=height)
            # Fix the dataset's metadata to match tile_extents exactly
            geotransform = list(self.GetGeoTransform())
            geotransform[0] = tile_extents.lower_left.x   # left
            geotransform[3] = tile_extents.upper_right.y  # top
            # pixel width and height
            geotransform[1] = tile_extents.dimensions.x / self._image.Xsize()
            geotransform[5] = -tile_extents.dimensions.y / self._image.Ysize()
            self.SetGeoTransform(geotransform, local=True)
            self.SetLocalSizes(xsize=width, ysize=height)

    # The next methods are there to prevent you from shooting yourself in the
    # foot.
    def ReadRaster(self, *args, **kwargs):
        raise NotImplementedError(
            "Use ReadAsArray or a gdal.Dataset if you want to read from a "
            " dataset."
        )

    def ReadRaster1(self, *args, **kwargs):
        raise NotImplementedError(
            "Use ReadAsArray or a gdal.Dataset if you want to read from a "
            " dataset."
        )


class TmsTiles(object):
    """Represents a set of tiles in TMS co-ordinates."""

    IMAGE_BUFFER_INTERVAL = 4
    IMAGE_BUFFER_MEMORY_THRESHOLD = 1024 ** 2  # 1 MiB
    IMAGE_BUFFER_DISK_THRESHOLD = 1024 ** 3    # 1 GiB

    def __init__(self, image, storage, tile_width, tile_height, offset,
                 resolution):
        """
        image: gdal2mbtiles.vips.VImage
        storage: Storage for rendered tiles
        tile_width: Number of pixels for each tile
        tile_height: Number of pixels for each tile
        offset: TMS offset for the lower-left tile
        resolution: TMS resolution for this image.
        """
        self.image = image
        self.storage = storage
        self.tile_width = tile_width
        self.tile_height = tile_height
        self.offset = offset
        self.resolution = resolution

        # Used to determine whether this TmsTiles is backed by a buffer.
        self._parent = None

    @property
    def image_width(self):
        """Returns the width of self.image in pixels."""
        return self.image.Xsize()

    @property
    def image_height(self):
        """Returns the height of self.image in pixels."""
        return self.image.Ysize()

    def fill_borders(self, borders, resolution):
        for x, y in borders:
            self.storage.save_border(x=x, y=y, z=resolution)

    def _slice(self):
        """Helper function that actually slices tiles. See ``slice``."""
        with LibVips.disable_warnings():
            for y in xrange(0, self.image_height, self.tile_height):
                for x in xrange(0, self.image_width, self.tile_width):
                    out = self.image.extract_area(
                        x, y,                    # left, top offsets
                        self.tile_width, self.tile_height
                    )
                    offset = XY(
                        x=int(x / self.tile_width + self.offset.x),
                        y=int((self.image_height - y) / self.tile_height +
                              self.offset.y - 1)
                    )
                    self.storage.save(x=offset.x, y=offset.y,
                                      z=self.resolution,
                                      image=out)

    def slice(self):
        """
        Slices a VIPS image object into TMS tiles in PNG format.

        If a tile duplicates another tile already known to this process, a
        symlink is created instead of rendering the same tile to PNG again.
        """
        with LibVips.disable_warnings():
            if self.image_width % self.tile_width != 0:
                raise ValueError('image width {0!r} does not contain a whole '
                                 'number of tiles of width {1!r}'.format(
                                     self.image_width, self.tile_width
                                 ))

            if self.image_height % self.tile_height != 0:
                raise ValueError('image height {0!r} does not contain a whole '
                                 'number of tiles of height {1!r}'.format(
                                     self.image_height, self.tile_height
                                 ))

        self._slice()
        self.storage.waitall()

    def downsample(self, levels=1):
        """
        Downsamples the image.

        levels: Number of levels to downsample the image.

        Returns a new TmsTiles object containing the downsampled image.
        """
        assert self.resolution >= levels and levels > 0

        image = self.image
        offset = self.offset

        parent = self._parent if self._parent is not None else self
        parent_resolution = parent.resolution
        parent_size = parent.image.BufferSize()

        for res in reversed(range(self.resolution - levels, self.resolution)):
            offset /= 2.0
            shrunk = image.shrink(xscale=0.5, yscale=0.5)
            image = shrunk.tms_align(tile_width=self.tile_width,
                                     tile_height=self.tile_height,
                                     offset=offset)
            offset = offset.floor()

            # Render to a temporary buffer every IMAGE_BUFFER_INTERVAL levels
            # of scaling.
            #
            # Since VIPS is lazy, it will try to downscale from the parent
            # image, each time you do a render. What you need to do is
            # checkpoint the work every so often, trading off memory or disk
            # space for memory or CPU time.
            #
            # Memory is saved, even when buffering to memory, because VIPS does
            # not need to stream compressed data from the inputfile.
            if parent_resolution - res >= self.IMAGE_BUFFER_INTERVAL:
                if parent_size < self.IMAGE_BUFFER_MEMORY_THRESHOLD:
                    # Not worth buffering because the parent is so small
                    continue

                image = self.write_buffer(image=image, resolution=res)
                parent_resolution = res
                parent_size = image.BufferSize()

        if parent_resolution < parent.resolution:
            # Buffering occurred.
            parent = None
            # The final resolution is not the same as the buffered resolution,
            # so write the buffer once more.
            if parent_resolution != res:
                image = self.write_buffer(image=image, resolution=res)

        result = self.__class__(image=image,
                                storage=self.storage,
                                tile_width=self.tile_width,
                                tile_height=self.tile_height,
                                offset=offset,
                                resolution=res)
        result._parent = parent
        return result

    def upsample(self, levels=1):
        """
        Upsample the image.

        levels: Number of levels to upsample the image.

        Returns a new TmsTiles object containing the upsampled image.
        """
        # Note: You cannot upsample tile-by-tile because it looks ugly at the
        # boundaries.
        assert levels > 0
        scale = 2 ** levels
        offset = self.offset * scale
        stretched = self.image.stretch(xscale=scale, yscale=scale)
        aligned = stretched.tms_align(tile_width=self.tile_width,
                                      tile_height=self.tile_height,
                                      offset=offset)

        return self.__class__(image=aligned,
                              storage=self.storage,
                              tile_width=self.tile_width,
                              tile_height=self.tile_height,
                              offset=offset.floor(),
                              resolution=self.resolution + levels)

    def write_buffer(self, image, resolution):
        if image.BufferSize() >= self.IMAGE_BUFFER_DISK_THRESHOLD:
            logger.debug(
                'Buffering resolution {0} to disk'.format(resolution)
            )
            return image.write_to_tempfile()

        logger.debug(
            'Buffering resolution {0} to memory'.format(resolution)
        )
        return image.write_to_memory()


class TmsPyramid(object):
    """Represents an image pyramid of TMS tiles."""

    TmsTiles = TmsTiles

    def __init__(self, inputfile, storage,
                 min_resolution=None, max_resolution=None):
        """
        Represents a pyramid of PNG tiles.

        inputfile: Filename
        storage: Storage for rendered tiles
        min_resolution: Minimum resolution to downsample tiles.
        max_resolution: Maximum resolution to upsample tiles.

        Filenames are in the format `{tms_z}/{tms_x}-{tms_y}-{image_hash}.png`.

        If a tile duplicates another tile already known to this process, a
        symlink may be created instead of rendering the same tile to PNG again.

        If `min_resolution` is None, don't downsample.
        If `max_resolution` is None, don't upsample.
        """
        self.inputfile = inputfile
        self.storage = storage
        self.min_resolution = min_resolution
        self.max_resolution = max_resolution

        self._dataset = None
        self._resolution = None

    def colorize(self, colors):
        """Replaces this image with a colorized version."""
        return self.dataset.colorize(colors)

    @property
    def dataset(self):
        if self._dataset is None:
            self._dataset = VipsDataset(self.inputfile)
        return self._dataset

    @property
    def image(self):
        return self.dataset.image

    @property
    def resolution(self):
        if self._resolution is None:
            self._resolution = self.dataset.GetNativeResolution()
        return self._resolution

    def get_tiles(self):
        """Returns the TmsTiles object for the native resolution."""
        offset = self.dataset.GetTmsExtents()
        with LibVips.disable_warnings():
            return self.TmsTiles(image=self.image,
                                 storage=self.storage,
                                 tile_width=TILE_SIDE, tile_height=TILE_SIDE,
                                 offset=offset.lower_left,
                                 resolution=self.resolution)

    def slice_downsample(self, tiles, min_resolution, max_resolution=None,
                         fill_borders=None):
        """Downsamples the input TmsTiles down to min_resolution and slices."""
        validate_resolutions(resolution=self.resolution,
                             min_resolution=min_resolution)
        if max_resolution is None or max_resolution >= self.resolution:
            max_resolution = self.resolution - 1

        with LibVips.disable_warnings():
            # Skip resolutions if there's a gap between max_resolution and
            # self.resolution.
            tiles = tiles.downsample(
                levels=(self.resolution - max_resolution),
            )

            for res in reversed(range(min_resolution, max_resolution + 1)):
                logger.debug(
                    'Slicing at downsampled resolution {resolution}: '
                    '{width} × {height}'.format(
                        resolution=res,
                        width=tiles.image.Xsize(),
                        height=tiles.image.Ysize()
                    )
                )

                if fill_borders or fill_borders is None:
                    borders = self.dataset.GetWorldTmsBorders(resolution=res)
                    tiles.fill_borders(borders=borders, resolution=res)
                tiles._slice()

                # Downsample to the next layer, unless we're not going to go
                # through the loop again.
                if res > min_resolution:
                    tiles = tiles.downsample(levels=1)

    def slice_native(self, tiles, fill_borders=None):
        """Slices the input image at native resolution."""
        logger.debug(
            'Slicing at native resolution {resolution}: '
            '{width} × {height}'.format(
                resolution=self.resolution,
                width=self.image.Xsize(),
                height=self.image.Ysize()
            )
        )
        with LibVips.disable_warnings():
            if fill_borders or fill_borders is None:
                tiles.fill_borders(
                    borders=self.dataset.GetWorldTmsBorders(
                        resolution=self.resolution
                    ),
                    resolution=self.resolution
                )
            tiles._slice()

    def slice_upsample(self, tiles, max_resolution, min_resolution=None,
                       fill_borders=None):
        """Upsamples the input TmsTiles up to max_resolution and slices."""
        validate_resolutions(resolution=self.resolution,
                             max_resolution=max_resolution)
        if min_resolution is None or min_resolution <= self.resolution:
            min_resolution = self.resolution + 1

        with LibVips.disable_warnings():
            # Upsampling one zoom level at a time, from the native image.
            for res in range(min_resolution, max_resolution + 1):
                upsampled = tiles.upsample(levels=(res - self.resolution))
                logger.debug(
                    'Slicing at upsampled resolution {resolution}: '
                    '{width} × {height}'.format(
                        resolution=res,
                        width=upsampled.image.Xsize(),
                        height=upsampled.image.Ysize()
                    )
                )

                if fill_borders or fill_borders is None:
                    borders = self.dataset.GetWorldTmsBorders(resolution=res)
                    upsampled.fill_borders(borders=borders, resolution=res)
                upsampled._slice()

    def slice(self, fill_borders=True):
        """Slices the input image into the pyramid of PNG tiles."""
        logger.info('Slicing tiles')
        if self.min_resolution is not None:
            min_resolution = self.min_resolution
        else:
            min_resolution = self.resolution

        if self.max_resolution is not None:
            max_resolution = self.max_resolution
        else:
            max_resolution = self.resolution

        tiles = self.get_tiles()

        if min_resolution <= self.resolution <= max_resolution:
            self.slice_native(tiles, fill_borders=fill_borders)

        if 0 <= min_resolution < self.resolution:
            self.slice_downsample(tiles=tiles,
                                  min_resolution=min_resolution,
                                  max_resolution=max_resolution,
                                  fill_borders=fill_borders)
        if self.resolution < max_resolution:
            self.slice_upsample(tiles=tiles,
                                min_resolution=min_resolution,
                                max_resolution=max_resolution,
                                fill_borders=fill_borders)
        self.storage.waitall()

        # Post-import hook needs to be called in case the storage has to
        # update some metadata
        self.storage.post_import(pyramid=self)


def validate_resolutions(resolution,
                         min_resolution=None, max_resolution=None,
                         strict=True):
    """
    Returns cleaned (min_resolution, max_resolution).

    If strict is True, then it is an error if this condition doesn't hold:
        min_resolution < resolution < max_resolution
    """
    if min_resolution is not None:
        if not strict:
            if min_resolution < 0:
                raise ValueError(
                    'min_resolution {0!r} must be greater than 0'.format(
                        min_resolution
                    )
                )
            if max_resolution is None and min_resolution > resolution:
                raise ValueError(
                    'min_resolution {0!r} must be between 0 and {1}'.format(
                        min_resolution, resolution
                    )
                )
            if max_resolution is not None and min_resolution > max_resolution:
                raise ValueError(
                    'min_resolution {0!r} must be between 0 and {1}'.format(
                        min_resolution, max_resolution
                    )
                )
        elif not 0 <= min_resolution < resolution:
            raise ValueError(
                'min_resolution {0!r} must be between 0 and {1}'.format(
                    min_resolution, resolution
                )
            )

    if max_resolution is not None:
        if strict and max_resolution < resolution:
            raise ValueError(
                'max_resolution {0!r} must be greater than {1}'.format(
                    max_resolution, resolution
                )
            )
        if not strict and \
           resolution > max_resolution and min_resolution is None:
            raise ValueError(
                'max_resolution {0!r} must be greater than {1}'.format(
                    max_resolution, min_resolution
                )
            )

    return min_resolution, max_resolution


# Utility classes for coloring
class ColorList(list):
    """Represents a list of (band_value, color) for a single band."""

    def deduplicate(self):
        """Remove duplicate colors."""
        self[:] = [
            next(g)             # First in the group: smallest expression
            for k, g
            in groupby(self,
                       key=itemgetter(1))  # Group by band color
        ]

    def lstrip(self, value):
        """
        Remove smallest `colors` that are equal to the background for `band`.
        """
        for i, v in enumerate(self):
            if v[1] != value:
                # First non-background color
                self[:] = self[i:]
                return
        self[:] = []


class ColorBase(dict):
    """Base class for ColorExact, ColorPalette, and ColorGradient."""

    # Background is transparent
    BACKGROUND = rgba(r=0, g=0, b=0, a=0)

    @classmethod
    def _background(self, band):
        """Returns the background color for `band`"""
        return getattr(self.BACKGROUND, band)

    def _clauses(self, band, nodata=None):
        raise NotImplementedError()

    def _colors(self, band):
        """Returns a list of (band_value, color) for `band`"""
        colors = ColorList((band_value, getattr(color, band))
                           for band_value, color in self.iteritems())
        colors.sort()
        return colors

    def _colorize_bands(self, data, nodata=None):
        for band in 'rgba':
            expr = self._expression(band=band, nodata=nodata)
            if expr is None:
                # No expression, so create an array filled with the background
                # value.
                array = numpy.empty(shape=data.size, dtype=numpy.uint8)
                array.fill(self._background(band=band))
                yield array
            else:
                # Evaluate expression
                yield numexpr.evaluate(self._expression(band=band,
                                                        nodata=nodata),
                                       local_dict=dict(n=data.copy()),
                                       global_dict={})

    def colorize(self, image, nodata=None):
        """Returns a new RGBA VImage that has been colorized"""
        if image.Bands() != 1:
            raise ValueError(
                'image {0!r} has more than one band'.format(image)
            )

        logging.info('Coloring data')
        logging.debug(
            'Algorithm: {0} {1}'.format(
                type(self).__name__, self
            )
        )

        # Convert to a numpy array
        data = numpy.frombuffer(buffer=image.tobuffer(),
                                dtype=image.NumPyType())

        # Use numexpr to color the data as RGBA bands
        bands = self._colorize_bands(data=data, nodata=nodata)

        # Merge the bands into a single RGBA VImage
        width, height = image.Xsize(), image.Ysize()
        images = [VImage.from_numpy_array(array=band,
                                          width=width, height=height,
                                          bands=1, format=VImage.FMTUCHAR)
                  for band in bands]
        return VImage.gbandjoin(bands=images)

    def _expression(self, band, nodata=None):
        clauses = self._clauses(band=band, nodata=nodata)
        if not clauses:
            return None

        result = str(getattr(self.BACKGROUND, band))  # Set default background
        for expression, true_value in clauses:
            result = 'where({expression}, {true}, {false})'.format(
                expression=expression, true=true_value, false=result
            )
        return bytes(result)


class ColorExact(ColorBase):
    """
    Given the following ColorExact, sorted by key:
    {-2: red,
      0: green,
      2: blue}

    The color line looks like this, with colors at the exact values:

                red    green    blue
                 |       |       |
      ---o---o---o---o---o---o---o---o---o---o---
    ... -4  -3  -2  -1   0   1   2   3   4   5...

    All other values are transparent.
    """

    def _clauses(self, band, nodata=None):
        colors = self._colors(band=band)
        background = self._background(band=band)

        return [('n == {0!r}'.format(band_value),  # Expression
                 color)                            # True value
                for band_value, color in colors
                if band_value != nodata and color != background]


class ColorPalette(ColorBase):
    """
    Given the following ColorPalette, sorted by key:
    {-2: red,
      0: green,
      2: blue}

    The color line looks like this, with solid blocks of color:

           trans | red   | green | blue
             <-- |-->    |-->    |-->
      ---o---o---o---o---o---o---o---o---o---o---
    ... -4  -3  -2  -1   0   1   2   3   4   5...

    All values less than the smallest become transparent.
    """

    def _clauses(self, band, nodata=None):
        colors = self._colors(band=band)
        colors.lstrip(value=self._background(band=band))
        colors.deduplicate()

        result = [('n >= {0!r}'.format(band_value),  # Expression
                   color)                            # True value
                  for band_value, color in colors]

        if nodata is not None and band == 'a' and colors and \
           nodata >= colors[0][0]:
            result.append(('n == {0!r}'.format(nodata),     # Expression
                           self._background(band=band)))    # True value

        return result


class ColorGradient(ColorBase):
    """
    Given the following ColorGradient, sorted by key:
    {-2: red,
      0: green,
      2: blue,
      4: trans}

    The color line looks like this, with a linear gradient between each color:

           trans | red   | green | blue  | trans
             <-- |==-->  |==-->  |==-->  |-->
      ---o---o---o---o---o---o---o---o---o---o---
    ... -4  -3  -2  -1   0   1   2   3   4   5...

    All values less than the smallest become transparent.
    """

    def _linear_gradient(self, colors):
        """
        Returns a list of (band_value, m, b) for y = m * x + b.

        Where y is the new color, and x is the band_value to transform.

        You may note that this is the slope-representation for a line, since we
        are doing linear gradients.

        """
        if not colors:
            return

        prev_value, prev_color = colors[0]
        m = b = None
        for value, color in colors[1:]:
            if prev_color == color:
                # Horizontal line: y = b
                m = 0
                b = prev_color
            else:
                # Solve for (color = m * value + b) with two points
                m = (prev_value - value) / (prev_color - color)
                b = prev_color - m * prev_value
            yield (prev_value, m, b)
            prev_value, prev_color = value, color

        # Last color is constant, but don't repeat it
        if m != 0 and prev_color != b:
            yield (prev_value, 0, prev_color)  # Horizontal line: y = b

    def _clauses(self, band, nodata=None):
        colors = self._colors(band=band)

        result = ColorList(
            ('n >= {0!r}'.format(band_value),     # Expression
             b if m == 0 else '{m!r} * n + {b!r}'.format(m=m, b=b))
            for band_value, m, b in self._linear_gradient(colors)
        )

        if nodata is not None and band == 'a' and colors and \
           nodata >= colors[0][0]:
            result.append(('n == {0!r}'.format(nodata),     # Expression
                           self._background(band=band)))    # True value

        result.lstrip(value=self._background(band=band))
        result.deduplicate()
        return result
