# -*- coding: utf-8 -*-

from __future__ import absolute_import

from .renderers import PngRenderer
from .storages import SimpleFileStorage
from .vips import TmsPyramid


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
        renderer = PngRenderer()
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
        renderer = PngRenderer()
    storage = SimpleFileStorage(outputdir=outputdir,
                                renderer=renderer,
                                hasher=hasher)
    pyramid = TmsPyramid(inputfile=inputfile,
                         storage=storage,
                         min_resolution=None,
                         max_resolution=None)
    pyramid.slice()
