from __future__ import absolute_import

from collections import OrderedDict
import errno
from math import pi
from itertools import count
from operator import itemgetter
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
from .exceptions import (GdalError, CalledGdalError, UnalignedInputError,
                         UnknownResamplingMethodError, VrtError)
from .types import Extents, GdalFormat, XY


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
    Applies VRT-functions to a GDAL-readable inputfile, rendering to outputfile.

    Functions must be an iterable of single-parameter functions that take a
    filename as input.
    """
    if not functions:
        raise ValueError('Must have at least one function')

    tmpfiles = []
    try:
        previous = inputfile
        for i, f in enumerate(functions):
            vrt = f(previous)
            current = vrt.get_tempfile(suffix='.vrt', prefix=('gdal%d' % i))
            tmpfiles.append(current)
            previous = current.name
        return vrt.render(outputfile=outputfile, **kwargs)
    finally:
        for f in tmpfiles:
            f.close()


def colourize(inputfile, colours, band=None):
    """
    Takes an GDAL-readable inputfile and generates the VRT to colourize it.

    You can also specify a ComplexSource Look Up Table (LUT) that allows you to
    interpolate colours between source values.
        colours = {0: rgba(0, 0, 0, 255),
                   10: rgba(255, 255, 255, 255)}
    This means that at value 5, the colour represented would be
    rgba(128, 128, 128, 255).
    """
    if not hasattr(colours, 'items'):
        raise TypeError(
            'colours must be a dict, not a {}'.format(type(colours))
        )
    if band is None:
        band = 1

    Dataset(inputfile)
    command = [
        GDALBUILDVRT,
        '-q',                   # Quiet
        '/dev/stdout',
        inputfile
    ]
    vrt = VRT(check_output_gdal([str(e) for e in command]))

    # Assert that it is actually a VRT file
    root = vrt.get_root()
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

    # Sort the colours by value
    colours = OrderedDict(sorted(colours.items(), key=itemgetter(0)))

    # Set up the colour palette
    rasterband.set('band', '1')   # Destination band should always be 1
    rasterband.find('ColorInterp').text = 'Palette'
    colortable = SubElement(rasterband, 'ColorTable')
    colortable.extend(
        Element('Entry', c1=str(c.r), c2=str(c.g), c3=str(c.b), c4=str(c.a))
        for c in colours.values()
    )

    # Define the colour lookup table
    source = rasterband.find('ComplexSource')
    if source is None:
        source = rasterband.find('SimpleSource')
        source.tag = 'ComplexSource'

    lut = source.find('LUT')
    if lut is None:
        lut = SubElement(source, 'LUT')
    lut.text = ',\n'.join('%s:%d' % (band_value, i)
                          for i, band_value in enumerate(colours.keys()))

    vrt.update_content(root=root)
    return vrt


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
        return VRT(check_output_gdal([str(e) for e in command]))
    except CalledGdalError as e:
        if e.error == ("ERROR 4: `/dev/stdout' not recognised as a supported "
                       "file format."):
            # HACK: WTF?!?
            return VRT(e.output)
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
    extents = dataset.GetTiledExtents(transform=transform,
                                             resolution=resolution)
    warp_cmd.append('-te')
    warp_cmd.extend(map(
        # Ensure that we use as much precision as possible for floating point
        # numbers.
        '{!r}'.format,
        [
            extents.lower_left.x, extents.lower_left.y,   # xmin ymin
            extents.upper_right.x, extents.upper_right.y  # xmax ymax
        ]
    ))

    # Generate an output file with an whole number of tiles, in pixels.
    num_tiles = spatial_ref.GetTilesCount(extents=extents,
                                          resolution=resolution)
    warp_cmd.extend([
        '-ts',
        int(num_tiles.x) * TILE_SIDE,
        int(num_tiles.y) * TILE_SIDE
    ])

    # Propagate No Data Value
    nodata_values = [dataset.GetRasterBand(i).GetNoDataValue()
                     for i in range(1, dataset.RasterCount + 1)]
    if any(nodata_values):
        nodata_values = [str(v).lower() for v in nodata_values]
        warp_cmd.extend(['-dstnodata', ' '.join(nodata_values)])

    # Call gdalwarp
    warp_cmd.extend([inputfile, '/dev/stdout'])
    return VRT(check_output_gdal([str(e) for e in warp_cmd]))


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
        return Extents(lower_left=XY(min(x_values), min(y_values)),
                       upper_right=XY(max(x_values), max(y_values)))

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
        extents = self.GetExtents(transform=transform)

        # Correct for origin, because you can't do modular arithmetic on
        # half-tiles.
        left, bottom = spatial_ref.OffsetPoint(*extents.lower_left)
        right, top = spatial_ref.OffsetPoint(*extents.upper_right)

        # Compute the extents aligned to the above tiles.
        left -= left % tile_width
        right += -right % tile_width
        bottom -= bottom % tile_height
        top += -top % tile_height

        # FIXME: Ensure that the extents within the boundaries of the
        # destination projection.

        # Undo the correction.
        return Extents(
            lower_left=spatial_ref.OffsetPoint(left, bottom, reverse=True),
            upper_right=spatial_ref.OffsetPoint(right, top, reverse=True)
        )

    def GetTmsExtents(self):
        """
        Returns (lower-left, upper-right) TMS tile coordinates.

        The upper-right coordinates are excluded from the range, while the
        lower-left are included.
        """
        resolution = self.GetNativeResolution()

        spatial_ref = self.GetSpatialReference()
        tile_width, tile_height = spatial_ref.GetTileDimensions(
            resolution=resolution
        )

        # Get the extents in the native projection.
        extents = self.GetTiledExtents()
        if not extents.almost_equal(self.GetExtents(), places=2):
            raise UnalignedInputError('Dataset is not aligned to TMS grid')

        # Correct for origin, because you can't do modular arithmetic on
        # half-tiles.
        left, bottom = spatial_ref.OffsetPoint(*extents.lower_left)
        right, top = spatial_ref.OffsetPoint(*extents.upper_right)

        # Divide by number of tiles
        return Extents(lower_left=XY(int(left / tile_width),
                                     int(bottom / tile_height)),
                       upper_right=XY(int(right / tile_width),
                                      int(top / tile_height)))


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

    def OffsetPoint(self, x, y, reverse=False):
        major_offset = self.GetMajorCircumference() / 2
        minor_offset = self.GetMinorCircumference() / 2
        if self.IsProjected() == 0:
            # The semi-minor-axis is only off by 1/4 of the world
            minor_offset = self.GetMinorCircumference() / 4

        if reverse:
            major_offset = -major_offset
            minor_offset = -minor_offset

        return XY(x + major_offset,
                  y + minor_offset)

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
        width = extents.upper_right.x - extents.lower_left.x
        height = extents.upper_right.y - extents.lower_left.y

        tile_width, tile_height = self.GetTileDimensions(resolution=resolution)

        return XY(int(round(width / tile_width)),
                  int(round(height / tile_height)))


class VRT(object):
    def __init__(self, content):
        self.content = content

    def __str__(self):
        return self.content

    def get_root(self):
        return ElementTree.fromstring(self.content)

    def update_content(self, root):
        self.content = ElementTree.tostring(root)

    def get_tempfile(self, **kwargs):
        kwargs.setdefault('suffix', '.vrt')
        tempfile = NamedTemporaryFile(**kwargs)
        tempfile.write(self.content)
        tempfile.flush()
        tempfile.seek(0)
        return tempfile

    def render(self, outputfile, cmd=GDALWARP, working_memory=512,
               compress=None, tempdir=None):
        """Generate a GeoTIFF from a vrt string"""
        tmpfile = NamedTemporaryFile(
            suffix='.tif', prefix='gdalrender',
            dir=os.path.dirname(outputfile), delete=False
        )

        try:
            with self.get_tempfile(dir=tempdir) as inputfile:
                warp_cmd = [
                    cmd,
                    '-q',                   # Quiet - FIXME: Use logging
                    '-of', 'GTiff',         # Output to GeoTIFF
                    '-multi',               # Use multiple processes
                    '-overwrite',           # Overwrite outputfile
                    '-co', 'BIGTIFF=IF_NEEDED',  # Use BigTIFF if needed
                ]

                # Set the working memory so that gdalwarp doesn't stall of disk
                # I/O
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
                warp_cmd.extend([inputfile.name, tmpfile.name])
                check_output_gdal([str(e) for e in warp_cmd])

                # If it succeeds, then we move it to overwrite the actual
                # output
                os.rename(tmpfile.name, outputfile)
        finally:
            try:
                os.remove(tmpfile.name)
            except OSError as e:
                if e.errno != errno.ENOENT:
                    raise
