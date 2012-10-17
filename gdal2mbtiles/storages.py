# -*- coding: utf-8 -*-

from __future__ import absolute_import

import os

from .pool import Pool
from .utils import get_hasher, makedirs


class Storage(object):
    """Base class for storages."""

    def __init__(self, renderer, pool=None, hasher=None):
        """
        Initialize a storage.

        renderer: Used to render images into tiles.
        pool: Process pool to coordinate subprocesses.
        hasher: Hashing function to use for image data.
        """
        self.renderer = renderer

        if pool is None:
            # Create a pool with a maximum processes being equal to CPUs
            pool = Pool(processes=None)
        self.pool = pool

        if hasher is None:
            hasher = get_hasher()
        self.hasher = hasher

    def get_hash(self, image):
        """Returns the image content hash."""
        return self.hasher(image.tobuffer())

    def filepath(self, x, y, z, hashed):
        """Returns the filepath."""
        raise NotImplementedError()

    def save(self, x, y, z, image):
        """Saves `image` at coordinates `x`, `y`, and `z`."""
        raise NotImplementedError()

    def waitall(self):
        """Waits until all saves are finished."""
        self.pool.join()


class SimpleFileStorage(Storage):
    """
    Saves tiles in `outputdir` as 'z-x-y-hash.ext'.
    """

    def __init__(self, renderer, outputdir, seen=None, **kwargs):
        """
        Initializes storage.

        renderer: Used to render images into tiles.
        outputdir: Output directory for tiles
        pool: Process pool to coordinate subprocesses.
        hasher: Hashing function to use for image data.
        """
        super(SimpleFileStorage, self).__init__(renderer=renderer,
                                                **kwargs)
        if seen is None:
            seen = {}
            self.seen = seen

        self.outputdir = outputdir
        makedirs(self.outputdir, ignore_exists=True)

    def filepath(self, x, y, z, hashed):
        """Returns the filepath, relative to self.outputdir."""
        return '{z}-{x}-{y}-{hashed:x}'.format(**locals()) + self.renderer.ext

    def save(self, x, y, z, image):
        """Saves `image` at coordinates `x`, `y`, and `z`."""
        hashed = self.get_hash(image)
        filepath = self.filepath(x=x, y=y, z=z, hashed=hashed)
        if hashed in self.seen:
            self.symlink(src=self.seen[hashed], dst=filepath)
        else:
            self.seen[hashed] = filepath
            self.pool.apply_async(
                func=self.renderer.render,
                kwds=dict(image=image,
                          filename=os.path.join(self.outputdir, filepath))
            )

    def symlink(self, src, dst):
        """Creates a relative symlink from dst to src."""
        absdst = os.path.join(self.outputdir, dst)
        abssrc = os.path.join(self.outputdir, src)
        srcpath = os.path.relpath(abssrc,
                                  start=os.path.dirname(absdst))
        os.symlink(srcpath, absdst)
