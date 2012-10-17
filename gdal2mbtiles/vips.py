# -*- coding: utf-8 -*-

from __future__ import absolute_import, division

from math import ceil
import os

import vipsCC.VImage

from .constants import TILE_SIDE
from .gdal import Dataset
from .renderers import PngRenderer
from .storages import SimpleFileStorage
from .types import XY
from .utils import tempenv


class VImage(vipsCC.VImage.VImage):
    FILL_OPTIONS = {
        'black': 0,                 # Fill bands with 0
        'extend': 1,                # Extend bands from image to edge
        'tile': 2,                  # Tile bands from image
        'mirror': 3,                # Mirror bands from image
        'white': 4,                 # Fill bands with 255
    }

    def __init__(self, *args, **kwargs):
        super(VImage, self).__init__(*args, **kwargs)

    @classmethod
    def new_rgba(cls, width, height):
        """Creates a new transparent RGBA image sized width × height."""
        bands = 4                  # RGBA
        bandfmt = cls.FMTUCHAR     # 8-bit unsigned
        coding = cls.NOCODING      # No coding and no compression
        _type = cls.sRGB
        xres, yres = 2.835, 2.835  # Arbitrary 600 dpi
        xo, yo = 0, 0

        image = cls("", "p")       # Working buffer
        image.initdesc(width, height, bands, bandfmt, coding, _type,
                       xres, yres, xo, yo)
        return image

    @classmethod
    def from_vimage(cls, other):
        """Creates a new image from another VImage."""
        new = cls()
        new.__dict__.update(other.__dict__)
        return new

    @classmethod
    def disable_warnings(cls):
        """Context manager to disable VIPS warnings."""
        return tempenv('IM_WARNING', '0')

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

    def _scale(self, xscale, yscale):
        """
        Returns a new VImage that has been scaled by `xscale` and `yscale`.

        xscale: floating point scaling value for image
        yscale: floating point scaling value for image
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

        # Align the corners with the constant term of X and Y
        offset_x = (a - 1) / 2
        offset_y = (d - 1) / 2

        # No translation, so top-left corners match.
        output_x, output_y = 0, 0

        return self.from_vimage(
            self.affine(a, b, c, d, offset_x, offset_y,
                        output_x, output_y, output_width, output_height)
        )

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
        return self._scale(xscale=xscale, yscale=yscale)

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

        # We need to extend the image past its border so that interpolation
        # does not cause black borders due to missing data.
        border = XY(1, 1)               # Add a pixel border for interpolation
        extended = self.embed(fill='extend', left=border.x, top=border.y,
                              width=self.Xsize() + border.x * 2,
                              height=self.Ysize() + border.y * 2)

        # Now we can safely call _scale() without worrying about black borders.
        stretched = extended._scale(xscale=xscale, yscale=yscale)

        # Crop to the final extents, taking away the extra border we
        # introduced.
        return stretched.extract_area(left=int(border.x * xscale),
                                      top=int(border.y * yscale),
                                      width=int(self.Xsize() * xscale),
                                      height=int(self.Ysize() * yscale))

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

    def _slice(self):
        """Helper function that actually slices tiles. See ``slice``."""
        with self.image.disable_warnings():
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
                    self.storage.save(x=offset.x, y=offset.y, z=self.resolution,
                                      image=out)

    def slice(self):
        """
        Slices a VIPS image object into TMS tiles in PNG format.

        If a tile duplicates another tile already known to this process, a
        symlink is created instead of rendering the same tile to PNG again.
        """
        with self.image.disable_warnings():
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

    def downsample(self):
        """
        Downsamples the image by one resolution.

        Returns a new TmsTiles object containing the downsampled image.
        """
        assert self.resolution > 0

        offset = XY(self.offset.x / 2.0,
                    self.offset.y / 2.0)

        shrunk = self.image.shrink(xscale=0.5, yscale=0.5)
        aligned = shrunk.tms_align(tile_width=self.tile_width,
                                   tile_height=self.tile_height,
                                   offset=offset)

        tiles = self.__class__(image=aligned,
                               storage=self.storage,
                               tile_width=self.tile_width,
                               tile_height=self.tile_height,
                               offset=XY(int(offset.x), int(offset.y)),
                               resolution=self.resolution - 1)
        return tiles

    def upsample(self, levels):
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

        Filenames are in the format ``{tms_z}/{tms_x}-{tms_y}-{image_hash}.png``.

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
        with VImage.disable_warnings():
            # Downsampling one zoom level at a time, using the previous
            # downsampled results.
            for res in reversed(range(min_resolution, self.resolution)):
                tiles = tiles.downsample()
                tiles._slice()

    def slice_native(self):
        """Slices the input image at native resolution."""
        with VImage.disable_warnings():
            offset = self.dataset.GetTmsExtents()
            tiles = self.TmsTiles(image=self.image,
                                  storage=self.storage,
                                  tile_width=TILE_SIDE, tile_height=TILE_SIDE,
                                  offset=offset.lower_left,
                                  resolution=self.resolution)
            tiles._slice()
            return tiles

    def slice_upsample(self, tiles, max_resolution):
        """Upsamples the input TmsTiles up to max_resolution and slices."""
        with VImage.disable_warnings():
            # Upsampling one zoom level at a time, from the native image.
            for res in range(self.resolution + 1, max_resolution + 1):
                upsampled = tiles.upsample(levels=(res - self.resolution))
                upsampled._slice()

    def slice(self):
        """Slices the input image into the pyramid of PNG tiles."""
        tiles = self.slice_native()
        if self.min_resolution is not None:
            self.slice_downsample(tiles=tiles,
                                  min_resolution=self.min_resolution)
        if self.max_resolution is not None:
            self.slice_upsample(tiles=tiles,
                                max_resolution=self.max_resolution)
        self.storage.waitall()


def image_pyramid(inputfile, outputdir,
                  min_resolution=None, max_resolution=None,
                  renderer=None, hasher=None):
    """
    Slices a GDAL-readable inputfile into a pyramid of PNG tiles.

    inputfile: Filename
    outputdir: The output directory for the PNG tiles.
    min_resolution: Minimum resolution to downsample tiles.
    max_resolution: Maximum resolution to upsample tiles.
    hasher: Hashing function to use for image data.

    Filenames are in the format ``{tms_z}-{tms_x}-{tms_y}-{image_hash}.png``.

    If a tile duplicates another tile already known to this process, a symlink
    may be created instead of rendering the same tile to PNG again.

    If `min_resolution` is None, don't downsample.
    If `max_resolution` is None, don't upsample.
    """
    if renderer is None:
        renderer = PngRenderer
    storage = SimpleFileStorage(outputdir=outputdir,
                                renderer=renderer,
                                hasher=hasher)
    pyramid = TmsPyramid(inputfile=inputfile,
                         storage=storage,
                         min_resolution=min_resolution,
                         max_resolution=max_resolution)
    pyramid.slice()


def image_slice(inputfile, outputdir, hasher=None, renderer=None):
    """
    Slices a GDAL-readable inputfile into PNG tiles.

    inputfile: Filename
    outputdir: The output directory for the PNG tiles.
    hasher: Hashing function to use for image data.

    Filenames are in the format ``{tms_z}-{tms_x}-{tms_y}-{image_hash}.png``.

    If a tile duplicates another tile already known to this process, a symlink
    is created instead of rendering the same tile to PNG again.
    """
    if renderer is None:
        renderer = PngRenderer
    storage = SimpleFileStorage(outputdir=outputdir,
                                renderer=renderer,
                                hasher=hasher)
    pyramid = TmsPyramid(inputfile=inputfile,
                         storage=storage,
                         min_resolution=None,
                         max_resolution=None)
    pyramid.slice()
