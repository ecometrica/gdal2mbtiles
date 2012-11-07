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

    def initdesc(self, width, height, bands, bandfmt, coding, type, xres,
                 yres, xoffset, yoffset):
        """Initializes the descriptor for this VImage."""
        super(VImage, self).initdesc(width, height, bands, bandfmt, coding,
                                     type, xres, yres, xoffset, yoffset)

    def bandjoin(self, other):
        return self.from_vimage(
            super(VImage, self).bandjoin(other)
        )

    def draw_rect(self, left, top, width, height, fill, ink):
        return super(VImage, self).draw_rect(left, top, width, height,
                                             int(fill), ink)

    def embed(self, fill, left, top, width, height):
        """Returns a new VImage with this VImage embedded within it."""
        if isinstance(fill, basestring):
            if fill not in self.FILL_OPTIONS:
                raise ValueError('Invalid fill: {0!r}'.format(fill))
            fill = self.FILL_OPTIONS[fill]
        return self.from_vimage(
            super(VImage, self).embed(fill, left, top, width, height)
        )

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
        return self.from_vimage(
            super(VImage, self).extract_bands(band, nbands)
        )

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

        output_width = int(self.Xsize() * xscale)
        output_height = int(self.Ysize() * yscale)

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
            offset = XY(x=offset.x / 2.0,
                        y=offset.y / 2.0)

            shrunk = image.shrink(xscale=0.5, yscale=0.5)
            aligned = shrunk.tms_align(tile_width=self.tile_width,
                                       tile_height=self.tile_height,
                                       offset=offset)

            tiles = self.__class__(image=aligned,
                                   storage=self.storage,
                                   tile_width=self.tile_width,
                                   tile_height=self.tile_height,
                                   offset=XY(int(offset.x), int(offset.y)),
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

        offset = XY(self.offset.x * scale,
                    self.offset.y * scale)

        stretched = self.image.stretch(xscale=scale, yscale=scale)
        aligned = stretched.tms_align(tile_width=self.tile_width,
                                      tile_height=self.tile_height,
                                      offset=offset)

        tiles = self.__class__(image=aligned,
                               storage=self.storage,
                               tile_width=self.tile_width,
                               tile_height=self.tile_height,
                               offset=XY(int(offset.x), int(offset.y)),
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

    def slice_downsample(self, tiles, min_resolution):
        """Downsamples the input TmsTiles down to min_resolution and slices."""
        validate_resolutions(resolution=self.resolution,
                             min_resolution=min_resolution)
        with LibVips.disable_warnings():
            # Downsampling one zoom level at a time, using the previous
            # downsampled results.
            for res in reversed(range(min_resolution, self.resolution)):
                tiles = tiles.downsample()
                tiles.fill_borders(
                    borders=self.dataset.GetWorldTmsBorders(resolution=res),
                    resolution=res
                )
                tiles._slice()

    def slice_native(self):
        """Slices the input image at native resolution."""
        with LibVips.disable_warnings():
            offset = self.dataset.GetTmsExtents()
            tiles = self.TmsTiles(image=self.image,
                                  storage=self.storage,
                                  tile_width=TILE_SIDE, tile_height=TILE_SIDE,
                                  offset=offset.lower_left,
                                  resolution=self.resolution)
            tiles.fill_borders(
                borders=self.dataset.GetWorldTmsBorders(
                    resolution=self.resolution
                ),
                resolution=self.resolution
            )
            tiles._slice()
            return tiles

    def slice_upsample(self, tiles, max_resolution):
        """Upsamples the input TmsTiles up to max_resolution and slices."""
        validate_resolutions(resolution=self.resolution,
                             max_resolution=max_resolution)
        with LibVips.disable_warnings():
            # Upsampling one zoom level at a time, from the native image.
            for res in range(self.resolution + 1, max_resolution + 1):
                upsampled = tiles.upsample(levels=(res - self.resolution))
                upsampled.fill_borders(
                    borders=self.dataset.GetWorldTmsBorders(resolution=res),
                    resolution=res
                )
                upsampled._slice()

    def slice(self):
        """Slices the input image into the pyramid of PNG tiles."""
        validate_resolutions(resolution=self.resolution,
                             min_resolution=self.min_resolution,
                             max_resolution=self.max_resolution)

        tiles = self.slice_native()
        if self.min_resolution is not None:
            self.slice_downsample(tiles=tiles,
                                  min_resolution=self.min_resolution)
        if self.max_resolution is not None:
            self.slice_upsample(tiles=tiles,
                                max_resolution=self.max_resolution)
        self.storage.waitall()

        # Post-import hook needs to be called in case the storage has to
        # update some metadata
        self.storage.post_import(pyramid=self)


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

class ColorBase(dict):
    """Base class for ColorExact, ColorPalette, and ColorGradient."""

    # Background is transparent
    BACKGROUND = rgba(r=0, g=0, b=0, a=0)

    def _numexpr_clauses(self, band, nodata=None):
        raise NotImplementedError()

    def _as_numexpr(self, band, nodata=None):
        clauses = self._numexpr_clauses(band=band, nodata=nodata)

        result = str(getattr(self.BACKGROUND, band))  # Set default background
        for expression, true_value in clauses:
            result = 'where({expression}, {true}, {false})'.format(
                expression=expression, true=true_value, false=result
            )
        return result

    def colorize(self, image, nodata=None):
        context = dict(n=image)
        r, g, b, a = [numexpr.evaluate(self._as_numexpr(band='r',
                                                        datatype=image.dtype,
                                                        nodata=nodata),
                                       local_dict=context, global_dict={})
                      for b in 'rgba']
        rgba = r.bandjoin(g).bandjoin(b).bandjoin(a)

        self.initdesc(width=image.Xsize(), height=image.Ysize(),
                      bands=4,                  # RGBA
                      bandfmt=VImage.FMTUCHAR,  # 8-bit unsigned
                      coding=VImage.NOCODING,   # No coding and no compression
                      type=VImage.sRGB,
                      xres=image.Xres(), yres=image.Yres(),
                      xoffset=image.Xoffset(), yoffset=image.Yoffset())
        return rgba


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

    def _numexpr_clauses(self, band, nodata=None):
        # Extract band-specific colors
        background = getattr(self.BACKGROUND, band)
        colors = sorted([(band_value, getattr(color, band))
                         for band_value, color in self.iteritems()])

        return [('n == {0}'.format(band_value),  # Expression
                 color)                          # True value
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

    def _numexpr_clauses(self, band, nodata=None):
        # Extract band-specific colors
        colors = sorted([(band_value, getattr(color, band))
                         for band_value, color in sorted(self.items())])
        if not colors:
            return []

        # Remove duplicate colors
        background = getattr(self.BACKGROUND, band)
        colors = [
            next(g)             # First in the group: smallest expression
            for k, g
            in groupby(colors, key=itemgetter(1))  # Group by band color
        ]
        if background == colors[0][1]:
            # First color is also the background, so just drop it
            del colors[0]

        result = [('n >= {0}'.format(band_value),  # Expression
                   color)                          # True value
                  for band_value, color in colors]

        if nodata is not None and band == 'a':
            result.append(('n == {0}'.format(nodata),  # Expression
                           background))                # True value

        return result
