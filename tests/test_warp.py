import os
import subprocess
from tempfile import NamedTemporaryFile
import unittest
from xml.etree import ElementTree

from osgeo.gdalconst import GRA_Cubic

from gdal2mbtiles.constants import GDALINFO
from gdal2mbtiles.exceptions import (GdalError, CalledGdalError,
                                     UnknownResamplingMethodError, VrtError)
from gdal2mbtiles.types import rgba
from gdal2mbtiles.warp import (colourize, expand_colour_bands, warp,
                               preprocess, render_vrt)


__dir__ = os.path.dirname(__file__)


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


class TestGenerateVRT(unittest.TestCase):
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

class TestRenderVrt(unittest.TestCase):
    def setUp(self):
        self.inputfile = os.path.join(__dir__,
                                      'bluemarble.tif')

    def test_simple(self):
        with NamedTemporaryFile(suffix='.vrt') as inputfile, \
             NamedTemporaryFile(suffix='.tif') as tmpfile:
            inputfile.write(warp(self.inputfile))
            inputfile.flush()
            outputfile = tmpfile.name
            render_vrt(inputfile=inputfile.name, outputfile=outputfile,
                       compress='LZW')
            self.assertEqual(
                subprocess.call([GDALINFO, outputfile],
                                stdout=open('/dev/null', 'w+')),
                0
            )

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
