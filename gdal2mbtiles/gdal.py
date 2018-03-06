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

# Make sure we are using the python 3 version of round in both python 2 and 3
from builtins import round

from functools import partial
import logging
from math import ceil, floor, pi
from itertools import count
import os
import re
from subprocess import CalledProcessError, check_output, Popen, PIPE
from tempfile import NamedTemporaryFile
from xml.etree import ElementTree

import numpy

from osgeo import gdal, gdalconst, osr
from osgeo.gdalconst import (GA_ReadOnly, GRA_Bilinear, GRA_Cubic,
                             GRA_CubicSpline, GRA_Lanczos,
                             GRA_NearestNeighbour)

try:
  basestring
except NameError:
  basestring = str


gdal.UseExceptions()            # Make GDAL throw exceptions on error
osr.UseExceptions()             # And OSR as well.


from .constants import (EPSG_WEB_MERCATOR, ESRI_102113_PROJ, ESRI_102100_PROJ,
                        GDALTRANSLATE, GDALWARP, TILE_SIDE)
from .exceptions import (GdalError, CalledGdalError, UnalignedInputError,
                         UnknownResamplingMethodError)
from .gd_types import Extents, GdalFormat, XY
from .utils import rmfile


logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


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
                              error=stderrdata.decode('utf-8').rstrip('\n'))
    return stdoutdata


def preprocess(inputfile, outputfile, band=None, spatial_ref=None,
               resampling=None, compress=None, **kwargs):
    functions = []
    dataset = Dataset(inputfile)

    # Extract desired band to reduce the amount of warping
    if band is not None and not 1 <= band <= dataset.RasterCount:
        raise ValueError(
            'band {0} must be between 1 and {1}'.format(band,
                                                        dataset.RasterCount)
        )
    if band is not None and dataset.RasterCount > 1:
        functions.append(
            ('Extracting band {0}'.format(band),
             partial(extract_color_band, band=band))
        )

    # Warp
    if spatial_ref is not None and \
            dataset.GetSpatialReference() != spatial_ref:
        functions.append(
            ('Reprojecting to EPSG:{0}'.format(spatial_ref.GetEPSGCode()),
             partial(warp,
                     spatial_ref=spatial_ref, resampling=resampling))
        )

    if not functions:
        # No work needs to be done, so just symlink the outputfile to inputfile
        rmfile(outputfile, ignore_missing=True)
        srcfile = os.path.relpath(inputfile, os.path.dirname(outputfile))
        os.symlink(srcfile, outputfile)
        return inputfile

    return pipeline(inputfile=inputfile, outputfile=outputfile,
                    functions=functions, compress=compress, **kwargs)


def pipeline(inputfile, outputfile, functions, **kwargs):
    """
    Applies VRT-functions to a GDAL-readable inputfile, rendering outputfile.

    Functions must be an iterable of single-parameter functions that take a
    filename as input.
    """
    if not functions:
        raise ValueError('Must have at least one function')

    tmpfiles = []
    try:
        previous = inputfile
        for name, f in functions:
            logging.debug(name)
            vrt = f(previous)
            current = vrt.get_tempfile(suffix='.vrt', prefix='gdal')
            tmpfiles.append(current)
            previous = current.name
        logging.info('Rendering reprojected image')
        return vrt.render(outputfile=outputfile, **kwargs)
    finally:
        for f in tmpfiles:
            f.close()


