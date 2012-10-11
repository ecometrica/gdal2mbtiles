# -*- coding: utf-8 -*-

from __future__ import absolute_import

from math import ceil
import os
import platform

import vipsCC.VImage

from .constants import TILE_SIDE
from .gdal import Dataset
from .pool import Pool
from .utils import makedirs, tempenv


def get_hasher():
    """Returns a sensible, fast hashing algorithm"""
    try:
        import smhasher

        machine = platform.machine()
        if machine == 'x86_64':
            return smhasher.murmur3_x64_128
        elif machine == 'i386':
            return smhasher.murmur3_x86_128
    except ImportError:
        pass
    # No hasher was found
    import hashlib
    return (lambda x: int(hashlib.md5(x).hexdigest(), base=16))
hasher = get_hasher()


# Process pool
pool = Pool(processes=None)


class VImage(vipsCC.VImage.VImage):
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

    @classmethod
    def _write_to_png(cls, image, filename):
        """Helper method to write a VIPS image to filename."""
        return image.vips2png(filename)

    def shrink(self, xscale, yscale):
        """
        Returns a new VImage that has been shrunk by `xscale` and `yscale`.

        xscale: floating point scaling value for image
        yscale: floating point scaling value for image
        """
        # Shrink by aligning the corners of the input and output images.

        # See the following blog post, written by the VIPS people:
        # http://libvips.blogspot.ca/2011/12/task-of-day-resize-image-with-align.html

        # This is the image size convention which is ideal for reducing the
        # number of pixels in each direction by an exact fraction (with box
        # filtering, for example). With this convention, there is no
        # extrapolation near the boundary when downsampling.

        assert 0.0 < xscale < 1.0
        assert 0.0 < yscale < 1.0

        # Use the transformation matrix:
        #     [[xscale,      0],
        #      [     0, yscale]]
        a, b, c, d = xscale, 0, 0, yscale

        # The corners of input.img are located at:
        #     (-.5,-.5), (-.5,m-.5), (n-.5,-.5) and (n-.5,m-.5).
        # The corners of output.img are located at:
        #     (-.5,-.5), (-.5,M-.5), (N-.5,-.5) and (N-.5,M-.5).
        # The affine transformation that sends each input corner to the
        # corresponding output corner is:
        #     X = (M / m) * x + (M / m - 1) / 2
        #     Y = (N / n) * y + (N / n - 1) / 2
        # Since M = m * xscale and N = n * yscale
        #     X = xscale * x + (xscale - 1) / 2
        #     Y = yscale * y + (yscale - 1) / 2
        output_width = int(self.Xsize() * a)
        output_height = int(self.Ysize() * d)
        # Align the corners
        offset_x = (a - 1) / 2
        offset_y = (d - 1) / 2

        # No translation, so top-left corners match.
        output_x, output_y = 0, 0

        return self.from_vimage(
            self.affine(a, b, c, d, offset_x, offset_y,
                        output_x, output_y, output_width, output_height)
        )

    def tms_align(self, tile_width, tile_height, offset_x, offset_y):
        """
        Pads and aligns the VIPS Image object to the TMS grid.

        tile_width: Number of pixels for each tile
        tile_height: Number of pixels for each tile
        offset_x: TMS offset for the lower-left tile
        offset_y: TMS offset for the lower-left tile
        """
        _type = 0               # Transparent

        # Pixel offset from top-left of the aligned image.
        #
        # The y value needs to be converted from the lower-left corner to the
        # top-left corner.
        x = int(round(offset_x * tile_width)) % tile_width
        y = int(round(self.Ysize() - offset_y * tile_height)) % tile_height

        # Number of tiles for the aligned image, rounded up to provide
        # right and bottom borders.
        tiles_x = ceil(float(self.Xsize() + x / 2) / tile_width)
        tiles_y = ceil(float(self.Ysize() + y / 2) / tile_height)

        # Pixel width and height for the aligned image.
        width = int(tiles_x * tile_width)
        height = int(tiles_y * tile_height)

        if width == self.Xsize() and height == self.Ysize():
            # No change
            assert x == y == 0
            return self

        # Resize
        return self.from_vimage(self.embed(_type, x, y, width, height))

    def _tms_slice(self, outputdir,
                   tile_width, tile_height, offset_x=0, offset_y=0,
                   resolution=None):
        """Helper function that actually slices tiles. See ``tms_slice``."""
        with self.disable_warnings():
            image_width = self.Xsize()
            image_height = self.Ysize()

            seen = {}
            for y in xrange(0, image_height, tile_height):
                for x in xrange(0, image_width, tile_width):
                    out = self.extract_area(
                        x, y,                    # left, top offsets
                        tile_width, tile_height
                    )

                    hashed = hasher(out.tostring())
                    filename = '{x}-{y}-{hashed:x}.png'.format(
                        x=(x / tile_width + offset_x),
                        y=((image_height - y) / tile_height + offset_y - 1),
                        hashed=hashed
                    )
                    if resolution is None:
                        filepath = os.path.join(outputdir, filename)
                    else:
                        filepath = os.path.join(outputdir,
                                                str(resolution), filename)

                    if hashed in seen:
                        # Symlink so we don't have to generate PNGs for tiles
                        # this process has already seen.
                        os.symlink(seen[hashed], filepath)
                    else:
                        seen[hashed] = filename
                        pool.apply_async(
                            func=self._write_to_png,
                            kwds=dict(image=out, filename=filepath)
                        )
            pool.join()

    def tms_slice(self, outputdir,
                  tile_width, tile_height, offset_x=0, offset_y=0,
                  resolution=None):
        """
        Slices a VIPS image object into TMS tiles in PNG format.

        outputdir: The output directory for the tiles.
        tile_width: Number of pixels for each tile
        tile_height: Number of pixels for each tile
        offset_x: TMS offset for the lower-left tile
        offset_y: TMS offset for the lower-left tile

        resolution: If None, filenames are in the format
                        ``{tms_x}-{tms_y}-{image_hash}.png``.
                    If an integer, filenames are in the format
                        ``{tms_z}/{tms_x}-{tms_y}-{image_hash}.png``.

        If a tile duplicates another tile already known to this process, a
        symlink is created instead of rendering the same tile to PNG again.
        """
        # Make directory for this resolution
        makedirs(outputdir, ignore_exists=True)
        if resolution is not None:
            makedirs(os.path.join(outputdir, str(resolution)),
                     ignore_exists=True)

        with self.disable_warnings():
            image_width = self.Xsize()
            image_height = self.Ysize()

            if image_width % tile_width != 0:
                raise ValueError('image width {0!r} does not contain a whole '
                                 'number of tiles of width {1!r}'.format(
                                     image_width, tile_width
                                 ))

            if image_height % tile_height != 0:
                raise ValueError('image height {0!r} does not contain a whole '
                                 'number of tiles of height {1!r}'.format(
                                     image_height, tile_height
                                 ))

            return self._tms_slice(
                outputdir=outputdir,
                resolution=resolution,
                tile_width=tile_width, tile_height=tile_height,
                offset_x=offset_x, offset_y=offset_y
            )

    def downsample(self, resolution, outputdir, tile_width, tile_height,
                   offset_x=0, offset_y=0):
        """
        Downsamples the VIPS image by one resolution.

        resolution: Target resolution for the downsampled image.
        outputdir: The output directory for the tiles.
        tile_width: Number of pixels for each tile
        tile_height: Number of pixels for each tile
        offset_x: TMS offset for the lower-left tile
        offset_y: TMS offset for the lower-left tile

        Returns (image, offset_x, offset_y) for the new downsampled image.
        """
        assert resolution > 0

        offset_x /= 2.0
        offset_y /= 2.0

        shrunk = self.shrink(xscale=0.5, yscale=0.5)
        aligned = shrunk.tms_align(tile_width=tile_width,
                                   tile_height=tile_height,
                                   offset_x=offset_x, offset_y=offset_y)

        offset_x, offset_y = int(offset_x), int(offset_y)
        aligned.tms_slice(outputdir=outputdir,
                          resolution=(resolution - 1),
                          tile_width=tile_width, tile_height=tile_height,
                          offset_x=offset_x, offset_y=offset_y)
        return aligned, offset_x, offset_y


