from __future__ import absolute_import

import errno
from math import pi
from itertools import count
import os
import re
from subprocess import CalledProcessError, check_output, Popen, PIPE
from tempfile import NamedTemporaryFile
from xml.etree import ElementTree
from xml.etree.ElementTree import Element, SubElement

from osgeo import gdal, osr
from osgeo.gdalconst import (GA_ReadOnly, GRA_Bilinear, GRA_Cubic,
                             GRA_CubicSpline, GRA_Lanczos,
                             GRA_NearestNeighbour)

gdal.UseExceptions()            # Make GDAL throw exceptions on error
osr.UseExceptions()             # And OSR as well.


from .constants import (EPSG_WEB_MERCATOR, GDALBUILDVRT, GDALTRANSLATE,
                        GDALWARP, TILE_SIDE)
from .exceptions import (GdalError, CalledGdalError,
                         UnknownResamplingMethodError, VrtError)
from .types import GdalFormat, XY


RESAMPLING_METHODS = {
    GRA_NearestNeighbour: 'near',
    GRA_Bilinear: 'bilinear',
    GRA_Cubic: 'cubic',
    GRA_CubicSpline: 'cubicspline',
    GRA_Lanczos: 'lanczos',
}


def check_output_gdal(*popenargs, **kwargs):
    p = Popen(stderr=PIPE, stdout=PIPE, *popenargs, **kwargs)
    stdoutdata, stderrdata = p.communicate()
    if p.returncode:
        cmd = kwargs.get("args")
        if cmd is None:
            cmd = popenargs[0]
        raise CalledGdalError(p.returncode, cmd, output=stdoutdata,
                              error=stderrdata.rstrip('\n'))
    return stdoutdata


def preprocess(inputfile, outputfile, colours, band=None, spatial_ref=None,
               resampling=None, compress=None, **kwargs):
    functions = [
        (lambda f: colourize(inputfile=f, colours=colours, band=band)),
        (lambda f: warp(inputfile=f, spatial_ref=spatial_ref,
                        resampling=resampling)),
        (lambda f: expand_colour_bands(inputfile=f)),
    ]
    return pipeline(inputfile=inputfile, outputfile=outputfile,
                    functions=functions, compress=compress, **kwargs)


def pipeline(inputfile, outputfile, functions, **kwargs):
    """
    Applies functions to a GDAL-readable inputfile, rendering to outputfile.

    Functions must be an iterable of single-parameter functions that take a
    filename as input.
    """
    tmpfiles = []
    try:
        previous = inputfile
        for i, f in enumerate(functions):
            current = NamedTemporaryFile(suffix='.vrt', prefix=('gdal%d' % i))
            tmpfiles.append(current)
            current.write(f(previous))
            current.flush()
            previous = current.name
        return render_vrt(inputfile=previous, outputfile=outputfile, **kwargs)
    finally:
        for f in tmpfiles:
            f.close()


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

    Dataset(inputfile)
    command = [
        GDALBUILDVRT,
        '-q',                   # Quiet
        '/dev/stdout',
        inputfile
    ]
    vrt = check_output_gdal([str(e) for e in command])

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
    Dataset(inputfile)

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
        return check_output_gdal([str(e) for e in command])
    except CalledGdalError as e:
        if e.error == ("ERROR 4: `/dev/stdout' not recognised as a supported "
                       "file format."):
            # HACK: WTF?!?
            return e.output
        raise


def warp(inputfile, spatial_ref=None, cmd=GDALWARP, resampling=None,
         maximum_resolution=None):
    """
    Takes an GDAL-readable inputfile and generates the VRT to warp it.
    """
    dataset = Dataset(inputfile)

    warp_cmd = [
        cmd,
        '-q',                   # Quiet - FIXME: Use logging
        '-of', 'VRT',           # Output to VRT
    ]

    # Warping to Mercator.
    #
    # Note that EPSG:3857 replaces this EPSG:3785 but GDAL doesn't know about
    # it yet.
    if spatial_ref is None:
        spatial_ref = SpatialReference.FromEPSG(EPSG_WEB_MERCATOR)
    warp_cmd.extend(['-t_srs', spatial_ref.GetEPSGString()])

    # Resampling method
    if resampling is not None:
        try:
            warp_cmd.extend(['-r', RESAMPLING_METHODS[resampling]])
        except KeyError:
            raise UnknownResamplingMethodError(resampling)

    # Compute the target extents
    src_spatial_ref = dataset.GetSpatialReference()
    transform = CoordinateTransformation(src_spatial_ref, spatial_ref)
    resolution = dataset.GetNativeResolution(transform=transform,
                                             maximum=maximum_resolution)
    target_extents = dataset.GetTiledExtents(transform=transform,
                                             resolution=resolution)
    lower_left, upper_right = target_extents
    warp_cmd.append('-te')
    warp_cmd.extend(map(
        # Ensure that we use as much precision as possible for floating point
        # numbers.
        '{!r}'.format,
        [
            lower_left.x, lower_left.y,   # xmin ymin
            upper_right.x, upper_right.y  # xmax ymax
        ]
    ))

    # Generate an output file with an whole number of tiles, in pixels.
    num_tiles = spatial_ref.GetTilesCount(extents=target_extents,
                                          resolution=resolution)
    warp_cmd.extend([
        '-ts',
        int(num_tiles.x) * TILE_SIDE,
        int(num_tiles.y) * TILE_SIDE
    ])

    # Call gdalwarp
    warp_cmd.extend([inputfile, '/dev/stdout'])
    return check_output_gdal([str(e) for e in warp_cmd])