def extract_color_band(inputfile, band):
    """
    Takes an inputfile (probably a VRT) and generates a single-band VRT.
    """
    dataset = Dataset(inputfile)
    if not 1 <= band <= dataset.RasterCount:
        raise ValueError(
            "band must be between 1 and {0}".format(dataset.RasterCount)
        )

    command = [
        GDALTRANSLATE,
        '-q',                   # Quiet
        '-of', 'VRT',           # Output to VRT
        '-b', band,             # Single band
        inputfile,
        '/vsistdout'
    ]
    try:
        return VRT(check_output_gdal([str(e) for e in command]))
    except CalledGdalError as e:
        if e.error == ("ERROR 6: Read or update mode not supported on /vsistdout"):
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
    if spatial_ref is None:
        spatial_ref = SpatialReference.FromEPSG(EPSG_WEB_MERCATOR)
    warp_cmd.extend(['-t_srs', spatial_ref.GetEPSGString()])

    # Resampling method
    if resampling is not None:
        if not isinstance(resampling, basestring):
            try:
                resampling = RESAMPLING_METHODS[resampling]
            except KeyError:
                raise UnknownResamplingMethodError(resampling)
        elif resampling not in list(RESAMPLING_METHODS.values()):
            raise UnknownResamplingMethodError(resampling)
        warp_cmd.extend(['-r', resampling])

    # Propagate No Data Value
    nodata_values = [dataset.GetRasterBand(i).GetNoDataValue()
                     for i in range(1, dataset.RasterCount + 1)]
    if any(nodata_values):
        nodata_values = [str(v).lower() for v in nodata_values]
        warp_cmd.extend(['-dstnodata', ' '.join(nodata_values)])

    # Call gdalwarp
    warp_cmd.extend([inputfile, '/vsistdout'])

    try:
        return VRT(check_output_gdal([str(e) for e in warp_cmd]))
    except CalledGdalError as e:
        if e.error == ("ERROR 6: Read or update mode not supported on /vsistdout"):
            return VRT(e.output)
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

