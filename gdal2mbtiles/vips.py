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

import os

from contextlib import contextmanager
from ctypes import c_double, c_int, c_void_p, cdll
from ctypes.util import find_library
from itertools import groupby
import logging
from math import ceil, floor
from multiprocessing import cpu_count
from operator import itemgetter

import numexpr
import numpy

from .constants import TILE_SIDE
from .gdal import Dataset, Band
from .gd_types import rgba, XY
from .utils import tempenv

from pyvips import Image, Interpolate
from pyvips.enums import BandFormat, Coding

try:
  basestring
except NameError:
  basestring = str

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

    def get_concurrency(self):
        """Returns the number of threads used for computations."""
        return c_int.in_dll(self.libvips, 'vips__concurrency').value

    def set_concurrency(self, processes):
        """Sets the number of threads used for computations."""
        if not isinstance(processes, int) or processes < 0:
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


class VImageAdapter(object):
    """
    Class to prvovide some additional methods to manipulate a pyvips.Image
    """

    FILL_OPTIONS = {
        'black': 0,                 # Fill bands with 0
        'extend': 1,                # Extend bands from image to edge
        'tile': 2,                  # Tile bands from image
        'mirror': 3,                # Mirror bands from image
        'white': 4,                 # Fill bands with 255
    }

    NUMPY_TYPES = {
        BandFormat.CHAR: numpy.int8,
        BandFormat.UCHAR: numpy.uint8,
        BandFormat.SHORT: numpy.int16,
        BandFormat.USHORT: numpy.uint16,
        BandFormat.INT: numpy.int32,
        BandFormat.UINT: numpy.uint32,
        BandFormat.FLOAT: numpy.float32,
        BandFormat.DOUBLE: numpy.float64,
        BandFormat.COMPLEX: numpy.complex64,
        BandFormat.DPCOMPLEX: numpy.complex128,
    }

    def __init__(self, image, *args, **kwargs):
        # image: a pyvips.Image object
        self.image = image
        if VIPS.get_concurrency() == 0:
            # Override auto-detection from environ and argv.
            VIPS.set_concurrency(processes=cpu_count())
        args = [a.encode('utf-8') if isinstance(a, str) else a
                for a in args]
        with TIFF.disable_warnings():
            super(VImageAdapter, self).__init__(*args, **kwargs)

    @classmethod
    def new_rgba(cls, width, height, ink=None):
        """Creates a new transparent RGBA image sized width × height."""
        # Creating a placeholder image with new_from_memory (equivalent of the
        # old vipsCC frombuffer) creates an image
        # which is a few byes different when written back to memory, which means
        # we can't store and retrieve it from its hash.  So instead we use a
        # temporary transparent 256x256 file for the initial image
        image = Image.new_from_file(
            os.path.join(
                os.path.dirname(os.path.realpath(__file__)), 'default_rgba.png'
            )
        )
        image = image.copy(
            width=width, height=height,
            coding='none',  # No coding and no compression
            interpretation='srgb',
            xres=2.835, yres=2.835,  # Arbitrary 600 dpi
            xoffset=0, yoffset=0  # Working buffer
        )
        if ink is not None:
            image.draw_rect(
                [ink.r, ink.g, ink.b, ink.a], 0, 0, width, height, fill=True
            )
        return image

    @classmethod
    def from_gdal_dataset(cls, dataset, band):
        """
        Creates a new 1-band pyvips.Image from `dataset` at `band`

        dataset: GDAL Dataset
        band: Number of the band, starting from 1
        """
        with LibVips.disable_warnings():
            filename = dataset.GetFileList()[0]
            image1 = Image.new_from_file(filename)

            # Extract the band
            image2 = image1.extract_band((band - 1), n=1)

            # Cast to the right datatype, if necessary
            datatype = dataset.GetRasterBand(band).NumPyDataType
            if VImageAdapter(image2).NumPyType() == datatype:
                return image2
            types = dict((v, k) for k, v in cls.NUMPY_TYPES.items())
            image3 = Image.new_from_memory(image2.write_to_memory(),
                                           width=image2.width,
                                           height=image2.height,
                                           bands=1, format=types[datatype])
            image3._buf = image2
            return image3

    @classmethod
    def from_numpy_array(cls, array, width, height, bands, format):
        """
        Returns a new pyvips.Image created from a NumPy `array` of pixel data.

        array: The NumPy array
        width: Integer dimension
        height: Integer dimension
        bands: Number of bands in the buffer
        format: Band format (all bands must be the same format)
        """
        array = array.astype(cls.NUMPY_TYPES[format])
        buf = memoryview(array)
        image = Image.new_from_memory(buf, width, height, bands, format)

        # Hold on to the numpy array to prevent garbage collection
        image._numpy_array = array
        return image

    @classmethod
    def gbandjoin(cls, bands):
        """
        Returns a new pyvips.Image that is a bandwise join of `bands`.

        bands: Sequence of pyvips.Image objects.

        This previously used the vipsCC gbandjoin method which doesn't
        exist in pyvips.  pyvips' bandjoin method takes either a single 'other'
        band or a list of bands, so we can make it join the first image in the
        list to the remainder
        """
        return bands[0].bandjoin(bands[1:])

    @classmethod
    def get_fill_option(cls, fill):
        # TODO get rid of this?  No option to pass the fill colour
        if isinstance(fill, basestring):
            if fill not in cls.FILL_OPTIONS:
                raise cls('Invalid fill: {0!r}'.format(fill))
            return cls.FILL_OPTIONS[fill]

    def affine(self, a, b, c, d, dx, dy, ox, oy, ow, oh,
               interpolate='bilinear'):
        """
        Returns a new pyvips.Image that is affine transformed from this image.
        Uses `interpolate` as the interpolation method.

        interpolate: interpolation method (near, bilinear). Default: bilinear
        """
        if interpolate == 'near':
            interpolate = 'nearest'

        if interpolate == 'bilinear' or interpolate == 'nearest':
            interpolate = Interpolate.new(interpolate)
        else:
            raise ValueError(
                'interpolate must be near or bilinear, not {0!r}'.format(
                    interpolate
                )
            )

        # Link output to self, because its buffer is related to self.image()
        # We don't want self to get destructed in C++ when Python garbage
        # collects self if it falls out of scope.

        image = self.image.affine(
            [a, b, c, d],
            interpolate=interpolate,
            oarea=[ox, oy, ow, oh],
            odx=dx, ody=dy,
            idx=0, idy=0
        )
        image.__inputref = self.image
        # output = VIPS.im_affinei(self.image, self.image.copy(), interpolate,
        #                 a, b, c, d, dx, dy, ox, oy, ow, oh)

        return image

    def _scale(self, xscale, yscale, output_size, interpolate):
        """
        Returns a new pyvips.Image that has been scaled by `xscale` and `yscale`.

        xscale: floating point scaling value for image
        yscale: floating point scaling value for image
        output_size: output width and height in pixels (tuple)
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

        if output_size is None:
            if XY(x=xscale, y=yscale) > XY(x=1.0, y=1.0):
                output_width = int(ceil(self.image.width * xscale))
                output_height = int(ceil(self.image.height * yscale))
            else:
                output_width = int(floor(self.image.width * xscale))
                output_height = int(floor(self.image.height * yscale))
        else:
            output_width, output_height = output_size

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

    def shrink_affine(self, xscale, yscale, output_size=None):
        """
        Image.shrink uses lipvips shrink method which use reduce, not affine,
        for any residual shrink.  This method uses affine.

        Returns a new pyvips.Image that has been shrunk by `xscale` and `yscale`.

        xscale: floating point scaling value for image
        yscale: floating point scaling value for image
        output_size: output width and height in pixels (tuple)
        """
        if not 0.0 < xscale <= 1.0:
            raise ValueError(
                'xscale {0!r} be between 0.0 and 1.0'.format(xscale)
            )
        if not 0.0 < yscale <= 1.0:
            raise ValueError(
                'yscale {0!r} be between 0.0 and 1.0'.format(yscale)
            )
        return self._scale(
            xscale=xscale, yscale=yscale, output_size=output_size, interpolate='bilinear'
        )

    def stretch(self, xscale, yscale, output_size=None):
        """
        Returns a new pyvips.Image that has been stretched by `xscale` and `yscale`.

        xscale: floating point scaling value for image
        yscale: floating point scaling value for image
        output_size: output width and height in pixels (tuple)
        """
        if xscale < 1.0:
            raise ValueError(
                'xscale {0!r} cannot be less than 1.0'.format(xscale)
            )
        if yscale < 1.0:
            raise ValueError(
                'yscale {0!r} cannot be less than 1.0'.format(yscale)
            )
        return self._scale(
            xscale=xscale, yscale=yscale, output_size=output_size,
            interpolate='near'
        )

    def tms_align(self, tile_width, tile_height, offset):
        """
        Pads and aligns the VIPS Image object to the TMS grid.

        tile_width: Number of pixels for each tile
        tile_height: Number of pixels for each tile
        offset: TMS offset for the lower-left tile

        returns a new Image object
        """
        # Pixel offset from top-left of the aligned image.
        #
        # The y value needs to be converted from the lower-left corner to the
        # top-left corner.
        x = int(round(offset.x * tile_width)) % tile_width
        y = int(round(self.image.height - offset.y * tile_height)) % tile_height

        # Number of tiles for the aligned image, rounded up to provide
        # right and bottom borders.
        tiles_x = ceil((self.image.width + x / 2) / tile_width)
        tiles_y = ceil((self.image.height + y / 2) / tile_height)

        # Pixel width and height for the aligned image.
        width = int(tiles_x * tile_width)
        height = int(tiles_y * tile_height)

        if width == self.image.width and height == self.image.height:
            # No change
            assert x == y == 0
            return self.image

        # Resize
        return self.image.embed(
            x, y, width, height, background=[0, 0, 0, 0]  # Transparent
        )

    def BufferSize(self):
        """Return the size of the buffer in bytes if it were rendered."""
        data_size = self.NumPyType().itemsize
        return self.image.width * self.image.height * self.image.bands * data_size

    def NumPyType(self):
        """Return an instance of the NumPy data type."""
        return self.NUMPY_TYPES[self.image.format]()

    def write(self, *args):
        args = [a.encode('utf-8') if isinstance(a, str) else a
                for a in args]
        return self.image.write(*args)


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
            win_xsize = image.width - xoff

        if win_ysize is None:
            win_ysize = image.height - yoff

        band = image.extract_band(self._band_no, n=1)
        area = band.extract_area(xoff, yoff, win_xsize, win_ysize)

        return numpy.ndarray(shape=(win_xsize, win_ysize),
                             buffer=area.write_to_memory(),
                             dtype=VImageAdapter(band).NumPyType()).copy()

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
            self._image = Image.new_from_file(self.inputfile)
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

        area = self.image.extract_area(xoff, yoff, xsize, ysize)

        # Get the first band's datatype to be consistent with GDAL's behavior
        datatype = self.GetRasterBand(1).NumPyDataType

        return numpy.ndarray(shape=(self.RasterCount, ysize, xsize),
                             buffer=bytes(area.write_to_memory()),
                             dtype=datatype)

    def colorize(self, colors):
        """Replaces this image with a colorized version."""
        with LibVips.disable_warnings():
            nodata = self.GetRasterBand(1).GetNoDataValue()
            self._image = colors.colorize(image=self.image, nodata=nodata)

    def _resample(self, ratios):
        if ratios == XY(x=1.0, y=1.0):
            # No upsampling needed
            return

        extents = self.GetExtents()
        width, height = extents.dimensions

        if ratios > XY(x=1.0, y=1.0):
            dst_width = int(ceil(self.RasterXSize * ratios.x))
            dst_height = int(ceil(self.RasterYSize * ratios.y))
        else:
            dst_width = int(floor(self.RasterXSize * ratios.x))
            dst_height = int(floor(self.RasterYSize * ratios.y))
        logger.debug(
            'Resizing from {src_width} × {src_height} '
            'to {dst_width} × {dst_height}'.format(
                src_width=self.RasterXSize,
                src_height=self.RasterYSize,
                dst_width=dst_width,
                dst_height=dst_height
            )
        )

        with LibVips.disable_warnings():
            if ratios > XY(x=1.0, y=1.0):
                self._image = VImageAdapter(self.image).stretch(
                    xscale=ratios.x, yscale=ratios.y,
                    output_size=(dst_width, dst_height)
                )
            else:
                self._image = VImageAdapter(self.image).shrink_affine(
                    xscale=ratios.x, yscale=ratios.y,
                    output_size=(dst_width, dst_height)
                )

            # Fix the dataset's metadata
            geotransform = list(self.GetGeoTransform())
            geotransform[1] = width / self._image.width    # pixel width
            geotransform[5] = -height / self._image.height  # pixel height
            self.SetGeoTransform(geotransform, local=True)
            self.SetLocalSizes(xsize=self._image.width,
                               ysize=self._image.height)

    def resample(self, resolution=None):
        """Resamples the image to `resolution`."""
        return self._resample(
            ratios=self.GetScalingRatios(resolution=resolution, places=5)
        )

    def resample_to_world(self):
        """Resamples the image to native TMS resolution for the whole world."""
        ratios = self.GetWorldScalingRatios()
        if ratios == XY(x=1.0, y=1.0):
            # No resampling needed
            return

        result = self._resample(ratios=ratios)

        # Force world to be full width by changing pixel width
        world = self.GetSpatialReference().GetWorldExtents()
        geotransform = list(self.GetGeoTransform())
        geotransform[1] = world.dimensions.x / self._image.width
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
            self._image = self.image.embed(
                left, top, width, height,
                background=[VImageAdapter.FILL_OPTIONS['black']]
            )
            # Fix the dataset's metadata to match tile_extents exactly
            geotransform = list(self.GetGeoTransform())
            geotransform[0] = tile_extents.lower_left.x   # left
            geotransform[3] = tile_extents.upper_right.y  # top
            # pixel width and height
            geotransform[1] = tile_extents.dimensions.x / self._image.width
            geotransform[5] = -tile_extents.dimensions.y / self._image.height
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
        return self.image.width

    @property
    def image_height(self):
        """Returns the height of self.image in pixels."""
        return self.image.height

    def fill_borders(self, borders, resolution):
        for x, y in borders:
            self.storage.save_border(x=x, y=y, z=resolution)

    def _slice(self):
        """Helper function that actually slices tiles. See ``slice``."""
        with LibVips.disable_warnings():
            xys = []
            for y in range(0, self.image_height, self.tile_height):
                for x in range(0, self.image_width, self.tile_width):
                    out = self.image.extract_area(
                        x, y,                    # left, top offsets
                        self.tile_width, self.tile_height
                    )
                    offset = XY(
                        x=int(x / self.tile_width + self.offset.x),
                        y=int((self.image_height - y) / self.tile_height +
                              self.offset.y - 1)
                    )
                    xys.append((x, y))
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
        parent_size = VImageAdapter(parent.image).BufferSize()

        for res in reversed(list(range(self.resolution - levels, self.resolution))):
            offset /= 2.0
            shrunk = VImageAdapter(image).shrink_affine(xscale=0.5, yscale=0.5)
            image = VImageAdapter(shrunk).tms_align(tile_width=self.tile_width,
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
                parent_size = VImageAdapter(image).BufferSize()

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
        stretched = VImageAdapter(self.image).stretch(xscale=scale, yscale=scale)
        aligned = VImageAdapter(stretched).tms_align(tile_width=self.tile_width,
                                      tile_height=self.tile_height,
                                      offset=offset)

        return self.__class__(image=aligned,
                              storage=self.storage,
                              tile_width=self.tile_width,
                              tile_height=self.tile_height,
                              offset=offset.floor(),
                              resolution=self.resolution + levels)

    def write_buffer(self, image, resolution):
        if VImageAdapter(image).BufferSize() >= self.IMAGE_BUFFER_DISK_THRESHOLD:
            logger.debug(
                'Buffering resolution {0} to disk'.format(resolution)
            )
            vipsfile = Image.new_temp_file("%s.v")
            tempfile_image = image.write(vipsfile)
            return tempfile_image

        logger.debug(
            'Buffering resolution {0} to memory'.format(resolution)
        )
        return Image.new_from_memory(
            image.write_to_memory(), image.width, image.height, image.bands,
            'uchar'
        )


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

            for res in reversed(list(range(min_resolution, max_resolution + 1))):
                logger.debug(
                    'Slicing at downsampled resolution {resolution}: '
                    '{width} × {height}'.format(
                        resolution=res,
                        width=tiles.image.width,
                        height=tiles.image.height
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
                width=self.image.width,
                height=self.image.height
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
                        width=upsampled.image.width,
                        height=upsampled.image.height
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
                           for band_value, color in self.items())
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
        if image.bands != 1:
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
        data = numpy.frombuffer(buffer=image.write_to_memory(),
                                dtype=VImageAdapter(image).NumPyType())

        # Use numexpr to color the data as RGBA bands
        bands = self._colorize_bands(data=data, nodata=nodata)

        # Merge the bands into a single RGBA VImage
        images = [VImageAdapter.from_numpy_array(
            array=band, width=image.width, height=image.height, bands=1,
            format='uchar'
        ) for band in bands]

        return VImageAdapter.gbandjoin(bands=images)

    def _expression(self, band, nodata=None):
        clauses = self._clauses(band=band, nodata=nodata)
        if not clauses:
            return None

        result = str(getattr(self.BACKGROUND, band))  # Set default background
        for expression, true_value in clauses:
            result = 'where({expression}, {true}, {false})'.format(
                expression=expression, true=true_value, false=result
            )
        return result


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
