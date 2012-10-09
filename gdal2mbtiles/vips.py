from __future__ import absolute_import

import errno
from functools import wraps
from multiprocessing import cpu_count, Process, Queue
import os
import platform
from Queue import Empty as QueueEmpty

import vipsCC.VImage

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


class VImage(vipsCC.VImage.VImage):
    # Maximum number of processes in _process_pool
    _process_max = cpu_count() * 2

    # Number of active processes
    _process_pool = set()

    # Queue for processes to return results. See process_wrapper.
    _process_results = Queue()

    def __init__(self, *args, **kwargs):
        super(VImage, self).__init__(*args, **kwargs)

    @classmethod
    def disable_warnings(cls):
        """Context manager to disable VIPS warnings."""
        return tempenv('IM_WARNING', '0')

    # Decorator. Cannot be @staticmethod, as you would assume.
    def process_wrapper(q):
        """
        Decorator to wrap functions, that are split into Processes, so that
        they will return results or Exceptions in a Queue.
        """
        def wrap(target):
            @wraps(target)
            def wrapped(*args, **kwargs):
                extras = kwargs.pop('_extras', None)
                try:
                    q.put(target(*args, **kwargs))
                except Exception as e:
                    if extras is not None:
                        e.extras = extras
                    q.put(e)
            return wrapped
        return wrap

    @classmethod
    def _start_process(cls, target, args=(), kwargs={}):
        """
        Start target as a Process and put it in the Process pool.

        Limit the number of active processes to ``VImage._process_max``.
        """
        while len(cls._process_pool) >= cls._process_max:
            cls._wait_process()
        p = Process(target=target, args=args, kwargs=kwargs)
        cls._process_pool.add(p)
        p.start()
        return p

    @classmethod
    def _wait_process(cls):
        """
        Wait for a process to finish and return (process, result).
        """
        # Wait for a process to put a result on the queue, which means it is
        # about to die.
        result = cls._get_process_result(block=True)
        while cls._process_pool:
            # Spin until we find the dead process.
            for p in cls._process_pool:
                if not p.is_alive():
                    p.join()
                    cls._process_pool.remove(p)
                    return (p, result)

    @classmethod
    def _wait_all_processes(cls):
        """
        Wait for all processes to finish.

        Returns a list of (process, result).
        """
        results = []
        for p in cls._process_pool:
            p.join()
            results.append((p, cls._get_process_result(block=True)))
        cls._process_pool.clear()

    @classmethod
    def _get_process_result(cls, block):
        """
        Returns the result of a process.

        Blocks for a result if block is True.

        Returns None if there are no results pending and block is False.
        """
        try:
            result = cls._process_results.get(block=block)
        except QueueEmpty:
            return
        if isinstance(result, Exception):
            raise result
        return result

    @classmethod
    @process_wrapper(q=_process_results)
    def _write_to_png(cls, image, filename):
        """Helper method to write a VIPS image to filename."""
        return image.vips2png(filename)

    def _tms_slice(self, outputdir, tile_width, tile_height,
                    offset_x=0, offset_y=0):
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

                    if hashed in seen:
                        # Symlink so we don't have to generate PNGs for tiles
                        # this process has already seen.
                        os.symlink(seen[hashed],
                                   os.path.join(outputdir, filename))
                    else:
                        seen[hashed] = filename
                        self._start_process(
                            target=self._write_to_png,
                            kwargs=dict(
                                image=out,
                                filename=os.path.join(outputdir, filename),
                                _extras=dict(
                                    x=x, y=y,
                                    outputdir=outputdir,
                                    filename=filename,
                                    inputfile=self.filename(),
                                ),
                            )
                        )
            self._wait_all_processes()

    def tms_slice(self, outputdir, tile_width, tile_height,
                   offset_x=0, offset_y=0):
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

            try:
                os.makedirs(outputdir)
            except OSError as e:
                if e.errno != errno.EEXIST:  # OK if the outputdir exists
                    raise

            return self._tms_slice(
                outputdir=outputdir,
                tile_width=tile_width, tile_height=tile_height,
                offset_x=offset_x, offset_y=offset_y
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
        image = VImage(inputfile)
        return image.tms_slice(outputdir=outputdir,
                               tile_width=TILE_SIDE, tile_height=TILE_SIDE,
                               offset_x=lower_left.x, offset_y=lower_left.y)