def render_vrt(inputfile, outputfile, cmd=GDALWARP, working_memory=512,
               compress=None):
    """Generate a GeoTIFF from a vrt string"""
    tmpfile = NamedTemporaryFile(
        suffix='.tif', prefix='gdalrender',
        dir=os.path.dirname(outputfile), delete=False
    )

    try:
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
            '--config', 'GDAL_CACHEMAX', working_memory
        ])

        # Use compression
        compress = str(compress).upper()
        if compress and compress != 'NONE':
            warp_cmd.extend(['-co', 'COMPRESS=%s' % compress])
            if compress in ('LZW', 'DEFLATE'):
                warp_cmd.extend(['-co', 'PREDICTOR=2'])

        # Run gdalwarp and output to tmpfile.name
        warp_cmd.extend([inputfile, tmpfile.name])
        check_output_gdal([str(e) for e in warp_cmd])

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


# Utility classes that wrap GDAL because its SWIG bindings are not Pythonic.

class CoordinateTransformation(osr.CoordinateTransformation):
    def __init__(self, src_ref, dst_ref):
        # GDAL doesn't give us access to the source and destination
        # SpatialReferences, so we save them in the object.
        self.src_ref = src_ref
        self.dst_ref = dst_ref

        super(CoordinateTransformation, self).__init__(self.src_ref,
                                                       self.dst_ref)


class Dataset(gdal.Dataset):
    def __init__(self, inputfile, mode=GA_ReadOnly):
        """
        Opens a GDAL-readable file.

        Raises a GdalError if inputfile is invalid.
        """
        # Open the input file and read some metadata
        open(inputfile, 'r').close()  # HACK: GDAL gives a useless exception
        try:
            # Since this is a SWIG object, clone the ``this`` pointer
            self.this = gdal.Open(inputfile, mode).this
        except RuntimeError as e:
            raise GdalError(e.message)

    def GetSpatialReference(self):
        return SpatialReference(self.GetProjection())

    def GetCoordinateTransformation(self, dst_ref):
        return CoordinateTransformation(src_ref=self.GetSpatialReference(),
                                        dst_ref=dst_ref)

    def GetNativeResolution(self, transform=None, maximum=None):
        """
        Get a native destination resolution that does not reduce the precision
        of the source data.
        """
        # Get the source projection's units for a 1x1 pixel
        _, width, _, _, _, height = self.GetGeoTransform()
        src_pixel_size = min(abs(width), abs(height))

        if transform is None:
            dst_pixel_size = src_pixel_size
            dst_ref = self.GetSpatialReference()
        else:
            # Transform these dimensions into the destination projection
            dst_pixel_size = transform.TransformPoint(src_pixel_size, 0)[0]
            dst_pixel_size = abs(dst_pixel_size)
            dst_ref = transform.dst_ref

        # We allow some floating point error between src_pixel_size and
        # dst_pixel_size
        error = dst_pixel_size * 1.0e-06

        # Find the resolution where the pixels are smaller than dst_pixel_size.
        for resolution in count():
            if maximum is not None and resolution >= maximum:
                return resolution

            res_pixel_size = max(
                *dst_ref.GetPixelDimensions(resolution=resolution)
            )
            if (res_pixel_size - dst_pixel_size) <= error:
                return resolution

    def PixelCoordinates(self, x, y, transform=None):
        """
        Transforms pixel co-ordinates into the destination projection.

        If transform is None, no reprojection occurs and the dataset's
        SpatialReference is used.
        """
        # Assert that pixel_x and pixel_y are valid
        if not 0 <= x <= self.RasterXSize:
            raise ValueError('x %r is not between 0 and %d' %
                             (x, self.RasterXSize))
        if not 0 <= y <= self.RasterYSize:
            raise ValueError('y %r is not between 0 and %d' %
                             (y, self.RasterYSize))

        geotransform = self.GetGeoTransform()
        coords = XY(
            geotransform[0] + geotransform[1] * x + geotransform[2] * y,
            geotransform[3] + geotransform[4] * x + geotransform[5] * y
        )

        if transform is None:
            return coords

        # Reproject
        return XY(*transform.TransformPoint(coords.x, coords.y)[0:2])

    def GetExtents(self, transform=None):
        """
        Returns (lower-left, upper-right) extents in transform's destination
        projection.

        If transform is None, no reprojection occurs and the dataset's
        SpatialReference is used.
        """
        # Prepare GDAL functions to compute extents
        x_size, y_size = self.RasterXSize, self.RasterYSize

        # Compute four corners in destination projection
        upper_left = self.PixelCoordinates(0, 0,
                                           transform=transform)
        upper_right = self.PixelCoordinates(x_size, 0,
                                            transform=transform)
        lower_left = self.PixelCoordinates(0, y_size,
                                           transform=transform)
        lower_right = self.PixelCoordinates(x_size, y_size,
                                            transform=transform)
        x_values, y_values = zip(upper_left, upper_right,
                                 lower_left, lower_right)

        # Return lower-left and upper-right extents
        left, right = min(x_values), max(x_values)
        bottom, top = min(y_values), max(y_values)
        return (XY(left, bottom), XY(right, top))

    def GetTiledExtents(self, transform=None, resolution=None):
        if resolution is None:
            resolution = self.GetNativeResolution(transform=transform)

        # Get the tile dimensions in map units
        if transform is None:
            spatial_ref = self.GetSpatialReference()
        else:
            spatial_ref = transform.dst_ref
        tile_width, tile_height = spatial_ref.GetTileDimensions(
            resolution=resolution
        )

        # Project the extents to the destination projection.
        lower_left, upper_right = self.GetExtents(transform=transform)

        # Correct for origin, because you can't do modular arithmetic on
        # half-tiles.
        major_offset = spatial_ref.GetMajorCircumference() / 2
        minor_offset = spatial_ref.GetMinorCircumference() / 2
        if spatial_ref.IsProjected() == 0:
            # The semi-minor-axis is only off by 1/4 of the world
            minor_offset = spatial_ref.GetMinorCircumference() / 4

        left = lower_left.x + major_offset
        right = upper_right.x + major_offset
        bottom = lower_left.y + minor_offset
        top = upper_right.y + minor_offset

        # Compute the extents aligned to the above tiles.
        left -= left % tile_width
        right += -right % tile_width
        bottom -= bottom % tile_height
        top += -top % tile_height

        # Undo the correction.
        left -= major_offset
        bottom -= minor_offset
        right -= major_offset
        top -= minor_offset

        # FIXME: Ensure that the extents within the boundaries of the
        # destination projection.

        return (XY(left, bottom), XY(right, top))