def image_pyramid(inputfile, outputdir):
    """
    Slices a GDAL-readable inputfile into a pyramid of PNG tiles.

    inputfile: Filename
    outputdir: The output directory for the PNG tiles.

    Filenames are in the format ``{tms_z}/{tms_x}-{tms_y}-{image_hash}.png``.

    If a tile duplicates another tile already known to this process, a symlink
    may be created instead of rendering the same tile to PNG again.
    """
    dataset = Dataset(inputfile)
    lower_left, upper_right = dataset.GetTmsExtents()
    resolution = dataset.GetNativeResolution()

    with VImage.disable_warnings():
        # Native resolution
        image = VImage(inputfile)
        image.tms_slice(outputdir=outputdir,
                        resolution=resolution,
                        tile_width=TILE_SIDE, tile_height=TILE_SIDE,
                        offset_x=lower_left.x, offset_y=lower_left.y)

        # Downsampling one zoom level at a time
        offset_x, offset_y = lower_left.x, lower_left.y
        for res in range(resolution, 0, -1):
            image, offset_x, offset_y = image.downsample(
                resolution=res, outputdir=outputdir,
                tile_width=TILE_SIDE, tile_height=TILE_SIDE,
                offset_x=offset_x, offset_y=offset_y,
            )


def image_slice(inputfile, outputdir):
    """
    Slices a GDAL-readable inputfile into PNG tiles.

    inputfile: Filename
    outputdir: The output directory for the PNG tiles.

    Filenames are in the format ``{tms_x}-{tms_y}-{image_hash}.png``.

    If a tile duplicates another tile already known to this process, a symlink
    is created instead of rendering the same tile to PNG again.
    """
    dataset = Dataset(inputfile)
    lower_left, upper_right = dataset.GetTmsExtents()

    with VImage.disable_warnings():
        # Native resolution
        image = VImage(inputfile)
        image.tms_slice(outputdir=outputdir,
                        tile_width=TILE_SIDE, tile_height=TILE_SIDE,
                        offset_x=lower_left.x, offset_y=lower_left.y)
