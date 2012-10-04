# -*- coding: utf-8 -*-

from math import log
import os
import subprocess
from tempfile import NamedTemporaryFile
import unittest
from xml.etree import ElementTree

from osgeo import osr
from osgeo.gdalconst import GRA_Cubic

from gdal2mbtiles.constants import EPSG_WEB_MERCATOR, GDALINFO, TILE_SIDE
from gdal2mbtiles.exceptions import (GdalError, CalledGdalError,
                                     UnknownResamplingMethodError, VrtError)
from gdal2mbtiles.gdal import (Dataset, colourize, expand_colour_bands, warp,
                               preprocess, render_vrt, SpatialReference)
from gdal2mbtiles.types import rgba, XY


__dir__ = os.path.dirname(__file__)


class TestCase(unittest.TestCase):
    def assertExtentsEqual(self, first, second):
        # Assume that the extents are in the same projection
        first_ll, first_ur = first
        second_ll, second_ur = second

        # 1 cm precision
        self.assertAlmostEqual(first_ll.x, second_ll.x, places=2)
        self.assertAlmostEqual(first_ll.y, second_ll.y, places=2)
        self.assertAlmostEqual(first_ur.x, second_ur.x, places=2)
        self.assertAlmostEqual(first_ur.y, second_ur.y, places=2)


class TestColourize(unittest.TestCase):
    def setUp(self):
        self.inputfile = os.path.join(__dir__,
                                      'srtm.tif')

    def test_simple(self):
        vrt = colourize(inputfile=self.inputfile,
                        colours=[(0, rgba(0, 0, 0, 255)),
                                 (1, rgba(255, 255, 255, 255))])
        root = ElementTree.fromstring(vrt)
        self.assertEqual(root.tag, 'VRTDataset')
        color_table = root.find('VRTRasterBand').find('ColorTable')
        self.assertEqual(
            ElementTree.tostring(color_table),
            ('<ColorTable>'
             '<Entry c1="0" c2="0" c3="0" c4="255" />'
             '<Entry c1="255" c2="255" c3="255" c4="255" />'
             '</ColorTable>')
        )
        lut = root.find('VRTRasterBand').find('ComplexSource').find('LUT')
        self.assertEqual(lut.text,
                         '0:0,\n1:1')

    def test_invalid(self):
        self.assertRaises(GdalError,
                          colourize,
                          inputfile='/dev/null',
                          colours=[(0, rgba(0, 0, 0, 255)),
                                   (1, rgba(255, 255, 255, 255))])

    def test_missing_band(self):
        self.assertRaises(VrtError,
                          colourize,
                          inputfile=self.inputfile,
                          colours=[(0, rgba(0, 0, 0, 255)),
                                   (1, rgba(255, 255, 255, 255))],
                          band=2)

    def test_invalid_colours(self):
        self.assertRaises(AttributeError,
                          colourize,
                          inputfile=self.inputfile,
                          colours=[(0, 'red'),
                                   (1, 'green')])
        self.assertRaises(TypeError,
                          colourize,
                          inputfile=self.inputfile,
                          colours=None)


class TestExpandColourBands(unittest.TestCase):
    def setUp(self):
        self.inputfile = os.path.join(__dir__,
                                      'srtm.tif')

    def test_simple(self):
        with NamedTemporaryFile(suffix='.vrt') as paletted:
            paletted.write(colourize(inputfile=self.inputfile,
                                     colours=[(0, rgba(0, 0, 0, 255)),
                                              (1, rgba(255, 255, 255, 255))]))
            paletted.flush()
            vrt = expand_colour_bands(inputfile=paletted.name)
            root = ElementTree.fromstring(vrt)
            # There are four colours, RGBA.
            self.assertEqual(len(root.findall('.//VRTRasterBand')), 4)

    def test_no_colour_table(self):
        # srtm.tif has no colour table
        self.assertRaises(CalledGdalError,
                          expand_colour_bands, inputfile=self.inputfile)

    def test_invalid(self):
        self.assertRaises(GdalError,
                          expand_colour_bands,
                          inputfile='/dev/null')


