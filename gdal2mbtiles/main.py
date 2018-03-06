# -*- coding: utf-8 -*-

# Quickstart
# ----------
#
# To turn any GDAL-readable file into an MBTiles file, run:
#   $ gdal2mbtiles filename.tiff
# This creates a filename.mbtiles that can be served from a TMS service like
# Mapbox.
#
# You can explicitly specify an output filename:
#   $ gdal2mbtiles input.tiff output.mbtiles
#
# You can also pipe in any GDAL-readable file:
#   $ cat input.tiff | gdal2mbtiles > output.mbtiles
#
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


import argparse
from contextlib import contextmanager
import logging
import os
from shutil import copyfileobj
import sys
from tempfile import NamedTemporaryFile

if __name__ == '__main__' and __package__ is None:
    # HACK: Force this to work when called directly
    import gdal2mbtiles
    __package__ = gdal2mbtiles.__name__

from .gdal import RESAMPLING_METHODS, SpatialReference
from .gd_types import rgba
from .mbtiles import Metadata


COLORING_METHODS = {
    'exact': 'ColorExact',
    'gradient': 'ColorGradient',
    'palette': 'ColorPalette',
}


def coloring_arg(s):
    """Validates --coloring"""
    from gdal2mbtiles import vips
    if s is None:
        return None
    return getattr(vips, COLORING_METHODS[s])


def color_arg(s):
    """Validates --color"""
    try:
        band_value, html_color = s.split(':', 1)
    except ValueError:
        raise argparse.ArgumentTypeError(
            "'{0}' must be in format: BAND-VALUE:HTML-COLOR".format(s)
        )

    try:
        band_value = float(band_value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            "'{0}' is not a valid number".format(band_value)
        )

    try:
        color = rgba.webcolor(html_color)
    except ValueError:
        raise argparse.ArgumentTypeError(
            "'{0}' is not a valid HTML color".format(html_color)
        )

    return band_value, color


def colorize_band_arg(s):
    """Validates --colorize-band"""
    try:
        result = int(s)
    except ValueError:
        raise argparse.ArgumentTypeError("invalid int value: '{0}'".format(s))
    if result <= 0:
        raise argparse.ArgumentTypeError(
            "'{0}' must be 1 or greater".format(s)
        )
    return result


def parse_args(args):
    """Parses command-line `args`"""

    LatestMetadata = Metadata.latest()

    parser = argparse.ArgumentParser(
        description='Converts a GDAL-readable into an MBTiles file'
    )
    parser.add_argument('-v', '--verbose', action='count',
                        help='explain what is being done')

    group = parser.add_argument_group(title='Positional arguments')
    group.add_argument('INPUT', type=argparse.FileType('rb'), nargs='?',
                       default=sys.stdin,
                       help='GDAL-readable file.')
    group.add_argument('OUTPUT', type=argparse.FileType('wb'), nargs='?',
                       help='Output filename. Defaults to INPUT.mbtiles')

    group = parser.add_argument_group(title='MBTiles metadata arguments')
    group.add_argument('--name', default=None,
                       help=('Human-readable name of the tileset. '
                             'Defaults to INPUT'))
    group.add_argument('--description', default="",
                       help='Description of the layer. Defaults to ""')
    group.add_argument('--layer-type',
                       default=LatestMetadata.TYPES.OVERLAY,
                       choices=LatestMetadata.TYPES,
                       help='Type of layer. Defaults to "overlay"')
    group.add_argument('--version', default='1.0.0',
                       help='Version of the tileset. Defaults to "1.0.0"')
    group.add_argument('--format',
                       default=LatestMetadata.FORMATS.PNG,
                       choices=LatestMetadata.FORMATS,
                       help='Tile image format. Defaults to "png"')

    group = parser.add_argument_group(title='GDAL warp arguments')
    group.add_argument('--spatial-reference', type=int, default=3857,
                       help=('Destination EPSG spatial reference. '
                             'Defaults to 3857'))
    group.add_argument('--resampling',
                       default='near',
                       choices=list(RESAMPLING_METHODS.values()),
                       help=('Resampling algorithm for warping. '
                             'Defaults to "near" (nearest-neighbour)'))

    group = parser.add_argument_group(title='Rendering arguments')
    group.add_argument('--min-resolution', type=int, default=None,
                       help=('Minimum resolution to render and slice. '
                             'Defaults to None (do not downsample)'))
    group.add_argument('--max-resolution', type=int, default=None,
                       help=('Maximum resolution to render and slice. '
                             'Defaults to None (do not upsample)'))
    group.add_argument('--fill-borders',
                       action='store_const', const=True, default=True,
                       help=('Fill image to whole world with empty tiles. '
                             'Default.'))
    group.add_argument('--no-fill-borders', dest='fill_borders',
                       action='store_const', const=False,
                       help='Do not add borders to fill image.')
    group.add_argument('--zoom-offset', type=int, default=0,
                       metavar='N',
                       help=('Offset zoom level by N to fit unprojected '
                             'images to square maps. Defaults to 0.'))

    group = parser.add_argument_group(title='Coloring arguments')
    group.add_argument('--coloring', default=None,
                       choices=COLORING_METHODS,
                       help='Coloring algorithm.')
    group.add_argument('--color', dest='colors', action='append',
                       type=color_arg, metavar='BAND-VALUE:HTML-COLOR',
                       help=('Examples: --color="0:#ff00ff" --color=255:red'))
    group.add_argument('--colorize-band', metavar='COLORIZE-BAND',
                       type=colorize_band_arg, default=None,
                       help='Raster band to colorize. Defaults to 1')

    args = parser.parse_args(args=args)

    # Guess at the OUTPUT based on the INPUT
    if args.OUTPUT is None:
        if args.INPUT == sys.stdin:
            args.OUTPUT = sys.stdout
        else:
            # Set default output name based on input name
            args.OUTPUT = open(
                os.path.splitext(args.INPUT.name)[0] + '.mbtiles',
                mode='wb'
            )

    if args.name is None:
        args.name = os.path.basename(args.INPUT.name)

    # Make sure that --color and --coloring match up
    if args.coloring is None and (args.colors or
                                  args.colorize_band is not None):
        parser.error('must provide --coloring')
    elif args.coloring is not None and not args.colors:
        parser.error('must provide at least one --color')

    # Transform choices into ColorBase classes
    args.coloring = coloring_arg(args.coloring)

    return args