class Band(gdal.Band):
    """
    Wrapper class for gdal.Band

    band: gdal.Band object retrieved from gdal.Dataset
    dataset: gdal.Dataset object that is the parent of `band`
    """

    def __init__(self, band, dataset):
        # Since this is a SWIG object, clone the ``this`` pointer
        self.this = band.this
        # gdal.Dataset deletes all of its data structures when it is deleted.
        self._dataset = dataset

    def GetMetadataItem(self, name, domain=''):
        """Wrapper around gdal.Band.GetMetadataItem()"""
        if not isinstance(name, str):
            name = str(name)
        if not isinstance(domain, str):
            domain = str(domain)
        return super(Band, self).GetMetadataItem(name, domain)

    def GetNoDataValue(self):
        """Returns gdal.Band.GetNoDataValue() as a NumPy type"""
        result = super(Band, self).GetNoDataValue()
        if result is not None:
            return self.NumPyDataType(result)

    @property
    def NumPyDataType(self):
        """Returns the NumPy type associated with gdal.Band.DataType"""
        datatype = self.DataType
        if datatype == gdalconst.GDT_Byte:
            pixeltype = self.GetMetadataItem('PIXELTYPE', 'IMAGE_STRUCTURE')
            if pixeltype == 'SIGNEDBYTE':
                return numpy.int8
            return numpy.uint8
        elif datatype == gdalconst.GDT_UInt16:
            return numpy.uint16
        elif datatype == gdalconst.GDT_UInt32:
            return numpy.uint32
        elif datatype == gdalconst.GDT_Int16:
            return numpy.int16
        elif datatype == gdalconst.GDT_Int32:
            return numpy.int32
        elif datatype == gdalconst.GDT_Float32:
            return numpy.float32
        elif datatype == gdalconst.GDT_Float64:
            return numpy.float64
        else:
            raise ValueError(
                "Cannot handle DataType: {0}".format(
                    gdal.GetDataTypeName(datatype)
                )
            )

    @property
    def MinimumValue(self):
        """Returns the minimum value that can be stored in this band"""
        datatype = self.NumPyDataType
        if issubclass(datatype, numpy.integer):
            return numpy.iinfo(datatype).min
        elif issubclass(datatype, numpy.floating):
            return -numpy.inf
        else:
            raise TypeError("Cannot handle DataType: {0}".format(datatype))

    @property
    def MaximumValue(self):
        """Returns the minimum value that can be stored in this band"""
        datatype = self.NumPyDataType
        if issubclass(datatype, numpy.integer):
            return numpy.iinfo(datatype).max
        elif issubclass(datatype, numpy.floating):
            return numpy.inf
        else:
            raise TypeError("Cannot handle DataType: {0}".format(datatype))

    def IncrementValue(self, value):
        """Returns the next `value` expressible in this band"""
        datatype = self.NumPyDataType
        if issubclass(datatype, numpy.integer):
            if not isinstance(value, (int, numpy.integer)):
                raise TypeError(
                    'value {0!r} must be compatible with {1}'.format(
                        value, datatype.__name__
                    )
                )
            iinfo = numpy.iinfo(datatype)
            minint, maxint = iinfo.min, iinfo.max
            if not minint <= value <= maxint:
                raise ValueError(
                    'value {0!r} must be between {1} and {2}'.format(
                        value, minint, maxint
                    )
                )
            if value == maxint:
                return maxint
            return value + 1

        elif issubclass(datatype, numpy.floating):
            if not isinstance(value, (int, numpy.integer,
                                      float, numpy.floating)):
                raise TypeError(
                    "value {0!r} must be compatible with {1}".format(
                        value, datatype.__name__
                    )
                )
            if value == numpy.finfo(datatype).max:
                return numpy.inf
            return numpy.nextafter(datatype(value), datatype(numpy.inf))

        else:
            raise TypeError("Cannot handle DataType: {0}".format(datatype))


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
        if not isinstance(inputfile, bytes):
            inputfile = inputfile.encode('utf-8')
        try:
            # Since this is a SWIG object, clone the ``this`` pointer
            self.this = gdal.Open(inputfile, mode).this
        except RuntimeError as e:
            raise GdalError(str(e))

        # Shadow for metadata so we can overwrite it without saving
        # it to the original file.
        self._geotransform = None
        self._rastersizes = None

    def IsWholeWorld(self, resolution=None):
        """
        Returns whether the dataset covers the whole world or not.
        """
        if resolution is None:
            resolution = self.GetNativeResolution()

        spatial_ref = self.GetSpatialReference()
        world_extents = spatial_ref.GetWorldExtents()
        extents = self.GetExtents()
        ll_offset = world_extents.lower_left - extents.lower_left
        ur_offset = world_extents.upper_right - extents.upper_right

        pixel_sizes = spatial_ref.GetPixelDimensions(resolution=resolution)
        return (abs(ll_offset.x) <= pixel_sizes.x and
                abs(ll_offset.y) <= pixel_sizes.y and
                abs(ur_offset.x) <= pixel_sizes.x and
                abs(ur_offset.y) <= pixel_sizes.y)

    def GetRasterBand(self, i):
        return Band(band=super(Dataset, self).GetRasterBand(i),
                    dataset=self)

    def GetSpatialReference(self):
        try:
            sr = SpatialReference(self.GetProjection())
            sr.AutoIdentifyEPSG()
            return sr
        except RuntimeError as re:
            if 'Unsupported SRS' in str(re):
                # Equivalent to EPSG:3857
                web_mercator = SpatialReference.FromEPSG(EPSG_WEB_MERCATOR)
                sr = sr.FromEPSG(sr.GetEPSGCode())
                if web_mercator.IsSame(sr):
                    return web_mercator
            raise GdalError(str(re))

    def GetCoordinateTransformation(self, dst_ref):
        return CoordinateTransformation(src_ref=self.GetSpatialReference(),
                                        dst_ref=dst_ref)

    def GetGeoTransform(self):
        if self._geotransform is not None:
            return self._geotransform
        return super(Dataset, self).GetGeoTransform()

    def SetGeoTransform(self, geotransform, local=False):
        self._geotransform = geotransform
        if local is False:
            # Write to the file only if we want/can.
            super(Dataset, self).SetGeoTransform(geotransform)

    def GetNativeResolution(self, transform=None, maximum=None):
        """
        of the source data; this usually means upsampling the data, but if the
        pixel dimensions are slightly smaller than a given resolution, and
        equal within error tolerance, that resolution will get chosen as the
        native one.
        """
        # Get the source projection's units for a 1x1 pixel, assuming square
        # pixels.
        width, height = self.GetPixelDimensions()
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
        # dst_pixel_size based on the major circumference so that the error is
        # in the destination units
        error = max(*dst_ref.GetPixelDimensions(resolution=0)) / 128

        # Find the resolution where the pixels are smaller than dst_pixel_size.
        for resolution in count():
            if maximum is not None and resolution >= maximum:
                return resolution

            res_pixel_size = max(
                *dst_ref.GetPixelDimensions(resolution=resolution)
            )
            if (res_pixel_size - dst_pixel_size) <= error:
                return resolution

            # Halve error each resolution
            error /= 2

    def GetPixelDimensions(self):
        """Returns the (width, height) of pixels in this Dataset's units."""
        _, width, _, _, _, height = self.GetGeoTransform()
        return XY(x=width, y=height)

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
        x_values, y_values = list(zip(upper_left, upper_right,
                                 lower_left, lower_right))

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
        pixel_width, pixel_height = spatial_ref.GetPixelDimensions(
            resolution=resolution
        )

        # Project the extents to the destination projection.
        extents = self.GetExtents(transform=transform)

        # Correct for origin, because you can't do modular arithmetic on
        # half-tiles.
        left, bottom = spatial_ref.OffsetPoint(*extents.lower_left)
        right, top = spatial_ref.OffsetPoint(*extents.upper_right)

        # Compute the extents aligned to the above tiles.
        offset = left % tile_width
        if offset <= (tile_width - pixel_width):
            left -= offset
        else:
            left += tile_width - offset

        offset = -right % tile_width
        if offset <= (tile_width - pixel_width):
            right += offset
        else:
            right -= tile_width - offset

        offset = bottom % tile_height
        if offset <= (tile_height - pixel_height):
            bottom -= offset
        else:
            bottom += tile_width - offset

        offset = -top % tile_height
        if offset <= (tile_height - pixel_height):
            top += offset
        else:
            top -= tile_width - offset

        # Undo the correction.
        left, bottom = spatial_ref.OffsetPoint(left, bottom, reverse=True)
        right, top = spatial_ref.OffsetPoint(right, top, reverse=True)

        # Ensure that the extents within the boundaries of the destination
        # projection.
        world_extents = spatial_ref.GetWorldExtents()
        left = max(left, world_extents.lower_left.x)
        bottom = max(bottom, world_extents.lower_left.y)
        right = min(right, world_extents.upper_right.x)
        top = min(top, world_extents.upper_right.y)

        return Extents(lower_left=XY(left, bottom),
                       upper_right=XY(right, top))

    def GetScalingRatios(self, resolution=None, places=None):
        """
        Get the scaling ratios required to upsample an image to `resolution`.

        If resolution is None, then assume it will be upsampled to the native
        destination resolution. See Dataset.GetNativeResolution()

        If places is not None, rounds the ratios to the number of decimal
        places specified.
        """
        if resolution is None:
            resolution = self.GetNativeResolution(transform=None)

        # Get the pixel dimensions in map units. There is no custom transform,
        # because it makes no sense to compute a pixel ratio for a
        # reprojection.
        spatial_ref = self.GetSpatialReference()
        dst_pixel_width, dst_pixel_height = spatial_ref.GetPixelDimensions(
            resolution=resolution
        )
        src_pixel_width, src_pixel_height = self.GetPixelDimensions()

        xscale = abs(src_pixel_width / dst_pixel_width)
        yscale = abs(src_pixel_height / dst_pixel_height)

        if places is not None:
            xscale = round(xscale, places)
            yscale = round(yscale, places)

        return XY(x=xscale, y=yscale)

    def GetTmsExtents(self, resolution=None, transform=None):
        """
        Returns (lower-left, upper-right) TMS tile coordinates.

        The upper-right coordinates are excluded from the range, while the
        lower-left are included.
        """
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

        # Validate that the native resolution extents are tile-aligned.
        extents = self.GetTiledExtents(transform=transform)
        pixel_sizes = spatial_ref.GetPixelDimensions(resolution=resolution)
        if not extents.almost_equal(self.GetExtents(transform=transform),
                                    delta=min(*pixel_sizes)):
            raise UnalignedInputError('Dataset is not aligned to TMS grid')

        # Correct for origin, because you can't do modular arithmetic on
        # half-tiles.
        left, bottom = spatial_ref.OffsetPoint(*extents.lower_left)
        right, top = spatial_ref.OffsetPoint(*extents.upper_right)

        # Divide by number of tiles
        return Extents(lower_left=XY(int(floor(left / tile_width)),
                                     int(floor(bottom / tile_height))),
                       upper_right=XY(int(ceil(right / tile_width)),
                                      int(ceil(top / tile_height))))

    def GetWorldScalingRatios(self, resolution=None, places=None):
        """
        Get the scaling ratios required to upsample for the whole world.

        If resolution is None, then assume it will be upsampled to the native
        destination resolution. See Dataset.GetNativeResolution()

        If places is not None, rounds the ratios to the number of decimal
        places specified.
        """
        if resolution is None:
            resolution = self.GetNativeResolution()

        spatial_ref = self.GetSpatialReference()
        world = spatial_ref.GetWorldExtents().dimensions
        src_pixel_sizes = XY(x=world.x / self.RasterXSize,
                             y=world.y / self.RasterYSize)
        dst_pixel_sizes = spatial_ref.GetPixelDimensions(resolution=resolution)

        xscale = abs(src_pixel_sizes.x / dst_pixel_sizes.x)

        # Make sure that yscale fits within the whole world
        yscale = min(xscale, abs(src_pixel_sizes.y / dst_pixel_sizes.y))

        if places is not None:
            xscale = round(xscale, places)
            yscale = round(yscale, places)

        return XY(x=xscale, y=yscale)

    def GetWorldTmsExtents(self, resolution=None, transform=None):
        if resolution is None:
            resolution = self.GetNativeResolution()

        if transform is None:
            spatial_ref = self.GetSpatialReference()
        else:
            spatial_ref = transform.dst_ref

        world_tiles = spatial_ref.GetTilesCount(
            extents=spatial_ref.GetWorldExtents(),
            resolution=resolution
        )
        return Extents(lower_left=XY(0, 0),
                       upper_right=world_tiles)

    def GetWorldTmsBorders(self, resolution=None, transform=None):
        """Returns an iterable of TMS tiles that are outside this Dataset."""
        world_extents = self.GetWorldTmsExtents(resolution=resolution,
                                                transform=transform)
        data_extents = self.GetTmsExtents(resolution=resolution,
                                          transform=transform)
        return (XY(x, y)
                for x in range(world_extents.lower_left.x,
                                world_extents.upper_right.x)
                for y in range(world_extents.lower_left.y,
                                world_extents.upper_right.y)
                if XY(x, y) not in data_extents)

    @property
    def RasterXSize(self):
        if self._rastersizes is not None:
            return self._rastersizes.x
        return super(Dataset, self).RasterXSize

    @property
    def RasterYSize(self):
        if self._rastersizes is not None:
            return self._rastersizes.y
        return super(Dataset, self).RasterYSize

    def SetLocalSizes(self, xsize, ysize):
        # Write to the local shadow, because we can't edit XSize and YSize
        self._rastersizes = XY(x=xsize, y=ysize)


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

    def __ne__(self, other):
        return not self.__eq__(other)

    def GetEPSGCode(self):
        epsg_string = self.GetEPSGString()
        if epsg_string:
            return int(epsg_string.split(':')[1])
        else:
            # HACK: The following is to cope with the fact that the Wkt
            #       representation of the Web Mercator is different for
            #       ESRI's WKID 102100 and EPSG's 3857 while both are
            #       equivalent. Yet, Proj4 does not understand ESRI's
            #       'mercator_auxiliary_sphere' projection name.
            projcs_name = self.GetAttrValue(str('PROJCS'))
            # Returning equivalent EPSG code
            if projcs_name == ESRI_102100_PROJ:
                return 3857
            elif projcs_name == ESRI_102113_PROJ:
                return 3785

    def GetEPSGString(self):
        if self.IsLocal() == 1:
            return

        if self.IsGeographic() == 1:
            cstype = 'GEOGCS'
        else:
            cstype = 'PROJCS'

        if not isinstance(cstype, str):
            cstype = str(cstype)

        authority_name = self.GetAuthorityName(cstype)
        authority_code = self.GetAuthorityCode(cstype)

        if authority_name and authority_code:
            return '{0}:{1}'.format(authority_name, authority_code)
        else:
            return None

    def GetMajorCircumference(self):
        if self.IsProjected() == 0:
            return 2 * pi / self.GetAngularUnits()
        return self.GetSemiMajor() * 2 * pi / self.GetLinearUnits()

    def GetMinorCircumference(self):
        if self.IsProjected() == 0:
            return 2 * pi / self.GetAngularUnits()

        semi_minor = self.GetSemiMinor() * 2 * pi / self.GetLinearUnits()
        if self.GetEPSGCode() == 3857:
            # Cancel the flattening of the spheroid.
            # This is to account for the web mercator projection of points on
            # a spheroid but interpretation of said points on a sphere.
            return semi_minor / (1 - 1 / self.GetInvFlattening())
        return semi_minor

    def GetWorldExtents(self):
        major = self.GetMajorCircumference() / 2
        minor = self.GetMinorCircumference() / 2
        if self.IsProjected() == 0:
            minor /= 2
        return Extents(lower_left=XY(-major, -minor),
                       upper_right=XY(major, minor))

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
        return self.GetTileDimensions(resolution=resolution) / TILE_SIDE

    def GetTileDimensions(self, resolution):
        # Assume square tiles.
        width = self.GetMajorCircumference() / 2 ** resolution
        height = self.GetMinorCircumference() / 2 ** resolution
        result = XY(width, height)
        if self.IsProjected() == 0:
            # Resolution 0 only covers a longitudinal hemisphere
            result /= 2
        return result

    def GetTilesCount(self, extents, resolution):
        width, height = extents.dimensions
        tile_width, tile_height = self.GetTileDimensions(resolution=resolution)

        return XY(int(round(width / tile_width)),
                  int(round(height / tile_height)))


class VRT(object):
    def __init__(self, content):
        self.content = content

    def __str__(self):
        return self.content.decode('utf-8')

    def get_root(self):
        return ElementTree.fromstring(self.content)

    def get_tempfile(self, **kwargs):
        kwargs.setdefault('suffix', '.vrt')
        tempfile = NamedTemporaryFile(**kwargs)
        tempfile.write(self.content)
        tempfile.flush()
        tempfile.seek(0)
        return tempfile

    def render(self, outputfile, cmd=GDALTRANSLATE, working_memory=512,
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
                    '-co', 'BIGTIFF=IF_SAFER',  # Use BigTIFF if >2GB
                    # gdal_translate does not support the following
                    # '-multi',               # Use multiple processes
                    # '-overwrite',           # Overwrite outputfile
                    # '-wo', 'NUM_THREADS=ALL_CPUS',  # Use all CPUs
                ]

                # Set the working memory so that gdalwarp doesn't stall of disk
                # I/O
                warp_cmd.extend([
                    # gdal_translate does not support -wm
                    # '-wm', working_memory,
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
                return outputfile
        finally:
            rmfile(tmpfile.name, ignore_missing=True)
            rmfile(tmpfile.name + '.aux.xml', ignore_missing=True)
