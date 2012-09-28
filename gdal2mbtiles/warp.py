from __future__ import absolute_import

import errno
from math import ceil
import os
import re
from subprocess import CalledProcessError, Popen, PIPE
from tempfile import NamedTemporaryFile
from xml.etree import ElementTree
from xml.etree.ElementTree import Element, SubElement

from .constants import GDALBUILDVRT, GDALTRANSLATE, GDALWARP
from .exceptions import (GdalError, CalledGdalError,
                         UnknownResamplingMethodError, VrtError)
from .types import GdalFormat, rgba


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


def check_output_gdalwarp(*popenargs, **kwargs):
    p = Popen(stderr=PIPE, stdout=PIPE, *popenargs, **kwargs)
    stdoutdata, stderrdata = p.communicate()
    if p.returncode:
        cmd = kwargs.get("args")
        if cmd is None:
            cmd = popenargs[0]
        raise CalledGdalError(p.returncode, cmd, output=stdoutdata,
                              error=stderrdata.rstrip('\n'))
    return stdoutdata


def gdal_open(inputfile):
    """
    Opens a GDAL-readable file.

    Raises a GdalError if inputfile is invalid.
    """
    # Open the input file and read some metadata
    open(inputfile, 'r').close()  # HACK: GDAL doesn't give a useful exception
    try:
        return gdal.Open(inputfile, GA_ReadOnly)
    except RuntimeError as e:
        raise GdalError(e.message)


def preprocess(inputfile, outputfile, colours, band=None, resampling=None,
               compress=None):
    with NamedTemporaryFile(suffix='.vrt', prefix='gdalcoloured') as coloured:
        coloured.write(colourize(inputfile=inputfile,
                                 colours=colours,
                                 band=band))
        coloured.flush()

        with NamedTemporaryFile(suffix='.vrt', prefix='gdalwarped') as warped:
            warped.write(warp(inputfile=coloured.name,
                              resampling=resampling))
            warped.flush()

            vrt = expand_colour_bands(inputfile=warped.name)

            vrt_to_geotiff(vrt=vrt, outputfile=outputfile,
                           compress=compress)


def colourize(inputfile, colours, band=None):
    """
    Takes an GDAL-readable inputfile and generates the VRT to colourize it.

    You can also specify a ComplexSource Look Up Table (LUT) that allows you to
    interpolate colours between source values.
        colours = [(0, rgba(0, 0, 0, 255),
                   (10, rgba(255, 255, 255, 255)))]
    This means that at value 5, the colour represented would be
    rgba(128, 128, 128, 255).
    """
    if band is None:
        band = 1

    gdal_open(inputfile)
    command = [
        GDALBUILDVRT,
        '-q',                   # Quiet
        '/dev/stdout',
        inputfile
    ]
    vrt = check_output_gdalwarp([str(e) for e in command])

    # Assert that it is actually a VRT file
    root = ElementTree.fromstring(vrt)
    if root.tag != 'VRTDataset':
        raise VrtError('Not a VRTDataset: %s' %
                       vrt[:80])

    rasterband = None
    # Remove VRTRasterBands that do not map to the requested band
    for rb in root.findall(".//VRTRasterBand"):
        if rb.get('band') == str(band):
            rasterband = rb
        else:
            root.remove(rb)
    if rasterband is None:
        raise VrtError('Cannot locate VRTRasterBand %d' % band)

    # Set up the colour palette
    rasterband.set('band', '1')   # Destination band should always be 1
    rasterband.find('ColorInterp').text = 'Palette'
    colortable = SubElement(rasterband, 'ColorTable')
    colortable.extend(
        Element('Entry', c1=str(c.r), c2=str(c.g), c3=str(c.b), c4=str(c.a))
        for _, c in colours
    )

    # Define the colour lookup table
    source = rasterband.find('SimpleSource')
    source.tag = 'ComplexSource'
    lut = SubElement(source, 'LUT')
    lut.text = ',\n'.join('%s:%d' % (value[0], i)
                                     for i, value in enumerate(colours))

    return ElementTree.tostring(root)


def expand_colour_bands(inputfile):
    """
    Takes a paletted inputfile (probably a VRT) and generates a RGBA VRT.
    """
    f = gdal_open(inputfile)

    command = [
        GDALTRANSLATE,
        '-q',                   # Quiet
        '-of', 'VRT',           # Output to VRT
        '-expand', 'rgba',      # RGBA bands
        '-ot', 'Byte',          # 8-bit bands (so that GIMP can open)
        inputfile,
        '/dev/stdout'
    ]
    try:
        return check_output_gdalwarp([str(e) for e in command])
    except CalledGdalError as e:
        if e.error == "ERROR 4: `/dev/stdout' not recognised as a supported file format.":
            # HACK: WTF?!?
            return e.output
        raise


def warp(inputfile, cmd=GDALWARP, resampling=None):
    """
    Takes an GDAL-readable inputfile and generates the VRT to warp it.
    """
    f = gdal_open(inputfile)

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
    return check_output_gdalwarp([str(e) for e in warp_cmd])


def vrt_to_geotiff(vrt, outputfile, cmd=GDALWARP, working_memory=512,
                   compress=None):
    """Generate a GeoTIFF from a vrt string"""
    tmpfile = NamedTemporaryFile(
        suffix='.tif', prefix='gdal2mbtiles',
        dir=os.path.dirname(outputfile), delete=False
    )

    try:
        with NamedTemporaryFile(suffix='.vrt',
                                prefix='gdal2mbtiles') as inputfile:
            inputfile.write(vrt)
            inputfile.flush()

            warp_cmd = [
                cmd,
                '-q',                   # Quiet - FIXME: Use logging
                '-of', 'GTiff',         # Output to GeoTIFF
                '-multi',               # Use multiple processes
                '-overwrite',           # Overwrite output if it already exists
                '-co', 'BIGTIFF=IF_NEEDED',  # Use BigTIFF if needed
            ]

            # Set the working memory so that gdalwarp doesn't stall of disk I/O
            warp_cmd.extend([
                '-wm', working_memory,
                '--config', 'GDAL_CACHE_MAX', working_memory
            ])

            # Use compression
            compress = str(compress).upper()
            if compress and compress != 'NONE':
                warp_cmd.extend(['-co', 'COMPRESS=%s' % compress])
                if compress in ('LZW', 'DEFLATE'):
                    warp_cmd.extend(['-co', 'PREDICTOR=2'])

            # Run gdalwarp and output to tmpfile.name
            warp_cmd.extend([inputfile.name, tmpfile.name])
            check_output_gdalwarp([str(e) for e in warp_cmd])

            # If it succeeds, then we move it to overwrite the actual output
            os.rename(tmpfile.name, outputfile)
    finally:
        try:
            os.remove(tmpfile.name)
        except OSError as e:
            if e.errno != errno.ENOENT:
                raise


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
