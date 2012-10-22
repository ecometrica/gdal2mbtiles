# -*- coding: utf-8 -*-

from __future__ import absolute_import

from tempfile import NamedTemporaryFile

from .gdal import preprocess
from .renderers import PngRenderer
from .storages import MbtilesStorage, NestedFileStorage, SimpleFileStorage
from .vips import TmsPyramid


def image_mbtiles(inputfile, outputfile, metadata,
                  min_resolution=None, max_resolution=None,
                  renderer=None, hasher=None):
    """
    Slices a GDAL-readable inputfile into a pyramid of PNG tiles.

    inputfile: Filename
    outputfile: The output .mbtiles file.
    min_resolution: Minimum resolution to downsample tiles.
    max_resolution: Maximum resolution to upsample tiles.
    hasher: Hashing function to use for image data.

    If `min_resolution` is None, don't downsample.
    If `max_resolution` is None, don't upsample.
    """
    if renderer is None:
        renderer = PngRenderer()
    with MbtilesStorage.create(filename=outputfile,
                               metadata=metadata,
                               renderer=renderer,
                               hasher=hasher) as storage:
        pyramid = TmsPyramid(inputfile=inputfile,
                             storage=storage,
                             min_resolution=min_resolution,
                             max_resolution=max_resolution)
        pyramid.slice()


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

    Filenames are in the format ``{tms_z}/{tms_x}/{tms_y}.png``.

    If a tile duplicates another tile already known to this process, a symlink
    may be created instead of rendering the same tile to PNG again.

    If `min_resolution` is None, don't downsample.
    If `max_resolution` is None, don't upsample.
    """
    if renderer is None:
        renderer = PngRenderer()
    storage = NestedFileStorage(outputdir=outputdir,
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


def warp_mbtiles(inputfile, outputfile, metadata, colours=None, band=None,
                 spatial_ref=None, resampling=None, compress='LZW',
                 min_resolution=None, max_resolution=None, renderer=None,
                 hasher=None):
    """
    Warps a GDAL-readable inputfile into a pyramid of PNG tiles.

    inputfile: Filename
    outputfile: The output .mbtiles file.

    colours: Colour palette applied to single band files.
             colours={0: rgba(0, 0, 0, 255),
                      10: rgba(255, 255, 255, 255)}
             Defaults to no colourization.
    band: Select band to colourize and expand to RGBA. Defaults to 1.
    spatial_ref: Destination gdal.SpatialReference. Defaults to EPSG:3857,
                 Web Mercator
    resampling: Resampling algorithm. Defaults to GDAL's default,
                nearest neighbour as of GDAL 1.9.1.
    compress: Compression algorithm. Defaults to LZW.

    min_resolution: Minimum resolution to downsample tiles.
    max_resolution: Maximum resolution to upsample tiles.
    hasher: Hashing function to use for image data.

    If `min_resolution` is None, don't downsample.
    If `max_resolution` is None, don't upsample.
    """
    with NamedTemporaryFile(suffix='.tif') as tempfile:
        preprocess(inputfile=inputfile, outputfile=tempfile.name,
                   colours=colours, band=band, spatial_ref=spatial_ref,
                   resampling=resampling, compress=compress)
        return image_mbtiles(inputfile=tempfile.name, outputfile=outputfile,
                             metadata=metadata,
                             min_resolution=min_resolution,
                             max_resolution=max_resolution, renderer=renderer,
                             hasher=hasher)


def warp_pyramid(inputfile, outputdir, colours=None, band=None,
                 spatial_ref=None, resampling=None, compress='LZW',
                 min_resolution=None, max_resolution=None, renderer=None,
                 hasher=None):
    """
    Warps a GDAL-readable inputfile into a pyramid of PNG tiles.

    inputfile: Filename
    outputdir: The output directory for the PNG tiles.

    colours: Colour palette applied to single band files.
             colours={0: rgba(0, 0, 0, 255),
                      10: rgba(255, 255, 255, 255)}
             Defaults to no colourization.
    band: Select band to colourize and expand to RGBA. Defaults to 1.
    spatial_ref: Destination gdal.SpatialReference. Defaults to EPSG:3857,
                 Web Mercator
    resampling: Resampling algorithm. Defaults to GDAL's default,
                nearest neighbour as of GDAL 1.9.1.
    compress: Compression algorithm. Defaults to LZW.

    min_resolution: Minimum resolution to downsample tiles.
    max_resolution: Maximum resolution to upsample tiles.
    hasher: Hashing function to use for image data.

    Filenames are in the format ``{tms_z}/{tms_x}/{tms_y}.png``.

    If a tile duplicates another tile already known to this process, a symlink
    may be created instead of rendering the same tile to PNG again.

    If `min_resolution` is None, don't downsample.
    If `max_resolution` is None, don't upsample.
    """
    with NamedTemporaryFile(suffix='.tif') as tempfile:
        preprocess(inputfile=inputfile, outputfile=tempfile.name,
                   colours=colours, band=band, spatial_ref=spatial_ref,
                   resampling=resampling, compress=compress)
        return image_pyramid(inputfile=tempfile.name, outputdir=outputdir,
                             min_resolution=min_resolution,
                             max_resolution=max_resolution, renderer=renderer,
                             hasher=hasher)


def warp_slice(inputfile, outputdir, colours=None, band=None,
               spatial_ref=None, resampling=None, compress='LZW',
               renderer=None, hasher=None):
    """
    Warps a GDAL-readable inputfile into a directory of PNG tiles.

    inputfile: Filename
    outputdir: The output directory for the PNG tiles.

    colours: Colour palette applied to single band files.
             colours={0: rgba(0, 0, 0, 255),
                      10: rgba(255, 255, 255, 255)}
             Defaults to no colourization.
    band: Select band to colourize and expand to RGBA. Defaults to 1.
    spatial_ref: Destination gdal.SpatialReference. Defaults to EPSG:3857,
                 Web Mercator
    resampling: Resampling algorithm. Defaults to GDAL's default,
                nearest neighbour as of GDAL 1.9.1.
    compress: Compression algorithm. Defaults to LZW.

    min_resolution: Minimum resolution to downsample tiles.
    max_resolution: Maximum resolution to upsample tiles.
    hasher: Hashing function to use for image data.

    Filenames are in the format ``{tms_z}-{tms_x}-{tms_y}-{image_hash}.png``.

    If a tile duplicates another tile already known to this process, a symlink
    may be created instead of rendering the same tile to PNG again.

    If `min_resolution` is None, don't downsample.
    If `max_resolution` is None, don't upsample.
    """
    with NamedTemporaryFile(suffix='.tif') as tempfile:
        preprocess(inputfile=inputfile, outputfile=tempfile.name,
                   colours=colours, band=band, spatial_ref=spatial_ref,
                   resampling=resampling, compress=compress)
        return image_slice(inputfile=tempfile.name, outputdir=outputdir,
                           renderer=renderer, hasher=hasher)
