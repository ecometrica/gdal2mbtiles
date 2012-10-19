# -*- coding: utf-8 -*-

from __future__ import absolute_import

from collections import defaultdict
from functools import partial
import os
from tempfile import gettempdir, NamedTemporaryFile

from .mbtiles import MBTiles
from .pool import Pool
from .utils import get_hasher, makedirs, rmfile


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
        return ('{z}-{x}-{y}-{hashed:x}'.format(**locals()) +
                self.renderer.suffix)

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


class NestedFileStorage(SimpleFileStorage):
    """
    Saves tiles in `outputdir` as 'z/x/y.ext' for serving via static site.
    """

    def __init__(self, renderer, **kwargs):
        """
        Initializes storage.

        renderer: Used to render images into tiles.
        outputdir: Output directory for tiles
        pool: Process pool to coordinate subprocesses.
        hasher: Hashing function to use for image data.
        """
        super(NestedFileStorage, self).__init__(renderer=renderer,
                                                **kwargs)
        self.madedirs = defaultdict(partial(defaultdict, bool))

    def filepath(self, x, y, z, hashed):
        """Returns the filepath, relative to self.outputdir."""
        return (os.path.join(unicode(z), unicode(x), unicode(y)) +
                self.renderer.suffix)

    def makedirs(self, x, y, z):
        if not self.madedirs[z][x]:
            makedirs(os.path.join(self.outputdir, unicode(z), unicode(x)),
                     ignore_exists=True)
            self.madedirs[z][x] = True

    def save(self, x, y, z, image):
        """Saves `image` at coordinates `x`, `y`, and `z`."""
        self.makedirs(x=x, y=y, z=z)
        return super(NestedFileStorage, self).save(x=x, y=y, z=z, image=image)


class MbtilesStorage(Storage):
    """
    Saves tiles in `filename` in the MBTiles format.

    http://mapbox.com/developers/mbtiles/
    """
    def __init__(self, renderer, filename, seen=None, tempdir=None, **kwargs):
        """
        Initializes storage.

        renderer: Used to render images into tiles.
        filename: Name of the MBTiles file.
        pool: Process pool to coordinate subprocesses.
        hasher: Hashing function to use for image data.
        """
        super(MbtilesStorage, self).__init__(renderer=renderer,
                                             **kwargs)
        if seen is None:
            seen = set()
        self.seen = seen

        if tempdir is None:
            tempdir = gettempdir()
        self.tempdir = tempdir

        if isinstance(filename, basestring):
            self.filename = filename
            self.mbtiles = MBTiles(filename=filename)
        else:
            self.mbtiles = filename
            self.filename = self.mbtiles.filename

    @classmethod
    def create(cls, renderer, filename, metadata, version=None, tempdir=None,
               **kwargs):
        """
        Creates a new MBTiles file.

        renderer: Used to render images into tiles.
        filename: Name of the MBTiles file.
        metadata: Metadata dictionary.
        version: Optional MBTiles version.
        pool: Process pool to coordinate subprocesses.
        hasher: Hashing function to use for image data.

        Metadata is also taken as **kwargs. See `mbtiles.Metadata`.
        """

        bounds = metadata.get('bounds', None)
        if bounds is not None and not isinstance(bounds, basestring):
            metadata['bounds'] = (
                '{ll.x!r},{ll.y!r},{ur.x!r},{ur.y!r}'.format(
                    ll=bounds.lower_left,
                    ur=bounds.upper_right
                )
            )
        mbtiles = MBTiles.create(filename=filename, metadata=metadata,
                                 version=version)
        return cls(renderer=renderer,
                   filename=mbtiles,
                   tempdir=tempdir,
                   **kwargs)

    def save(self, x, y, z, image):
        """Saves `image` at coordinates `x`, `y`, and `z`."""
        hashed = self.get_hash(image)
        if hashed in self.seen:
            self.mbtiles.insert(x=x, y=y, z=z, hashed=hashed)
        else:
            self.seen.add(hashed)
            tempfile = NamedTemporaryFile(dir=self.tempdir,
                                          suffix=self.renderer.suffix)
            self.pool.apply_async(
                func=self.renderer.render,
                kwds=dict(image=image,
                          filename=tempfile.name),
                callback=self._make_callback(x=x, y=y, z=z, hashed=hashed,
                                             tempfile=tempfile),
            )

    def _make_callback(self, x, y, z, hashed, tempfile):
        """Returns a callback that saves the rendered image."""
        def callback(filename):
            # Insert the rendered file into the database
            with open(filename) as output:
                self.mbtiles.insert(x=x, y=y, z=z, hashed=hashed,
                                    data=buffer(output.read()))
            # Delete tempfile
            tempfile.close()
            # Delete the rendered file if it wasn't tempfile
            if filename != tempfile.name:
                rmfile(filename, ignore_missing=True)
        return callback
