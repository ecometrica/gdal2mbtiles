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

from functools import partial
from tempfile import NamedTemporaryFile

from .gdal import Dataset, preprocess
from .renderers import PngRenderer
from .storages import MbtilesStorage, NestedFileStorage, SimpleFileStorage
from .vips import TmsPyramid, validate_resolutions


def image_mbtiles(inputfile, outputfile, metadata,
                  min_resolution=None, max_resolution=None, fill_borders=None,
                  zoom_offset=None, colors=None, renderer=None,
                  preprocessor=None):
    """
    Slices a GDAL-readable inputfile into a pyramid of PNG tiles.

    inputfile: Filename
    outputfile: The output .mbtiles file.
    min_resolution: Minimum resolution to downsample tiles.
    max_resolution: Maximum resolution to upsample tiles.
    fill_borders: Fill borders of image with empty tiles.
    zoom_offset: Offset zoom level to fit unprojected images to square maps.

    colors: Color palette applied to single band files.
            colors=ColorGradient({0: rgba(0, 0, 0, 255),
                                  10: rgba(255, 255, 255, 255)})
            Defaults to no colorization.
    preprocessor: Function to run on the TmsPyramid before slicing.

    If `min_resolution` is None, don't downsample.
    If `max_resolution` is None, don't upsample.
    """
    if renderer is None:
        renderer = PngRenderer()

    with MbtilesStorage.create(filename=outputfile,
                               metadata=metadata,
                               zoom_offset=zoom_offset,
                               renderer=renderer) as storage:
        pyramid = TmsPyramid(inputfile=inputfile,
                             storage=storage,
                             min_resolution=min_resolution,
                             max_resolution=max_resolution)
        if preprocessor is None:
            preprocessor = colorize

        pyramid = preprocessor(**locals())

        pyramid.slice(fill_borders=fill_borders)

        # Add metadata extensions
        if zoom_offset is None:
            zoom_offset = 0
        if min_resolution is None:
            min_resolution = pyramid.resolution
        if max_resolution is None:
            max_resolution = pyramid.resolution

        metadata = storage.mbtiles.metadata
        metadata['x-minzoom'] = min_resolution + zoom_offset
        metadata['x-maxzoom'] = max_resolution + zoom_offset


def image_pyramid(inputfile, outputdir,
                  min_resolution=None, max_resolution=None, fill_borders=None,
                  colors=None, renderer=None, preprocessor=None):
    """
    Slices a GDAL-readable inputfile into a pyramid of PNG tiles.

    inputfile: Filename
    outputdir: The output directory for the PNG tiles.
    min_resolution: Minimum resolution to downsample tiles.
    max_resolution: Maximum resolution to upsample tiles.
    fill_borders: Fill borders of image with empty tiles.
    preprocessor: Function to run on the TmsPyramid before slicing.

    Filenames are in the format ``{tms_z}/{tms_x}/{tms_y}.png``.

    If a tile duplicates another tile already known to this process, a symlink
    may be created instead of rendering the same tile to PNG again.

    If `min_resolution` is None, don't downsample.
    If `max_resolution` is None, don't upsample.
    """
    if renderer is None:
        renderer = PngRenderer()
    storage = NestedFileStorage(outputdir=outputdir,
                                renderer=renderer)
    pyramid = TmsPyramid(inputfile=inputfile,
                         storage=storage,
                         min_resolution=min_resolution,
                         max_resolution=max_resolution)
    if preprocessor is None:
        preprocessor = colorize
    pyramid = preprocessor(**locals())
    pyramid.slice(fill_borders=fill_borders)