@contextmanager
def input_output(inputfile, outputfile):
    tempfiles = []

    infile = inputfile
    if inputfile == sys.stdin:
        infile = NamedTemporaryFile()
        copyfileobj(inputfile, infile)
        infile.seek(0)
        tempfiles.append(infile)

    outfile = outputfile
    if outputfile == sys.stdout:
        outfile = NamedTemporaryFile()
        tempfiles.append(outfile)

    try:
        yield infile, outfile
        if outputfile == sys.stdout:
            copyfileobj(open(outfile.name, 'rb'), outputfile)
    finally:
        for f in tempfiles:
            f.close()


def main(args=None, use_logging=True):
    if args is None:
        args = sys.argv[1:]
    args = parse_args(args=args)

    if use_logging:
        configure_logging(args)

    # HACK: Import here, so that VIPS doesn't parse sys.argv!!!
    # In vimagemodule.cxx, SWIG_init actually does argument parsing
    from gdal2mbtiles.helpers import warp_mbtiles

    with input_output(inputfile=args.INPUT,
                      outputfile=args.OUTPUT) as (inputfile, outputfile):
        # MBTiles
        metadata = dict(
            description=args.description,
            format=args.format,
            name=args.name,
            type=args.layer_type,
            version=args.version,
        )

        # GDAL
        spatial_ref = SpatialReference.FromEPSG(args.spatial_reference)

        # Coloring
        if not args.coloring:
            colors = band = None
        else:
            colors = args.coloring(args.colors)
            band = args.colorize_band

        warp_mbtiles(inputfile=inputfile.name, outputfile=outputfile.name,
                     # MBTiles
                     metadata=metadata,
                     # GDAL
                     spatial_ref=spatial_ref, resampling=args.resampling,
                     # Rendering
                     min_resolution=args.min_resolution,
                     max_resolution=args.max_resolution,
                     fill_borders=args.fill_borders,
                     zoom_offset=args.zoom_offset,
                     # Coloring
                     colors=colors, band=band)
        return 0


def configure_logging(args):
    if not args.verbose:
        return

    if args.verbose == 1:
        level = logging.INFO
        fmt = '%(message)s'
    else:
        level = logging.DEBUG
        fmt = '%(asctime)s %(module)s: %(message)s'

    logging.basicConfig(level=level, format=fmt,
                        datefmt='%Y-%m-%d %H:%M:%S')


if __name__ == '__main__':
    retcode = main(args=sys.argv[1:])
    sys.exit(retcode)
