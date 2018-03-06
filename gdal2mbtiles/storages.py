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

import sys

from collections import defaultdict
from functools import partial
import os

from .constants import TILE_SIDE
from .gdal import SpatialReference
from .mbtiles import MBTiles
from .gd_types import rgba
from .utils import intmd5, makedirs
from .vips import VImageAdapter


try:
  basestring
except NameError:
  basestring = str


class Storage(object):
    """Base class for storages."""

    def __init__(self, renderer, pool=None):
        """
        Initialize a storage.

        renderer: Used to render images into tiles.
        """
        self.renderer = renderer

        self.hasher = intmd5

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        return

    def get_hash(self, image):
        """Returns the image content hash."""
        return self.hasher(image.write_to_memory())

    def filepath(self, x, y, z, hashed):
        """Returns the filepath."""
        raise NotImplementedError()

    def post_import(self, pyramid):
        """Runs after `pyramid` has finished importing into this storage."""
        pass

    def save(self, x, y, z, image):
        """Saves `image` at coordinates `x`, `y`, and `z`."""
        raise NotImplementedError()

    def save_border(self, x, y, z):
        """Saves a border image at coordinates `x`, `y`, and `z`."""
        self.save(x=x, y=y, z=z, image=self._border_image())

    @classmethod
    def _border_image(cls, width=TILE_SIDE, height=TILE_SIDE):
        """Returns a border image suitable for borders."""
        image = VImageAdapter.new_rgba(
            width, height, ink=rgba(r=0, g=0, b=0, a=0)
        )
        image._buf = image
        return image


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
        """
        super(SimpleFileStorage, self).__init__(renderer=renderer,
                                                **kwargs)
        if seen is None:
            seen = {}
        self.seen = seen
        self._border_hashed = None

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
            contents = self.renderer.render(image)
            outputfile = os.path.join(self.outputdir, filepath)
            with open(outputfile, 'wb') as output:
                output.write(contents)

    def symlink(self, src, dst):
        """Creates a relative symlink from dst to src."""
        absdst = os.path.join(self.outputdir, dst)
        abssrc = os.path.join(self.outputdir, src)
        srcpath = os.path.relpath(abssrc,
                                  start=os.path.dirname(absdst))
        os.symlink(srcpath, absdst)

    def save_border(self, x, y, z):
        """Saves a border image at coordinates `x`, `y`, and `z`."""
        if self._border_hashed is None or self._border_hashed not in self.seen:
            image = self._border_image()
            self._border_hashed = self.get_hash(image)
            self.save(x=x, y=y, z=z, image=image)
        else:
            # self._border_hashed will already be in self.seen
            filepath = self.filepath(x=x, y=y, z=z, hashed=self._border_hashed)
            self.symlink(src=self.seen[self._border_hashed], dst=filepath)


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
        """
        super(NestedFileStorage, self).__init__(renderer=renderer,
                                                **kwargs)
        self.madedirs = defaultdict(partial(defaultdict, bool))

    def filepath(self, x, y, z, hashed):
        """Returns the filepath, relative to self.outputdir."""
        return (os.path.join(str(z), str(x), str(y)) +
                self.renderer.suffix)

    def makedirs(self, x, y, z):
        if not self.madedirs[z][x]:
            makedirs(os.path.join(self.outputdir, str(z), str(x)),
                     ignore_exists=True)
            self.madedirs[z][x] = True

    def save(self, x, y, z, image):
        """Saves `image` at coordinates `x`, `y`, and `z`."""
        self.makedirs(x=x, y=y, z=z)
        return super(NestedFileStorage, self).save(x=x, y=y, z=z, image=image)

    def save_border(self, x, y, z):
        """Saves a border image at coordinates `x`, `y`, and `z`."""
        self.makedirs(x=x, y=y, z=z)
        return super(NestedFileStorage, self).save_border(x=x, y=y, z=z)


class MbtilesStorage(Storage):
    """
    Saves tiles in `filename` in the MBTiles format.

    http://mapbox.com/developers/mbtiles/
    """
    def __init__(self, renderer, filename, zoom_offset=None, seen=None,
                 **kwargs):
        """
        Initializes storage.

        renderer: Used to render images into tiles.
        filename: Name of the MBTiles file.
        pool: Process pool to coordinate subprocesses.
        """
        super(MbtilesStorage, self).__init__(renderer=renderer,
                                             **kwargs)
        if zoom_offset is None:
            zoom_offset = 0
        self.zoom_offset = zoom_offset

        if seen is None:
            seen = set()
        self.seen = seen
        self._border_hashed = None

        self.mbtiles = None

        if isinstance(filename, basestring):
            self.filename = filename
            self.mbtiles = MBTiles(filename=filename)
        else:
            self.mbtiles = filename
            self.filename = self.mbtiles.filename

    def __del__(self):
        if self.mbtiles is not None:
            self.mbtiles.close()

    def __exit__(self, type, value, traceback):
        if self.mbtiles is not None:
            self.mbtiles.close()

    @classmethod
    def create(cls, renderer, filename, metadata, zoom_offset=None,
               version=None, **kwargs):
        """
        Creates a new MBTiles file.

        renderer: Used to render images into tiles.
        filename: Name of the MBTiles file.
        metadata: Metadata dictionary.
        zoom_offset: Offset zoom level.

        version: Optional MBTiles version.
        pool: Process pool to coordinate subprocesses.

        Metadata is also taken as **kwargs. See `mbtiles.Metadata`.
        """
        bounds = metadata.get('bounds', None)
        if bounds is not None:
            metadata['bounds'] = bounds.lower_left + bounds.upper_right
        mbtiles = MBTiles.create(filename=filename, metadata=metadata,
                                 version=version)
        return cls(renderer=renderer,
                   filename=mbtiles,
                   zoom_offset=zoom_offset,
                   **kwargs)

    def post_import(self, pyramid):
        """Insert the dataset extents into the metadata."""
        # The MBTiles spec says that the bounds must be in EPSG:4326
        transform = pyramid.dataset.GetCoordinateTransformation(
            dst_ref=SpatialReference.FromEPSG(4326)
        )

        lower_left, upper_right = pyramid.dataset.GetTiledExtents(
            transform=transform
        )
        self.mbtiles.metadata['bounds'] = (lower_left.x, lower_left.y,
                                           upper_right.x, upper_right.y)

    def save(self, x, y, z, image):
        """Saves `image` at coordinates `x`, `y`, and `z`."""
        hashed = self.get_hash(image)
        if hashed in self.seen:
            self.mbtiles.insert(x=x, y=y,
                                z=z + self.zoom_offset,
                                hashed=hashed)
        else:
            self.seen.add(hashed)
            contents = self.renderer.render(image)
            if sys.version_info < (3, 0):
                data = buffer(contents)
            else:
                data = memoryview(contents)
            self.mbtiles.insert(x=x, y=y,
                                z=z + self.zoom_offset,
                                hashed=hashed,
                                data=data)

    def save_border(self, x, y, z):
        """Saves a border image at coordinates `x`, `y`, and `z`."""
        if self._border_hashed is None:
            image = self._border_image()
            self.save(x=x, y=y, z=z, image=image)
            self._border_hashed = self.get_hash(image)
        else:
            # self._border_hashed will already be inserted
            self.mbtiles.insert(x=x, y=y,
                                z=z + self.zoom_offset,
                                hashed=self._border_hashed)