def image_slice(inputfile, outputdir, fill_borders=None,
                colors=None, renderer=None, preprocessor=None):
    """
    Slices a GDAL-readable inputfile into PNG tiles.

    inputfile: Filename
    outputdir: The output directory for the PNG tiles.
    fill_borders: Fill borders of image with empty tiles.
    colors: Color palette applied to single band files.
            colors=ColorGradient({0: rgba(0, 0, 0, 255),
                                  10: rgba(255, 255, 255, 255)})
            Defaults to no colorization.
    preprocessor: Function to run on the TmsPyramid before slicing.

    Filenames are in the format ``{tms_z}-{tms_x}-{tms_y}-{image_hash}.png``.

    If a tile duplicates another tile already known to this process, a symlink
    is created instead of rendering the same tile to PNG again.
    """
    if renderer is None:
        renderer = PngRenderer()
    storage = SimpleFileStorage(outputdir=outputdir,
                                renderer=renderer)
    pyramid = TmsPyramid(inputfile=inputfile,
                         storage=storage,
                         min_resolution=None,
                         max_resolution=None)
    if preprocessor is None:
        preprocessor = colorize
    pyramid = preprocessor(**locals())
    pyramid.slice(fill_borders=fill_borders)


def warp_mbtiles(inputfile, outputfile, metadata, colors=None, band=None,
                 spatial_ref=None, resampling=None,
                 min_resolution=None, max_resolution=None, fill_borders=None,
                 zoom_offset=None, renderer=None):
    """
    Warps a GDAL-readable inputfile into a pyramid of PNG tiles.

    inputfile: Filename
    outputfile: The output .mbtiles file.

    colors: Color palette applied to single band files.
            colors=ColorGradient({0: rgba(0, 0, 0, 255),
                                  10: rgba(255, 255, 255, 255)})
            Defaults to no colorization.
    band: Select band to palettize and expand to RGBA. Defaults to 1.
    spatial_ref: Destination gdal.SpatialReference. Defaults to EPSG:3857,
                 Web Mercator
    resampling: Resampling algorithm. Defaults to GDAL's default,
                nearest neighbour as of GDAL 1.9.1.

    min_resolution: Minimum resolution to downsample tiles.
    max_resolution: Maximum resolution to upsample tiles.
    fill_borders: Fill borders of image with empty tiles.
    zoom_offset: Offset zoom level to fit unprojected images to square maps.

    If `min_resolution` is None, don't downsample.
    If `max_resolution` is None, don't upsample.
    """
    if colors and band is None:
        band = 1
    with NamedTemporaryFile(suffix='.tif') as tempfile:
        dataset = Dataset(inputfile)
        validate_resolutions(resolution=dataset.GetNativeResolution(),
                             min_resolution=min_resolution,
                             max_resolution=max_resolution,
                             strict=False)
        warped = preprocess(inputfile=inputfile, outputfile=tempfile.name,
                            band=band, spatial_ref=spatial_ref,
                            resampling=resampling, compress='LZW')
        preprocessor = partial(resample_after_warp,
                               whole_world=dataset.IsWholeWorld())
        return image_mbtiles(inputfile=warped, outputfile=outputfile,
                             metadata=metadata,
                             min_resolution=min_resolution,
                             max_resolution=max_resolution,
                             colors=colors, renderer=renderer,
                             preprocessor=preprocessor,
                             fill_borders=fill_borders,
                             zoom_offset=zoom_offset)


