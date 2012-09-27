import os
import unittest
from xml.etree import ElementTree

from osgeo.gdalconst import GRA_Cubic

from gdal2mbtiles.exceptions import GdalError, UnknownResamplingMethodError
from gdal2mbtiles.warp import generate_vrt


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
