# -*- coding: utf-8 -*-

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

from ctypes import c_double, c_int, c_void_p, cdll
from ctypes.util import find_library
from itertools import groupby
from math import ceil
from multiprocessing import cpu_count
from operator import itemgetter

import numexpr
import numpy

from vipsCC.VError import VError
import vipsCC.VImage

from .constants import TILE_SIDE
from .gdal import Dataset
from .types import rgba, XY
from .utils import tempenv


class LibVips(object):
    """Wrapper object around C library."""

    def __init__(self, version=None):
        library = find_library('vips')
        if version is not None or library is None:
            library = 'libvips.so.{0:d}'.format(version)
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
        if args and isinstance(args[0], unicode):
            # args[0] is a Unicode filename
            args = list(args)
            args[0] = args[0].encode('utf-8')
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

        output_width = int(round(self.Xsize() * xscale))
        output_height = int(round(self.Ysize() * yscale))

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
        _type = 0               # Transparent

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
        return self.from_vimage(self.embed(_type, x, y, width, height))

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


class TmsTiles(object):
    """Represents a set of tiles in TMS co-ordinates."""

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
        Downsamples the image by one resolution.

        Returns a new TmsTiles object containing the downsampled image.
        """
        assert self.resolution >= levels and levels > 0

        image = self.image
        offset = self.offset

        for res in reversed(range(self.resolution - levels, self.resolution)):
            offset /= 2.0

            shrunk = image.shrink(xscale=0.5, yscale=0.5)
            aligned = shrunk.tms_align(tile_width=self.tile_width,
                                       tile_height=self.tile_height,
                                       offset=offset)

            tiles = self.__class__(image=aligned,
                                   storage=self.storage,
                                   tile_width=self.tile_width,
                                   tile_height=self.tile_height,
                                   offset=offset.floor(),
                                   resolution=res)
            image = tiles.image
        return tiles

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

        tiles = self.__class__(image=aligned,
                               storage=self.storage,
                               tile_width=self.tile_width,
                               tile_height=self.tile_height,
                               offset=offset.floor(),
                               resolution=self.resolution + levels)
        return tiles


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
        self._image = None
        self._resolution = None

    def colorize(self, colors):
        """Replaces this image with a colorized version."""
        with LibVips.disable_warnings():
            nodata = self.dataset.GetRasterBand(1).GetNoDataValue()
            self._image = colors.colorize(image=self.image, nodata=nodata)

    @property
    def dataset(self):
        if self._dataset is None:
            self._dataset = Dataset(self.inputfile)
        return self._dataset

    @property
    def image(self):
        if self._image is None:
            self._image = VImage(self.inputfile)
        return self._image

    @property
    def resolution(self):
        if self._resolution is None:
            self._resolution = self.dataset.GetNativeResolution()
        return self._resolution

    def slice_downsample(self, tiles, min_resolution, fill_borders=None):
        """Downsamples the input TmsTiles down to min_resolution and slices."""
        validate_resolutions(resolution=self.resolution,
                             min_resolution=min_resolution)
        with LibVips.disable_warnings():
            # Downsampling one zoom level at a time, using the previous
            # downsampled results.
            for res in reversed(range(min_resolution, self.resolution)):
                tiles = tiles.downsample()
                if fill_borders or fill_borders is None:
                    tiles.fill_borders(
                        borders=self.dataset.GetWorldTmsBorders(resolution=res),
                        resolution=res
                    )
                tiles._slice()

    def slice_native(self, fill_borders=None):
        """Slices the input image at native resolution."""
        with LibVips.disable_warnings():
            offset = self.dataset.GetTmsExtents()
            tiles = self.TmsTiles(image=self.image,
                                  storage=self.storage,
                                  tile_width=TILE_SIDE, tile_height=TILE_SIDE,
                                  offset=offset.lower_left,
                                  resolution=self.resolution)
            if fill_borders or fill_borders is None:
                tiles.fill_borders(
                    borders=self.dataset.GetWorldTmsBorders(
                        resolution=self.resolution
                    ),
                    resolution=self.resolution
                )
            tiles._slice()
            return tiles

    def slice_upsample(self, tiles, max_resolution, fill_borders=None):
        """Upsamples the input TmsTiles up to max_resolution and slices."""
        validate_resolutions(resolution=self.resolution,
                             max_resolution=max_resolution)
        with LibVips.disable_warnings():
            # Upsampling one zoom level at a time, from the native image.
            for res in range(self.resolution + 1, max_resolution + 1):
                upsampled = tiles.upsample(levels=(res - self.resolution))
                if fill_borders or fill_borders is None:
                    upsampled.fill_borders(
                        borders=self.dataset.GetWorldTmsBorders(resolution=res),
                        resolution=res
                    )
                upsampled._slice()

    def slice(self, fill_borders=True):
        """Slices the input image into the pyramid of PNG tiles."""
        validate_resolutions(resolution=self.resolution,
                             min_resolution=self.min_resolution,
                             max_resolution=self.max_resolution)

        tiles = self.slice_native(fill_borders=fill_borders)
        if self.min_resolution is not None:
            self.slice_downsample(tiles=tiles,
                                  min_resolution=self.min_resolution,
                                  fill_borders=fill_borders)
        if self.max_resolution is not None:
            self.slice_upsample(tiles=tiles,
                                max_resolution=self.max_resolution,
                                fill_borders=fill_borders)
        self.storage.waitall()

        # Post-import hook needs to be called in case the storage has to
        # update some metadata
        self.storage.post_import(pyramid=self)

    def _upsample(self, ratios):
        if ratios == XY(x=1.0, y=1.0):
            # No upsampling needed
            return

        extents = self.dataset.GetExtents()
        width, height = extents.dimensions

        with LibVips.disable_warnings():
            self._image = self.image.stretch(xscale=ratios.x,
                                             yscale=ratios.y)
            # Fix the dataset's metadata
            geotransform = list(self.dataset.GetGeoTransform())
            geotransform[1] = width / self._image.Xsize()    # pixel width
            geotransform[5] = -height / self._image.Ysize()  # pixel height
            self.dataset.SetGeoTransform(geotransform, local=True)
            self.dataset.SetLocalSizes(xsize=self._image.Xsize(),
                                       ysize=self._image.Ysize())

    def upsample(self, resolution=resolution):
        """Upsamples the image to `resolution`."""
        return self._upsample(
            ratios=self.dataset.GetTileScalingRatios(resolution=resolution,
                                                     places=5)
        )

    def upsample_to_world(self):
        """Upsamples the image to native TMS resolution for the whole world."""
        ratios = self.dataset.GetWorldScalingRatios()
        if ratios == XY(x=1.0, y=1.0):
            # No upsampling needed
            return

        result = self._upsample(ratios=ratios)

        # Force world to be full width by changing pixel width
        world = self.dataset.GetSpatialReference().GetWorldExtents()
        geotransform = list(self.dataset.GetGeoTransform())
        geotransform[1] = world.dimensions.x / self._image.Xsize()
        self.dataset.SetGeoTransform(geotransform, local=True)

        return result

    def align_to_grid(self, resolution=None):
        """Aligns the image to the TMS tile grid."""
        if resolution is None:
            resolution = self.dataset.GetNativeResolution()
        spatial_ref = self.dataset.GetSpatialReference()
        pixel_sizes = spatial_ref.GetPixelDimensions(resolution=resolution)

        # Assume the image is already in the right projection
        extents = self.dataset.GetExtents(transform=None)
        tile_extents = self.dataset.GetTiledExtents(transform=None)

        left = int(round(
            ((extents.lower_left.x - tile_extents.lower_left.x) /
             pixel_sizes.x)
        ))
        top = int(round(
            ((tile_extents.upper_right.y - extents.upper_right.y) /
             pixel_sizes.y)
        ))

        width = int(tile_extents.dimensions.x / pixel_sizes.x)
        height = int(tile_extents.dimensions.y / pixel_sizes.y)

        if left == top == 0 and \
           width == self.dataset.RasterXSize and \
           height == self.dataset.RasterYSize:
            # No alignment needed
            return

        if width % TILE_SIDE != 0:
            raise AssertionError(
                'width {0} is not an integer multiple of {1}'.format(width,
                                                                     TILE_SIDE)
            )
        if height % TILE_SIDE != 0:
            raise AssertionError(
                'height {0} is not an integer multiple of {1}'.format(height,
                                                                      TILE_SIDE)
            )

        with LibVips.disable_warnings():
            self._image = self.image.embed(fill='black',
                                           left=left, top=top,
                                           width=width, height=height)
            # Fix the dataset's metadata
            geotransform = list(self.dataset.GetGeoTransform())
            geotransform[0] -= left * pixel_sizes.x  # left
            geotransform[3] += top * pixel_sizes.y   # top
            self.dataset.SetGeoTransform(geotransform, local=True)
            self.dataset.SetLocalSizes(xsize=width, ysize=height)


def validate_resolutions(resolution, min_resolution=None,
                         max_resolution=None):
    if min_resolution is not None and \
       not 0 <= min_resolution < resolution:
        raise ValueError(
            'min_resolution {0!r} must be between 0 and {1}'.format(
                min_resolution, resolution
            )
        )

    if max_resolution is not None and max_resolution < resolution:
        raise ValueError(
            'max_resolution {0!r} must be greater than {1}'.format(
                max_resolution, resolution
            )
        )


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