class TestWarp(unittest.TestCase):
    def setUp(self):
        self.inputfile = os.path.join(__dir__,
                                      'bluemarble.tif')

    def test_simple(self):
        root = ElementTree.fromstring(warp(self.inputfile))
        self.assertEqual(root.tag, 'VRTDataset')
        self.assertTrue(all(t.text == self.inputfile
                            for t in root.findall('.//SourceDataset')))

    def test_resampling(self):
        # Cubic
        root = ElementTree.fromstring(warp(self.inputfile,
                                           resampling=GRA_Cubic))
        self.assertEqual(root.tag, 'VRTDataset')
        self.assertTrue(all(t.text == 'Cubic'
                            for t in root.findall('.//ResampleAlg')))

        # Invalid
        self.assertRaises(UnknownResamplingMethodError,
                          warp, self.inputfile, resampling=-1)

    def test_spatial_ref(self):
        root = ElementTree.fromstring(warp(self.inputfile))
        self.assertTrue('"EPSG","3785"' in root.find('.//TargetSRS').text)

        root = ElementTree.fromstring(
            warp(self.inputfile,
                 spatial_ref=SpatialReference.FromEPSG(4326))
        )
        self.assertTrue('WGS 84' in root.find('.//TargetSRS').text)

    def skiptest_maximum_resolution_partial(self):
        self.fail('This test needs to work on partial datasets, where changing '
                  'the resolution will change the extents')

    def test_invalid(self):
        self.assertRaises(GdalError, warp, '/dev/null')

    def test_missing(self):
        self.assertRaises(IOError,
                          warp, os.path.join(__dir__, 'missing.tif'))


class TestPreprocess(unittest.TestCase):
    def setUp(self):
        self.inputfile = os.path.join(__dir__,
                                      'srtm.tif')

    def test_simple(self):
        with NamedTemporaryFile(suffix='.tif') as outputfile:
            preprocess(inputfile=self.inputfile, outputfile=outputfile.name,
                       colours=[(0, rgba(0, 0, 0, 255)),
                                (1, rgba(255, 255, 255, 255))])
            self.assertTrue(os.path.exists(outputfile.name))
            self.assertTrue(os.stat(outputfile.name).st_size > 0)


class TestRenderVrt(TestCase):
    def setUp(self):
        self.inputfile = os.path.join(__dir__,
                                      'bluemarble.tif')

    def test_world(self):
        with NamedTemporaryFile(suffix='.vrt') as warpfile, \
             NamedTemporaryFile(suffix='.tif') as tmpfile:
            warpfile.write(warp(self.inputfile))
            warpfile.flush()
            outputfile = tmpfile.name
            render_vrt(inputfile=warpfile.name, outputfile=outputfile,
                       compress='LZW')
            self.assertEqual(
                subprocess.call([GDALINFO, outputfile],
                                stdout=open('/dev/null', 'w+')),
                0
            )

            # Test that the metadata hasn't been munged by warp()
            in_data = Dataset(self.inputfile)
            out_data = Dataset(outputfile)
            self.assertExtentsEqual(in_data.GetExtents(),
                                    out_data.GetExtents())
            self.assertEqual(in_data.RasterXSize, out_data.RasterXSize)
            self.assertEqual(in_data.RasterYSize, out_data.RasterYSize)

    def test_aligned_partial(self):
        inputfile = os.path.join(__dir__, 'bluemarble-aligned-ll.tif')
        with NamedTemporaryFile(suffix='.vrt') as warpfile, \
             NamedTemporaryFile(suffix='.tif') as tmpfile:
            warpfile.write(warp(inputfile))
            warpfile.flush()
            outputfile = tmpfile.name
            render_vrt(inputfile=warpfile.name, outputfile=outputfile,
                       compress='LZW')
            self.assertEqual(
                subprocess.call([GDALINFO, outputfile],
                                stdout=open('/dev/null', 'w+')),
                0
            )

            # Test that the metadata hasn't been munged by warp()
            in_data = Dataset(inputfile)
            out_data = Dataset(outputfile)
            self.assertExtentsEqual(in_data.GetExtents(),
                                    out_data.GetExtents())
            self.assertEqual(in_data.RasterXSize, out_data.RasterXSize)
            self.assertEqual(in_data.RasterYSize, out_data.RasterYSize)

    def test_invalid_input(self):
        with NamedTemporaryFile(suffix='.tif') as tmpfile:
            self.assertRaises(CalledGdalError,
                              render_vrt, inputfile='/dev/null',
                              outputfile=tmpfile.name)

    def test_invalid_output(self):
        with NamedTemporaryFile(suffix='.vrt') as inputfile:
            inputfile.write(warp(self.inputfile))
            inputfile.flush()
            self.assertRaises(OSError,
                              render_vrt, inputfile=inputfile,
                              outputfile='/dev/invalid')