def warp_pyramid(inputfile, outputdir, colors=None, band=None,
                 spatial_ref=None, resampling=None,
                 min_resolution=None, max_resolution=None, fill_borders=None,
                 renderer=None):
    """
    Warps a GDAL-readable inputfile into a pyramid of PNG tiles.

    inputfile: Filename
    outputdir: The output directory for the PNG tiles.

    colors: Color palette applied to single band files.
            colors=ColorGradient({0: rgba(0, 0, 0, 255),
                                  10: rgba(255, 255, 255, 255)})
            Defaults to no colorization.
    band: Select band to palettize and expand to RGBA. Defaults to 1.
    spatial_ref: Destination gdal.SpatialReference. Defaults to EPSG:3857,
                 Web Mercator
    resampling: Resampling algorithm. Defaults to GDAL's default,
                nearest neighbour as of GDAL 1.9.1.

    min_resolution: Minimum resolution to downsample tiles.
    max_resolution: Maximum resolution to upsample tiles.
    fill_borders: Fill borders of image with empty tiles.

    Filenames are in the format ``{tms_z}/{tms_x}/{tms_y}.png``.

    If a tile duplicates another tile already known to this process, a symlink
    may be created instead of rendering the same tile to PNG again.

    If `min_resolution` is None, don't downsample.
    If `max_resolution` is None, don't upsample.
    """
    if colors and band is None:
        band = 1

    with NamedTemporaryFile(suffix='.tif') as tempfile:
        dataset = Dataset(inputfile)
        validate_resolutions(resolution=dataset.GetNativeResolution(),
                             min_resolution=min_resolution,
                             max_resolution=max_resolution,
                             strict=False)
        warped = preprocess(inputfile=inputfile, outputfile=tempfile.name,
                            band=band, spatial_ref=spatial_ref,
                            resampling=resampling, compress='LZW')
        preprocessor = partial(resample_after_warp,
                               whole_world=dataset.IsWholeWorld())
        return image_pyramid(inputfile=warped, outputdir=outputdir,
                             min_resolution=min_resolution,
                             max_resolution=max_resolution,
                             colors=colors, renderer=renderer,
                             preprocessor=preprocessor,
                             fill_borders=fill_borders)


def warp_slice(inputfile, outputdir, fill_borders=None, colors=None, band=None,
               spatial_ref=None, resampling=None,
               renderer=None):
    """
    Warps a GDAL-readable inputfile into a directory of PNG tiles.

    inputfile: Filename
    outputdir: The output directory for the PNG tiles.

    fill_borders: Fill borders of image with empty tiles.
    colors: Color palette applied to single band files.
            colors=ColorGradient({0: rgba(0, 0, 0, 255),
                                  10: rgba(255, 255, 255, 255)})
            Defaults to no colorization.
    band: Select band to palettize and expand to RGBA. Defaults to 1.
    spatial_ref: Destination gdal.SpatialReference. Defaults to EPSG:3857,
                 Web Mercator
    resampling: Resampling algorithm. Defaults to GDAL's default,
                nearest neighbour as of GDAL 1.9.1.

    min_resolution: Minimum resolution to downsample tiles.
    max_resolution: Maximum resolution to upsample tiles.

    Filenames are in the format ``{tms_z}-{tms_x}-{tms_y}-{image_hash}.png``.

    If a tile duplicates another tile already known to this process, a symlink
    may be created instead of rendering the same tile to PNG again.
    """
    if colors and band is None:
        band = 1

    with NamedTemporaryFile(suffix='.tif') as tempfile:
        dataset = Dataset(inputfile)
        warped = preprocess(inputfile=inputfile, outputfile=tempfile.name,
                            band=band, spatial_ref=spatial_ref,
                            resampling=resampling, compress='LZW')
        preprocessor = partial(resample_after_warp,
                               whole_world=dataset.IsWholeWorld())
        return image_slice(inputfile=warped, outputdir=outputdir,
                           colors=colors, renderer=renderer,
                           preprocessor=preprocessor,
                           fill_borders=fill_borders)


# Preprocessors

def resample_after_warp(pyramid, colors, whole_world, **kwargs):
    resolution = pyramid.dataset.GetNativeResolution()
    if whole_world:
        # We must resample the image to fit whole tiles, even if this makes the
        # extents of the image go PAST the full world.
        #
        # This is because GDAL sometimes reprojects from a whole world image
        # into a partial world image, due to rounding errors.
        pyramid.dataset.resample_to_world()
    else:
        pyramid.dataset.resample(resolution=resolution)
    colorize(pyramid=pyramid, colors=colors)
    pyramid.dataset.align_to_grid(resolution=resolution)
    return pyramid


def colorize(pyramid, colors, **kwargs):
    if colors is not None:
        pyramid.colorize(colors)
    return pyramid