class SpatialReference(osr.SpatialReference):
    def __init__(self, *args, **kwargs):
        super(SpatialReference, self).__init__(*args, **kwargs)
        self._angular_transform = None

    @classmethod
    def FromEPSG(cls, code):
        s = cls()
        s.ImportFromEPSG(code)
        return s

    def __eq__(self, other):
        return bool(self.IsSame(other))

    def GetEPSGCode(self):
        epsg_string = self.GetEPSGString()
        if epsg_string:
            return int(epsg_string.split(':')[1])

    def GetEPSGString(self):
        if self.IsLocal() == 1:
            return

        if self.IsGeographic() == 1:
            cstype = 'GEOGCS'
        else:
            cstype = 'PROJCS'
        return '{0}:{1}'.format(self.GetAuthorityName(cstype),
                                self.GetAuthorityCode(cstype))

    def GetMajorCircumference(self):
        if self.IsProjected() == 0:
            return 2 * pi / self.GetAngularUnits()
        return self.GetSemiMajor() * 2 * pi / self.GetLinearUnits()

    def GetMinorCircumference(self):
        if self.IsProjected() == 0:
            return 2 * pi / self.GetAngularUnits()
        return self.GetSemiMinor() * 2 * pi / self.GetLinearUnits()

    def GetPixelDimensions(self, resolution):
        # Assume square pixels.
        width, height = self.GetTileDimensions(resolution=resolution)
        return XY(width / TILE_SIDE,
                  height / TILE_SIDE)

    def GetTileDimensions(self, resolution):
        # Assume square tiles.
        width = self.GetMajorCircumference() / 2 ** resolution
        height = self.GetMinorCircumference() / 2 ** resolution
        if self.IsProjected() == 0:
            # Resolution 0 only covers a longitudinal hemisphere
            return XY(width / 2, height / 2)
        else:
            # Resolution 0 covers the whole world
            return XY(width, height)

    def GetTilesCount(self, extents, resolution):
        lower_left, upper_right = extents

        width = upper_right.x - lower_left.x
        height = upper_right.y - lower_left.y

        tile_width, tile_height = self.GetTileDimensions(resolution=resolution)

        return XY(int(round(width / tile_width)),
                  int(round(height / tile_height)))