class TestDataset(unittest.TestCase):
    def setUp(self):
        # Whole world: (180°W, 85°S), (180°E, 85°N)
        self.inputfile = os.path.join(__dir__,
                                      'bluemarble.tif')

        # Aligned partial: (90°W, 42.5°S), (0°E, 0°N)
        self.alignedfile = os.path.join(__dir__,
                                        'bluemarble-aligned-ll.tif')

        # Unaligned (spanning) partial: (162.4°W, 76.7°S), (17.6°W, 8.3°S)
        self.spanningfile = os.path.join(__dir__,
                                         'bluemarble-spanning-ll.tif')

    def test_open(self):
        from osgeo.gdalconst import GA_Update

        # Valid
        self.assertTrue(Dataset(inputfile=self.inputfile))
        self.assertTrue(Dataset(inputfile=self.inputfile, mode=GA_Update))

        # Invalid
        self.assertRaises(GdalError, Dataset, inputfile='/dev/null')

        # Missing
        self.assertRaises(IOError, Dataset, inputfile='/dev/missing')

    def test_raster_size(self):
        dataset = Dataset(inputfile=self.inputfile)

        # bluemarble.tif is a 1024×1024 image
        self.assertEqual(dataset.RasterXSize, 1024)
        self.assertEqual(dataset.RasterYSize, 1024)

    def test_get_spatial_reference(self):
        self.assertEqual(
            Dataset(inputfile=self.inputfile).GetSpatialReference(),
            SpatialReference.FromEPSG(EPSG_WEB_MERCATOR)
        )

    def test_get_coordinate_transformation(self):
        dataset = Dataset(inputfile=self.inputfile)
        wgs84 = SpatialReference(osr.SRS_WKT_WGS84)
        transform = dataset.GetCoordinateTransformation(dst_ref=wgs84)
        self.assertEqual(transform.src_ref,
                         dataset.GetSpatialReference())
        self.assertEqual(transform.dst_ref,
                         wgs84)

    def test_get_native_resolution(self):
        dataset = Dataset(inputfile=self.inputfile)

        # bluemarble.tif is a 1024×1024 image of the whole world
        self.assertEqual(dataset.GetNativeResolution(),
                         2)

        # Maximum
        self.assertEqual(dataset.GetNativeResolution(maximum=1),
                         1)
        self.assertEqual(dataset.GetNativeResolution(maximum=10),
                         2)

        # Transform into US survey feet
        sr = SpatialReference.FromEPSG(EPSG_WEB_MERCATOR)
        sr.ImportFromWkt(sr.ExportToWkt().replace(
            'UNIT["metre",1,AUTHORITY["EPSG","9001"]]',
            'UNIT["US survey foot",0.3048006096012192,AUTHORITY["EPSG","9003"]]'
        ))
        transform = dataset.GetCoordinateTransformation(dst_ref=sr)
        self.assertEqual(dataset.GetNativeResolution(transform=transform),
                         2 + int(round(log(3.28, 2))))  # 3.28 ft/m

    def test_pixel_coordinates(self):
        dataset = Dataset(inputfile=self.inputfile)
        spatial_ref = dataset.GetSpatialReference()

        # Upper-left corner
        coords = dataset.PixelCoordinates(0, 0)
        self.assertAlmostEqual(coords.x,
                               -spatial_ref.GetMajorCircumference() / 2,
                               places=2)
        self.assertAlmostEqual(coords.y,
                               spatial_ref.GetMinorCircumference() / 2,
                               places=2)

        # Bottom-right corner
        coords = dataset.PixelCoordinates(dataset.RasterXSize,
                                          dataset.RasterYSize)
        self.assertAlmostEqual(coords.x,
                               spatial_ref.GetMajorCircumference() / 2,
                               places=2)
        self.assertAlmostEqual(coords.y,
                               -spatial_ref.GetMinorCircumference() / 2,
                               places=2)

        # Out of bounds
        self.assertRaises(ValueError,
                          dataset.PixelCoordinates, -1, 0)
        self.assertRaises(ValueError,
                          dataset.PixelCoordinates,
                          dataset.RasterXSize, dataset.RasterYSize + 1)

    def test_pixel_coordinates_partial(self):
        dataset = Dataset(inputfile=self.alignedfile)
        spatial_ref = dataset.GetSpatialReference()

        # Upper-left corner
        coords = dataset.PixelCoordinates(0, 0)
        self.assertAlmostEqual(coords.x,
                               -spatial_ref.GetMajorCircumference() / 4,
                               places=2)
        self.assertAlmostEqual(coords.y,
                               0.0,
                               places=2)

        # Bottom-right corner
        coords = dataset.PixelCoordinates(dataset.RasterXSize,
                                          dataset.RasterYSize)
        self.assertAlmostEqual(coords.x,
                               0.0,
                               places=2)
        self.assertAlmostEqual(coords.y,
                               -spatial_ref.GetMinorCircumference() / 4,
                               places=2)

        # Out of bounds
        self.assertRaises(ValueError,
                          dataset.PixelCoordinates, -1, 0)
        self.assertRaises(ValueError,
                          dataset.PixelCoordinates,
                          dataset.RasterXSize, dataset.RasterYSize + 1)

    def test_get_extents(self):
        dataset = Dataset(inputfile=self.inputfile)
        mercator = dataset.GetSpatialReference()
        major_half_circumference = mercator.GetMajorCircumference() / 2
        minor_half_circumference = mercator.GetMinorCircumference() / 2

        ll, ur = dataset.GetExtents()
        self.assertAlmostEqual(ll.x, -major_half_circumference, places=0)
        self.assertAlmostEqual(ll.y, -minor_half_circumference, places=0)
        self.assertAlmostEqual(ur.x, major_half_circumference, places=0)
        self.assertAlmostEqual(ur.y, minor_half_circumference, places=0)

    def test_get_extents_wgs84(self):
        dataset = Dataset(inputfile=self.inputfile)
        transform = dataset.GetCoordinateTransformation(
            dst_ref=SpatialReference(osr.SRS_WKT_WGS84)
        )
        ll, ur = dataset.GetExtents(transform=transform)
        self.assertAlmostEqual(ll.x, -180.0, places=0)
        self.assertAlmostEqual(ll.y, -85.0, places=0)
        self.assertAlmostEqual(ur.x, 180.0, places=0)
        self.assertAlmostEqual(ur.y, 85.0, places=0)

    def test_get_extents_mercator(self):
        mercator = SpatialReference.FromEPSG(EPSG_WEB_MERCATOR)
        major_half_circumference = mercator.GetMajorCircumference() / 2
        minor_half_circumference = mercator.GetMinorCircumference() / 2

        dataset = Dataset(inputfile=self.inputfile)
        transform = dataset.GetCoordinateTransformation(dst_ref=mercator)
        ll, ur = dataset.GetExtents(transform=transform)
        self.assertAlmostEqual(ll.x, -major_half_circumference, places=0)
        self.assertAlmostEqual(ll.y, -minor_half_circumference, places=0)
        self.assertAlmostEqual(ur.x, major_half_circumference, places=0)
        self.assertAlmostEqual(ur.y, minor_half_circumference, places=0)

    def test_get_extents_partial_aligned(self):
        dataset = Dataset(inputfile=self.alignedfile)
        mercator = dataset.GetSpatialReference()
        major_circumference = mercator.GetMajorCircumference()
        minor_circumference = mercator.GetMinorCircumference()

        ll, ur = dataset.GetExtents()
        self.assertAlmostEqual(ll.x, -major_circumference / 4, places=0)
        self.assertAlmostEqual(ll.y, -minor_circumference / 4, places=0)
        self.assertAlmostEqual(ur.x, 0.0, places=0)
        self.assertAlmostEqual(ur.y, 0.0, places=0)

    def test_get_extents_partial_spanning(self):
        dataset = Dataset(inputfile=self.spanningfile)
        mercator = dataset.GetSpatialReference()
        major_half_circumference = mercator.GetMajorCircumference() / 2
        minor_half_circumference = mercator.GetMinorCircumference() / 2

        # Spanning file is 50 pixels in from alignment
        pixel_size = mercator.GetPixelDimensions(
            resolution=dataset.GetNativeResolution()
        )
        border = 50 * pixel_size.x

        ll, ur = dataset.GetExtents()
        self.assertAlmostEqual(ll.x,
                               -major_half_circumference + border,
                               places=0)
        self.assertAlmostEqual(ll.y,
                               -minor_half_circumference + border,
                               places=0)
        self.assertAlmostEqual(ur.x,
                               0.0 - border,
                               places=0)
        self.assertAlmostEqual(ur.y, 0.0 - border,
                               places=0)

    def test_get_extents_partial_wgs84(self):
        dataset = Dataset(inputfile=self.alignedfile)
        transform = dataset.GetCoordinateTransformation(
            dst_ref=SpatialReference(osr.SRS_WKT_WGS84)
        )
        ll, ur = dataset.GetExtents(transform=transform)
        # 66.5°S is due to the fact that the original file is in Mercator and
        # the southern latitudes take up more pixels in Mercator than in WGS 84.
        self.assertAlmostEqual(ll.x, -90.0, places=0)
        self.assertAlmostEqual(ll.y, -66.5, places=0)
        self.assertAlmostEqual(ur.x, 0.0, places=0)
        self.assertAlmostEqual(ur.y, 0.0, places=0)

    def test_get_extents_partial_mercator(self):
        mercator = SpatialReference.FromEPSG(EPSG_WEB_MERCATOR)
        major_circumference = mercator.GetMajorCircumference()
        minor_circumference = mercator.GetMinorCircumference()

        dataset = Dataset(inputfile=self.alignedfile)
        ll, ur = dataset.GetExtents()
        self.assertAlmostEqual(ll.x, -major_circumference / 4, places=0)
        self.assertAlmostEqual(ll.y, -minor_circumference / 4, places=0)
        self.assertAlmostEqual(ur.x, 0, places=0)
        self.assertAlmostEqual(ur.y, 0, places=0)

    def test_get_tiled_extents(self):
        dataset = Dataset(inputfile=self.inputfile)

        mercator = SpatialReference.FromEPSG(EPSG_WEB_MERCATOR)
        major_half_circumference = mercator.GetMajorCircumference() / 2
        minor_half_circumference = mercator.GetMinorCircumference() / 2

        # Native resolution, source projection which is Mercator, already
        # aligned.
        ll, ur = dataset.GetTiledExtents()
        self.assertAlmostEqual(ll.x, -major_half_circumference, places=0)
        self.assertAlmostEqual(ll.y, -minor_half_circumference, places=0)
        self.assertAlmostEqual(ur.x, major_half_circumference, places=0)
        self.assertAlmostEqual(ur.y, minor_half_circumference, places=0)

        # Resolution 0, source projection which is Mercator, already
        # aligned. This is the same as above, because the dataset covers the
        # whole world.
        ll, ur = dataset.GetTiledExtents(resolution=0)
        self.assertAlmostEqual(ll.x, -major_half_circumference, places=0)
        self.assertAlmostEqual(ll.y, -minor_half_circumference, places=0)
        self.assertAlmostEqual(ur.x, major_half_circumference, places=0)
        self.assertAlmostEqual(ur.y, minor_half_circumference, places=0)

        # Native resolution, WGS 84 projection, already aligned
        ll, ur = dataset.GetTiledExtents(
            transform=dataset.GetCoordinateTransformation(
                dst_ref=SpatialReference(osr.SRS_WKT_WGS84)
            )
        )
        self.assertAlmostEqual(ll.x, -180.0, places=0)
        self.assertAlmostEqual(ll.y, -90.0, places=0)
        self.assertAlmostEqual(ur.x, 180.0, places=0)
        self.assertAlmostEqual(ur.y, 90.0, places=0)

        # Resolution 0, WGS 84 projection, already aligned. This is the
        # same as above, because the dataset covers the whole world.
        ll, ur = dataset.GetTiledExtents(
            transform=dataset.GetCoordinateTransformation(
                dst_ref=SpatialReference(osr.SRS_WKT_WGS84)
            ),
            resolution=0
        )
        self.assertAlmostEqual(ll.x, -180.0, places=0)
        self.assertAlmostEqual(ll.y, -90.0, places=0)
        self.assertAlmostEqual(ur.x, 180.0, places=0)
        self.assertAlmostEqual(ur.y, 90.0, places=0)

    def test_get_tiled_extents_partial_aligned(self):
        dataset = Dataset(inputfile=self.alignedfile)

        mercator = SpatialReference.FromEPSG(EPSG_WEB_MERCATOR)
        major_circumference = mercator.GetMajorCircumference()
        minor_circumference = mercator.GetMinorCircumference()

        # Native resolution, source projection which is Mercator, already
        # aligned.
        ll, ur = dataset.GetTiledExtents()
        self.assertAlmostEqual(ll.x, -major_circumference / 4, places=0)
        self.assertAlmostEqual(ll.y, -minor_circumference / 4, places=0)
        self.assertAlmostEqual(ur.x, 0, places=0)
        self.assertAlmostEqual(ur.y, 0, places=0)

        # Resolution 1, source projection which is Mercator, already
        # aligned. This should be the south-western quadrant, because the tile
        # is the north-eastern section of that quadrant.
        ll, ur = dataset.GetTiledExtents(resolution=1)
        self.assertAlmostEqual(ll.x, -major_circumference / 2, places=0)
        self.assertAlmostEqual(ll.y, -minor_circumference / 2, places=0)
        self.assertAlmostEqual(ur.x, 0, places=0)
        self.assertAlmostEqual(ur.y, 0, places=0)

        # Native resolution, WGS 84 projection, already aligned
        ll, ur = dataset.GetTiledExtents(
            transform=dataset.GetCoordinateTransformation(
                dst_ref=SpatialReference(osr.SRS_WKT_WGS84)
            )
        )
        self.assertAlmostEqual(ll.x, -90.0, places=0)
        self.assertAlmostEqual(ll.y, -90.0, places=0)
        self.assertAlmostEqual(ur.x, 0.0, places=0)
        self.assertAlmostEqual(ur.y, 0.0, places=0)

        # Resolution 0, WGS 84 projection, already aligned. This should be
        # the western hemisphere.
        ll, ur = dataset.GetTiledExtents(
            transform=dataset.GetCoordinateTransformation(
                dst_ref=SpatialReference(osr.SRS_WKT_WGS84)
            ),
            resolution=0
        )
        self.assertAlmostEqual(ll.x, -180.0, places=0)
        self.assertAlmostEqual(ll.y, -90.0, places=0)
        self.assertAlmostEqual(ur.x, 0.0, places=0)
        self.assertAlmostEqual(ur.y, 90.0, places=0)

    def skiptest_get_tiled_extents_partial_spanning(self):
        self.fail('Test not written yet')


