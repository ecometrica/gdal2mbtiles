from __future__ import absolute_import

from collections import namedtuple
from math import ceil
import re
from subprocess import CalledProcessError, check_output

from .constants import GDALWARP
from .exceptions import GdalError, UnknownResamplingMethodError


def warp_file(srcfile, dstfile, cmd=GDALWARP):
    """Take srcfile as input, write to dstfile, warped to Web Mercator."""
    pass


from osgeo import gdal
from osgeo.gdalconst import (GA_ReadOnly, GRA_Bilinear, GRA_Cubic,
                             GRA_CubicSpline, GRA_Lanczos,
                             GRA_NearestNeighbour)
gdal.UseExceptions()            # Make GDAL throw exceptions on error

RESAMPLING_METHODS = {
    GRA_NearestNeighbour: 'near',
    GRA_Bilinear: 'bilinear',
    GRA_Cubic: 'cubic',
    GRA_CubicSpline: 'cubicspline',
    GRA_Lanczos: 'lanczos',
}


HALF_CIRCUMFERENCE = 20037508.34  # in metres
TILE_SIDE = 256                   # in pixels


def generate_vrt(inputfile, cmd=GDALWARP, resampling=None):
    """
    Generate VRT for inputfile.
    """
    # Open the input file and read some metadata
    open(inputfile, 'r').close()  # HACK: GDAL doesn't give a useful exception
    try:
        f = gdal.Open(inputfile, GA_ReadOnly)
    except RuntimeError as e:
        raise GdalError(e.message)

    # Number of pixels on each side, upsampled to fit perfectly in a zoom
    # level.
    output_side = (ceil(max(f.RasterXSize, f.RasterYSize) / float(TILE_SIDE)) *
                   TILE_SIDE)

    warp_cmd = [
        cmd,
        '-q',                   # Quiet - FIXME: Use logging
        '-of', 'VRT',           # Output to VRT
    ]

    # Warping to Mercator.
    #
    # Note that EPSG:3857 replaces this EPSG:3785 but GDAL doesn't know about
    # it yet.
    warp_cmd.extend(['-t_srs', 'EPSG:3785'])

    # Resampling method
    if resampling is not None:
        try:
            warp_cmd.extend(['-r', RESAMPLING_METHODS[resampling]])
        except KeyError:
            raise UnknownResamplingMethodError(resampling)

    # Default extent: the whole world
    warp_cmd.extend([
        '-te',
        -HALF_CIRCUMFERENCE, -HALF_CIRCUMFERENCE,  # xmin ymin
        HALF_CIRCUMFERENCE, HALF_CIRCUMFERENCE     # xmax ymax
    ])

    # Generate an output file with size: (output_side * output_side) pixels.
    warp_cmd.extend([
        '-ts',
        output_side,          # width
        output_side           # height
    ])

    # Call gdalwarp
    warp_cmd.extend([inputfile, '/dev/stdout'])
    return check_output([str(e) for e in warp_cmd])


GdalFormat = namedtuple(typename='GdalFormat',
                        field_names=['name', 'attributes', 'description',
                                     'can_read', 'can_write', 'can_update',
                                     'has_virtual_io'])


def supported_formats(cmd=GDALWARP):
    if supported_formats._cache is None:
        result = None
        output = check_output([cmd, '--formats'])
        for line in output.splitlines():
            # Look for the header
            if result is None:
                if line == 'Supported Formats:':
                    result = []
                continue

            m = supported_formats.format_re.match(line)
            if m:
                attributes = frozenset(m.group('attributes'))
                result.append(GdalFormat(can_read=('r' in attributes),
                                         can_write=('w' in attributes),
                                         can_update=('+' in attributes),
                                         has_virtual_io=('v' in attributes),
                                         **m.groupdict()))

        supported_formats._cache = result

    return supported_formats._cache
supported_formats.format_re = re.compile(r'\s+(?P<name>.+?)'
                                         r'\s+\((?P<attributes>.+?)\):'
                                         r'\s+(?P<description>.*)$')
supported_formats._cache = None


def resampling_methods(cmd=GDALWARP):
    if resampling_methods._cache is None:
        result = None
        try:
            output = check_output([cmd, '--help'])
        except CalledProcessError as e:
            if e.returncode == 1 and e.output is not None:
                output = e.output
            else:
                raise

        for line in output.splitlines():
            # Look for the header
            if result is None:
                if line == 'Available resampling methods:':
                    result = []
                continue

            result.extend(m.strip(' \t.').split()[0] for m in line.split(','))
            if line.endswith('.'):
                break

        resampling_methods._cache = result

    return resampling_methods._cache
resampling_methods._cache = None
