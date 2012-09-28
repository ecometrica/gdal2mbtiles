import os
import subprocess
from tempfile import NamedTemporaryFile
import unittest
from xml.etree import ElementTree

from osgeo.gdalconst import GRA_Cubic

from gdal2mbtiles.constants import GDALINFO
from gdal2mbtiles.exceptions import (GdalError, GdalWarpError,
                                     UnknownResamplingMethodError)
from gdal2mbtiles.warp import generate_vrt, vrt_to_geotiff


__dir__ = os.path.dirname(__file__)


class TestGenerateVRT(unittest.TestCase):
    def setUp(self):
        self.inputfile = os.path.join(__dir__,
                                      'bluemarble.tif')

    def test_simple(self):
        root = ElementTree.fromstring(generate_vrt(self.inputfile))
        self.assertEqual(root.tag, 'VRTDataset')
        self.assertTrue(all(t.text == self.inputfile
                            for t in root.findall('.//SourceDataset')))

    def test_resampling(self):
        # Cubic
        root = ElementTree.fromstring(generate_vrt(self.inputfile,
                                                   resampling=GRA_Cubic))
        self.assertEqual(root.tag, 'VRTDataset')
        self.assertTrue(all(t.text == 'Cubic'
                            for t in root.findall('.//ResampleAlg')))

        # Invalid
        self.assertRaises(UnknownResamplingMethodError,
                          generate_vrt, self.inputfile, resampling=-1)

    def test_invalid(self):
        self.assertRaises(GdalError, generate_vrt, '/dev/null')

    def test_missing(self):
        self.assertRaises(IOError,
                          generate_vrt, os.path.join(__dir__, 'missing.tif'))


class TestVrtToGeotiff(unittest.TestCase):
    def setUp(self):
        self.inputfile = os.path.join(__dir__,
                                      'bluemarble.tif')

    def test_simple(self):
        vrt = generate_vrt(self.inputfile)
        with NamedTemporaryFile(suffix='.tif') as tmpfile:
            outputfile = tmpfile.name
            vrt_to_geotiff(vrt=vrt, outputfile=outputfile, compress='LZW')
            self.assertEqual(
                subprocess.call([GDALINFO, outputfile],
                                stdout=open('/dev/null', 'w+')),
                0
            )

    def test_invalid_input(self):
        with NamedTemporaryFile(suffix='.tif') as tmpfile:
            self.assertRaises(GdalWarpError,
                              vrt_to_geotiff, vrt='', outputfile=tmpfile.name)

    def test_invalid_output(self):
        vrt = generate_vrt(self.inputfile)
        self.assertRaises(OSError,
                          vrt_to_geotiff, vrt=vrt, outputfile='/dev/invalid')