class TestSpatialReference(unittest.TestCase):
    def setUp(self):
        self.wgs84 = SpatialReference(osr.SRS_WKT_WGS84)

    def test_from_epsg(self):
        self.assertEqual(SpatialReference.FromEPSG(4326), self.wgs84)

        # Web Mercator is not the same as WGS 84.
        self.assertNotEqual(SpatialReference.FromEPSG(3785), self.wgs84)

    def test_get_epsg_code(self):
        self.assertEqual(self.wgs84.GetEPSGCode(), 4326)

    def test_get_epsg_string(self):
        self.assertEqual(self.wgs84.GetEPSGString(), 'EPSG:4326')

    def test_get_major_circumerference(self):
        # Degrees
        self.assertAlmostEqual(self.wgs84.GetMajorCircumference(),
                               360.0)

        # Meters
        mercator = SpatialReference.FromEPSG(EPSG_WEB_MERCATOR)
        self.assertAlmostEqual(mercator.GetMajorCircumference(),
                               40075016.6856,
                               places=4)

    def test_get_minor_circumerference(self):
        # Degrees
        self.assertAlmostEqual(self.wgs84.GetMinorCircumference(),
                               360.0)

        # Meters
        mercator = SpatialReference.FromEPSG(EPSG_WEB_MERCATOR)
        self.assertAlmostEqual(mercator.GetMinorCircumference(),
                               40075016.6856,
                               places=4)

    def test_pixel_dimensions_wgs84(self):
        # Resolution 0 covers a longitudinal hemisphere.
        pixel_size = self.wgs84.GetPixelDimensions(resolution=0)
        self.assertAlmostEqual(pixel_size.x,
                               360.0 / TILE_SIDE / 2)
        self.assertAlmostEqual(pixel_size.y,
                               360.0 / TILE_SIDE / 2)

        # Resolution 1 should be half of the above
        pixel_size = self.wgs84.GetPixelDimensions(resolution=1)
        self.assertAlmostEqual(pixel_size.x,
                               360.0 / TILE_SIDE / 4)
        self.assertAlmostEqual(pixel_size.y,
                               360.0 / TILE_SIDE / 4)

    def test_pixel_dimensions_mercator(self):
        mercator = SpatialReference.FromEPSG(EPSG_WEB_MERCATOR)
        major_circumference = mercator.GetMajorCircumference()
        minor_circumference = mercator.GetMinorCircumference()

        # Resolution 0 covers the whole world
        pixel_size = mercator.GetPixelDimensions(resolution=0)
        self.assertAlmostEqual(pixel_size.x,
                               major_circumference / TILE_SIDE)
        self.assertAlmostEqual(pixel_size.y,
                               minor_circumference / TILE_SIDE)

        # Resolution 1 should be half of the above
        pixel_size = mercator.GetPixelDimensions(resolution=1)
        self.assertAlmostEqual(pixel_size.x,
                               major_circumference / TILE_SIDE / 2)
        self.assertAlmostEqual(pixel_size.y,
                               minor_circumference / TILE_SIDE / 2)

    def test_get_tile_dimensions_wgs84(self):
        # Resolution 0 covers a longitudinal hemisphere.
        tile_size = self.wgs84.GetTileDimensions(resolution=0)
        self.assertAlmostEqual(tile_size.x,
                               360.0 / 2)
        self.assertAlmostEqual(tile_size.y,
                               360.0 / 2)

        # Resolution 1 should be half of the above
        tile_size = self.wgs84.GetTileDimensions(resolution=1)
        self.assertAlmostEqual(tile_size.x,
                               360.0 / 4)
        self.assertAlmostEqual(tile_size.y,
                               360.0 / 4)

    def test_get_tile_dimensions_mercator(self):
        mercator = SpatialReference.FromEPSG(EPSG_WEB_MERCATOR)
        major_circumference = mercator.GetMajorCircumference()
        minor_circumference = mercator.GetMinorCircumference()

        # Resolution 0 covers the whole world
        tile_size = mercator.GetTileDimensions(resolution=0)
        self.assertAlmostEqual(tile_size.x,
                               major_circumference)
        self.assertAlmostEqual(tile_size.y,
                               minor_circumference)

        # Resolution 1 should be half of the above
        tile_size = mercator.GetTileDimensions(resolution=1)
        self.assertAlmostEqual(tile_size.x,
                               major_circumference / 2)
        self.assertAlmostEqual(tile_size.y,
                               minor_circumference / 2)

    def test_tiles_count_wgs84(self):
        world = (XY(-180, -90), XY(180, 90))

        # Resolution 0 is 2×1 for the whole world
        self.assertEqual(self.wgs84.GetTilesCount(extents=world,
                                                  resolution=0),
                         XY(2, 1))

        # Resolution 1 is 4×2 for the whole world
        self.assertEqual(self.wgs84.GetTilesCount(extents=world,
                                                  resolution=1),
                         XY(4, 2))

    def test_tiles_count_mercator(self):
        mercator = SpatialReference.FromEPSG(EPSG_WEB_MERCATOR)
        major_half_circumference = mercator.GetMajorCircumference() / 2
        minor_half_circumference = mercator.GetMinorCircumference() / 2
        world = (XY(-major_half_circumference, -minor_half_circumference),
                 XY(major_half_circumference, minor_half_circumference))

        # Resolution 0 is 1×1 for the whole world
        self.assertEqual(mercator.GetTilesCount(extents=world,
                                                resolution=0),
                         XY(1, 1))

        # Resolution 1 is 2×2 for the whole world
        self.assertEqual(mercator.GetTilesCount(extents=world,
                                                resolution=1),
                         XY(2, 2))
