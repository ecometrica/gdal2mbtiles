from __future__ import absolute_import

import errno
import os
import platform

import vipsCC.VImage

from .constants import TILE_SIDE
from .gdal import Dataset
from .pool import Pool
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


# Process pool
pool = Pool(processes=None)


class VImage(vipsCC.VImage.VImage):
    def __init__(self, *args, **kwargs):
        super(VImage, self).__init__(*args, **kwargs)

    @classmethod
    def disable_warnings(cls):
        """Context manager to disable VIPS warnings."""
        return tempenv('IM_WARNING', '0')

    @classmethod
    def _write_to_png(cls, image, filename):
        """Helper method to write a VIPS image to filename."""
        return image.vips2png(filename)

    def _tms_slice(self, outputdir, resolution,
                   tile_width, tile_height, offset_x=0, offset_y=0):
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

    def tms_slice(self, outputdir, resolution,
                  tile_width, tile_height, offset_x=0, offset_y=0):
        """
        Slices a VIPS image object into TMS tiles in PNG format.

        outputdir: The output directory for the tiles.
        tile_width: Number of pixels for each tile
        tile_height: Number of pixels for each tile
        offset_x: TMS offset for the lower-left tile
        offset_y: TMS offset for the lower-left tile

        Filenames are in the format ``{tms_x}-{tms_y}-{image_hash}.png``.

        If a tile duplicates another tile already known to this process, a
        symlink is created instead of rendering the same tile to PNG again.
        """
        # Make directory for this resolution
        try:
            os.makedirs(os.path.join(outputdir, str(resolution)))
        except OSError as e:
            if e.errno != errno.EEXIST:  # OK if the outputdir exists
                raise

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


def image_slice(inputfile, outputdir):
    """
    Slices a GDAL-readable inputfile into PNG tiles.

    inputfile: Filename
    outputdir: The output directory for the PNG tiles.

    Filenames are in the format ``{tms_z}/{tms_x}-{tms_y}-{image_hash}.png``.

    If a tile duplicates another tile already known to this process, a symlink
    is created instead of rendering the same tile to PNG again.
    """
    dataset = Dataset(inputfile)
    lower_left, upper_right = dataset.GetTmsExtents()
    resolution = dataset.GetNativeResolution()

    with VImage.disable_warnings():
        image = VImage(inputfile)
        return image.tms_slice(outputdir=outputdir,
                               resolution=resolution,
                               tile_width=TILE_SIDE, tile_height=TILE_SIDE,
                               offset_x=lower_left.x, offset_y=lower_left.y)
