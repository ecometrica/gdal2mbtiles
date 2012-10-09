from __future__ import absolute_import

import errno
import os
import platform

from vipsCC.VImage import VImage

from .constants import TILE_SIDE
from .gdal import Dataset
from .utils import tempenv


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


def _tile_slice(image, outputdir, tile_width, tile_height,
                offset_x=0, offset_y=0):
    """Helper function that actually slices tiles. See ``tile_slice``."""
    with tempenv('IM_WARNING', '0'):  # Turn off VIPS warnings
        image_width = image.Xsize()
        image_height = image.Ysize()

        seen = {}
        for y in xrange(0, image_height, tile_height):
            for x in xrange(0, image_width, tile_width):
                out = image.extract_area(
                    x, y,                    # left, top offsets
                    tile_width, tile_height
                )

                hashed = hasher(out.tostring())
                filename = '{x}-{y}-{hashed:x}.png'.format(
                    x=(x / tile_width + offset_x),
                    y=((image_height - y) / tile_height + offset_y - 1),
                    hashed=hashed
                )

                if hashed in seen:
                    # Symlink so we don't have to generate PNGs for tiles this
                    # process has already seen.
                    os.symlink(seen[hashed], os.path.join(outputdir, filename))
                else:
                    seen[hashed] = filename
                    out.vips2png(os.path.join(outputdir, filename))


def tile_slice(image, outputdir, tile_width, tile_height,
               offset_x=0, offset_y=0):
    """
    Slices a VIPS image object into PNG tiles.

    outputdir: The output directory for the PNG tiles.
    tile_width: Number of pixels for each tile
    tile_height: Number of pixels for each tile
    offset_x: TMS offset for the lower-left tile
    offset_y: TMS offset for the lower-left tile

    Filenames are in the format ``{tms_x}-{tms_y}-{image_hash}.png``.

    If a tile duplicates another tile already known to this process, a symlink
    is created instead of rendering the same tile to PNG again.
    """
    with tempenv('IM_WARNING', '0'):  # Turn off VIPS warnings
        image_width = image.Xsize()
        image_height = image.Ysize()

        if image_width % tile_width != 0:
            raise ValueError('image width {0!r} does not contain a whole number '
                             'of tiles of width {1!r}'.format(image_width,
                                                              tile_width))

        if image_height % tile_height != 0:
            raise ValueError('image height {0!r} does not contain a whole number '
                             'of tiles of height {1!r}'.format(image_height,
                                                               tile_height))

        try:
            os.makedirs(outputdir)
        except OSError as e:
            if e.errno != errno.EEXIST:  # OK if the outputdir already exists
                raise

        return _tile_slice(image=image, outputdir=outputdir,
                           tile_width=tile_width, tile_height=tile_height,
                           offset_x=offset_x, offset_y=offset_y)


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

    with tempenv('IM_WARNING', '0'):  # Turn off VIPS warnings
        image = VImage(inputfile)

        return tile_slice(image=image, outputdir=outputdir,
                          tile_width=TILE_SIDE, tile_height=TILE_SIDE,
                          offset_x=lower_left.x, offset_y=lower_left.y)
