# -*- coding: utf-8 -*-

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)
import pytest

import os
import unittest

import numpy

from gdal2mbtiles.constants import TILE_SIDE
from gdal2mbtiles.gdal import Dataset
from gdal2mbtiles.storages import Storage
from gdal2mbtiles.gd_types import rgba, XY
from gdal2mbtiles.vips import (ColorExact, ColorGradient, ColorPalette,
                               LibVips, TmsTiles, VImageAdapter, VipsDataset, VIPS)

from tests.test_gdal import TestCase as GdalTestCase


__dir__ = os.path.dirname(__file__)


class TestLibVips(unittest.TestCase):
    def tearDown(self):
        VIPS.set_concurrency(processes=0)  # Auto-detect

    def test_create(self):
        self.assertTrue(LibVips())
        self.assertRaises(OSError, LibVips, version=999)

    def test_concurrency(self):
        concurrency = 42
        vips = LibVips()
        self.assertRaises(ValueError, vips.set_concurrency, processes=1.1)
        self.assertRaises(ValueError, vips.set_concurrency, processes=-1)
        self.assertEqual(vips.set_concurrency(processes=concurrency), None)
        self.assertEqual(vips.get_concurrency(), concurrency)


class TestVImageAdapter(unittest.TestCase):
    def test_new_rgba(self):
        image = VImageAdapter.new_rgba(width=1, height=2)
        self.assertEqual(image.width, 1)
        self.assertEqual(image.height, 2)
        self.assertEqual(image.bands, 4)

    def test_buffer_size(self):
        image = VImageAdapter.new_rgba(width=16, height=16)
        self.assertEqual(
            VImageAdapter(image).BufferSize(),
            (16 *               # width
             16 *               # height
             4 *                # bands
             1)                 # data size
        )

    def test_stretch(self):
        image = VImageAdapter.new_rgba(width=16, height=16)

        # No stretch
        stretched = VImageAdapter(image).stretch(xscale=1.0, yscale=1.0)
        self.assertEqual(stretched.width, image.width)
        self.assertEqual(stretched.height, image.height)

        # X direction
        stretched = VImageAdapter(image).stretch(xscale=2.0, yscale=1.0)
        self.assertEqual(stretched.width, image.width * 2.0)
        self.assertEqual(stretched.height, image.height)

        # Y direction
        stretched = VImageAdapter(image).stretch(xscale=1.0, yscale=4.0)
        self.assertEqual(stretched.width, image.width)
        self.assertEqual(stretched.height, image.height * 4.0)

        # Both directions
        stretched = VImageAdapter(image).stretch(xscale=2.0, yscale=4.0)
        self.assertEqual(stretched.width, image.width * 2.0)
        self.assertEqual(stretched.height, image.height * 4.0)

        # Not a power of 2
        stretched = VImageAdapter(image).stretch(xscale=3.0, yscale=5.0)
        self.assertEqual(stretched.width, image.width * 3.0)
        self.assertEqual(stretched.height, image.height * 5.0)

        # Out of bounds
        self.assertRaises(ValueError,
                          VImageAdapter(image).stretch, xscale=0.5, yscale=1.0)
        self.assertRaises(ValueError,
                          VImageAdapter(image).stretch, xscale=1.0, yscale=0.5)

    def test_shrink_affine(self):
        image = VImageAdapter.new_rgba(width=16, height=16)

        # No shrink
        shrunk = VImageAdapter(image).shrink_affine(xscale=1.0, yscale=1.0)
        self.assertEqual(shrunk.width, image.width)
        self.assertEqual(shrunk.height, image.height)

        # X direction
        shrunk = VImageAdapter(image).shrink_affine(xscale=0.25, yscale=1.0)
        self.assertEqual(shrunk.width, image.width * 0.25)
        self.assertEqual(shrunk.height, image.height)

        # Y direction
        shrunk = VImageAdapter(image).shrink_affine(xscale=1.0, yscale=0.5)
        self.assertEqual(shrunk.width, image.width)
        self.assertEqual(shrunk.height, image.height * 0.5)

        # Both directions
        shrunk = VImageAdapter(image).shrink_affine(xscale=0.25, yscale=0.5)
        self.assertEqual(shrunk.width, image.width * 0.25)
        self.assertEqual(shrunk.height, image.height * 0.5)

        # Not a power of 2
        shrunk = VImageAdapter(image).shrink_affine(xscale=0.0625, yscale=0.125)
        self.assertEqual(shrunk.width, int(image.width * 0.0625))
        self.assertEqual(shrunk.height, int(image.height * 0.125))

        # Out of bounds
        self.assertRaises(ValueError,
                          VImageAdapter(image).shrink_affine, xscale=0.0, yscale=1.0)
        self.assertRaises(ValueError,
                          VImageAdapter(image).shrink_affine, xscale=2.0, yscale=1.0)
        self.assertRaises(ValueError,
                          VImageAdapter(image).shrink_affine, xscale=1.0, yscale=0.0)
        self.assertRaises(ValueError,
                          VImageAdapter(image).shrink_affine, xscale=1.0, yscale=2.0)

    def test_tms_align(self):
        image = VImageAdapter.new_rgba(width=16, height=16)

        # Already aligned to integer offsets
        result = VImageAdapter(image).tms_align(tile_width=16, tile_height=16,
                                 offset=XY(1, 1))
        self.assertEqual(result.width, image.width)
        self.assertEqual(result.height, image.height)

        # Spanning by half tiles in both X and Y directions
        result = VImageAdapter(image).tms_align(tile_width=16, tile_height=16,
                                 offset=XY(1.5, 1.5))
        self.assertEqual(result.width, image.width * 2)
        self.assertEqual(result.height, image.height * 2)

        # Image is quarter tile
        result = VImageAdapter(image).tms_align(tile_width=32, tile_height=32,
                                 offset=XY(1, 1))
        self.assertEqual(result.width, image.width * 2)
        self.assertEqual(result.height, image.height * 2)


class TestVipsDataset(GdalTestCase):
    def setUp(self):
        self.inputfile = os.path.join(__dir__,
                                      'bluemarble.tif')

        self.foreignfile = os.path.join(__dir__,
                                        'bluemarble-foreign.tif')
        self.slightlytoobigfile = os.path.join(
            __dir__, 'bluemarble-slightly-too-big.tif'
        )

        self.spanningforeignfile = os.path.join(
            __dir__, 'bluemarble-spanning-foreign.tif'
        )

        self.upsamplingfile = os.path.join(__dir__, 'upsampling.tif')

    def test_upsample(self):
        # bluemarble-foreign.tif is a 500 × 250 whole-world map.
        dataset = VipsDataset(inputfile=self.foreignfile)
        dataset.resample(resolution=None)
        self.assertEqual(dataset.RasterXSize, dataset.image.width)
        self.assertEqual(dataset.RasterYSize, dataset.image.height)
        self.assertEqual(dataset.RasterXSize, 512)
        self.assertEqual(dataset.RasterYSize, 512)

    @pytest.mark.newtest
    def test_downsample(self):
        """
        Test that a 258x258 file will get downsampled to
        256x256 instead of upsampled to the next resolution.
        Because the pixel size is within error tolerance
        of the lower resolution's pixel size
        """
        dataset = VipsDataset(inputfile=self.slightlytoobigfile)
        dataset.resample(resolution=None)
        self.assertEqual(dataset.RasterXSize, dataset.image.width)
        self.assertEqual(dataset.RasterYSize, dataset.image.height)
        self.assertEqual(dataset.RasterXSize, 256)
        self.assertEqual(dataset.RasterYSize, 256)

    def test_align_to_grid(self):
        with LibVips.disable_warnings():
            # bluemarble.tif is a 1024 × 1024 whole-world map.
            dataset = VipsDataset(inputfile=self.inputfile)
            dataset.align_to_grid()
            self.assertEqual(dataset.image.width, 1024)
            self.assertEqual(dataset.image.height, 1024)
            self.assertEqual(dataset.RasterXSize, 1024)
            self.assertEqual(dataset.RasterYSize, 1024)
            self.assertExtentsEqual(dataset.GetExtents(),
                                    dataset.GetTiledExtents())

            # bluemarble-foreign.tif is a 500 × 250 whole-world map.
            dataset = VipsDataset(inputfile=self.foreignfile)
            dataset.align_to_grid()
            self.assertEqual(dataset.image.width, 512)
            self.assertEqual(dataset.image.height, 512)
            self.assertEqual(dataset.RasterXSize, 512)
            self.assertEqual(dataset.RasterYSize, 512)
            self.assertEqual(dataset.GetExtents(),
                             dataset.GetTiledExtents())

            # bluemarble-spanning-foreign.tif is a 154 × 154 whole-world map.
            dataset = VipsDataset(inputfile=self.spanningforeignfile)
            dataset.align_to_grid()
            self.assertEqual(dataset.image.width, 256)
            self.assertEqual(dataset.image.height, 256)
            self.assertEqual(dataset.RasterXSize, 256)
            self.assertEqual(dataset.RasterYSize, 256)
            self.assertExtentsEqual(dataset.GetExtents(),
                                    dataset.GetTiledExtents())
            # The upper-left corner should be transparent
            data = numpy.frombuffer(dataset.image.write_to_memory(),
                                    dtype=numpy.uint8)
            self.assertEqual(tuple(data[0:4]),
                             rgba(0, 0, 0, 0))

    def test_readasarray(self):
        with LibVips.disable_warnings():
            vips_ds = VipsDataset(inputfile=self.upsamplingfile)
            gdal_ds = Dataset(inputfile=self.upsamplingfile)

            # Reading the whole file
            self.assertEqual(
                vips_ds.ReadAsArray(xoff=0, yoff=0).all(),
                gdal_ds.ReadAsArray(xoff=0, yoff=0).all()
            )

            # Reading from an offset
            vips_data = vips_ds.ReadAsArray(xoff=128, yoff=128)
            gdal_data = gdal_ds.ReadAsArray(
                xoff=128, yoff=128, xsize=128, ysize=128
            )
            self.assertEqual(vips_data.all(), gdal_data.all())

            vips_blue = vips_ds.GetRasterBand(3)
            gdal_blue = gdal_ds.GetRasterBand(3)

            # Reading the whole band
            self.assertEqual(
                vips_blue.ReadAsArray(xoff=0, yoff=0).all(),
                gdal_blue.ReadAsArray(xoff=0, yoff=0).all()
            )

            # Reading from an offset
            vips_band_data = vips_blue.ReadAsArray(xoff=128, yoff=128)
            gdal_band_data = gdal_blue.ReadAsArray(
                xoff=128, yoff=128, win_xsize=128, win_ysize=128
            )
            self.assertEqual(vips_band_data.all(), gdal_band_data.all())

            # Test for errors
            self.assertRaises(
                ValueError,
                vips_ds.ReadAsArray,
                xoff=0, yoff=0, buf_obj=[]
            )

            self.assertRaises(
                ValueError,
                vips_blue.ReadAsArray,
                xoff=0, yoff=0, buf_xsize=1, buf_ysize=1
            )


class TestTmsTiles(unittest.TestCase):
    def test_dimensions(self):
        # Very small WGS84 map. :-)
        image = VImageAdapter.new_rgba(width=2, height=1)
        tiles = TmsTiles(image=image,
                         storage=Storage(renderer=None),
                         tile_width=1, tile_height=1,
                         offset=XY(0, 0), resolution=0)
        self.assertEqual(tiles.image_width, 2)
        self.assertEqual(tiles.image_height, 1)

    def test_downsample(self):
        resolution = 2
        image = VImageAdapter.new_rgba(width=TILE_SIDE * 2 ** resolution,
                                height=TILE_SIDE * 2 ** resolution)
        tiles = TmsTiles(image=image,
                         storage=Storage(renderer=None),
                         tile_width=TILE_SIDE, tile_height=TILE_SIDE,
                         offset=XY(0, 0),
                         resolution=resolution)

        # Zero levels - invalid
        self.assertRaises(AssertionError,
                          tiles.downsample, levels=0)

        # One level
        tiles1a = tiles.downsample()
        self.assertEqual(tiles1a.image_width,
                         TILE_SIDE * 2 ** (resolution - 1))
        self.assertEqual(tiles1a.image_height,
                         TILE_SIDE * 2 ** (resolution - 1))
        self.assertEqual(tiles1a.resolution,
                         resolution - 1)

        tiles1b = tiles.downsample(levels=1)
        self.assertEqual(tiles1b.image_width,
                         TILE_SIDE * 2 ** (resolution - 1))
        self.assertEqual(tiles1b.image_height,
                         TILE_SIDE * 2 ** (resolution - 1))
        self.assertEqual(tiles1b.resolution,
                         resolution - 1)

        # Two levels
        tiles2 = tiles.downsample(levels=2)
        self.assertEqual(tiles2.image_width,
                         TILE_SIDE * 2 ** (resolution - 2))
        self.assertEqual(tiles2.image_height,
                         TILE_SIDE * 2 ** (resolution - 2))
        self.assertEqual(tiles2.resolution,
                         resolution - 2)

        # Three levels - invalid since resolution is 2
        self.assertRaises(AssertionError,
                          tiles.downsample, levels=3)

    def test_upsample(self):
        resolution = 0
        image = VImageAdapter.new_rgba(width=TILE_SIDE * 2 ** resolution,
                                height=TILE_SIDE * 2 ** resolution)

        tiles = TmsTiles(image=image,
                         storage=Storage(renderer=None),
                         tile_width=TILE_SIDE, tile_height=TILE_SIDE,
                         offset=XY(0, 0), resolution=resolution)

        # Zero levels
        self.assertRaises(AssertionError,
                          tiles.upsample, levels=0)

        # One level
        tiles1a = tiles.upsample()
        self.assertEqual(tiles1a.image_width,
                         TILE_SIDE * 2 ** (resolution + 1))
        self.assertEqual(tiles1a.image_height,
                         TILE_SIDE * 2 ** (resolution + 1))
        self.assertEqual(tiles1a.resolution,
                         resolution + 1)

        tiles1b = tiles.upsample(levels=1)
        self.assertEqual(tiles1b.image_width,
                         TILE_SIDE * 2 ** (resolution + 1))
        self.assertEqual(tiles1b.image_height,
                         TILE_SIDE * 2 ** (resolution + 1))
        self.assertEqual(tiles1b.resolution,
                         resolution + 1)

        # Two levels
        tiles2 = tiles.upsample(levels=2)
        self.assertEqual(tiles2.image_width,
                         TILE_SIDE * 2 ** (resolution + 2))
        self.assertEqual(tiles2.image_height,
                         TILE_SIDE * 2 ** (resolution + 2))
        self.assertEqual(tiles2.resolution,
                         resolution + 2)


class TestColors(unittest.TestCase):
    def setUp(self):
        self.transparent = rgba(0, 0, 0, 0)
        self.black = rgba(0, 0, 0, 255)
        self.red = rgba(255, 0, 0, 255)
        self.green = rgba(0, 255, 0, 255)
        self.blue = rgba(0, 0, 255, 255)
        self.white = rgba(255, 255, 255, 255)

    def test_exact_0(self):
        # Empty
        colors = ColorExact()
        self.assertEqual(colors._clauses(band='r'),
                         [])
        self.assertEqual(colors._clauses(band='a'),
                         [])
        self.assertEqual(colors._expression(band='r'),
                         None)
        self.assertEqual(colors._expression(band='a'),
                         None)

        # Empty, with nodata - no-op
        self.assertEqual(colors._clauses(band='r', nodata=0),
                         [])
        self.assertEqual(colors._clauses(band='a', nodata=0),
                         [])
        self.assertEqual(colors._expression(band='r', nodata=0),
                         None)
        self.assertEqual(colors._expression(band='a', nodata=0),
                         None)

    def test_exact_1(self):
        # One color
        colors = ColorExact({0: self.red})
        self.assertEqual(colors._clauses(band='r'),
                         [('n == 0', self.red.r)])
        self.assertEqual(colors._clauses(band='a'),
                         [('n == 0', self.red.a)])
        self.assertEqual(colors._expression(band='r'),
                         'where(n == 0, {true}, {false})'.format(
                             true=self.red.r,
                             false=ColorExact.BACKGROUND.r
                         ))
        self.assertEqual(colors._expression(band='a'),
                         'where(n == 0, {true}, {false})'.format(
                             true=self.red.a,
                             false=ColorExact.BACKGROUND.a
                         ))

    def test_exact_2(self):
        # Two colors
        colors = ColorExact({0: self.red,
                             2: self.green})
        self.assertEqual(colors._clauses(band='r'),
                         [('n == 0', self.red.r)])
        self.assertEqual(colors._clauses(band='g'),
                         [('n == 2', self.green.g)])
        self.assertEqual(colors._clauses(band='a'),
                         [('n == 0', self.red.a),
                          ('n == 2', self.green.a)])
        self.assertEqual(
            colors._expression(band='r'),
            'where(n == 0, {red}, {false})'.format(
                red=self.red.r,
                false=ColorExact.BACKGROUND.r
            ))
        self.assertEqual(
            colors._expression(band='g'),
            'where(n == 2, {green}, {false})'.format(
                green=self.green.g,
                false=ColorExact.BACKGROUND.g
            ))
        self.assertEqual(
            colors._expression(band='a'),
            'where(n == 2, {green}, where(n == 0, {red}, {false}))'.format(
                red=self.red.a,
                green=self.green.a,
                false=ColorExact.BACKGROUND.a
            ))

        # Two colors, with no data - should look like "One color" above.
        colors = ColorExact({0: self.red,
                             2: self.green})
        self.assertEqual(colors._clauses(band='r', nodata=2),
                         [('n == 0', self.red.r)])
        self.assertEqual(colors._clauses(band='a', nodata=2),
                         [('n == 0', self.red.a)])
        self.assertEqual(colors._expression(band='r', nodata=2),
                         'where(n == 0, {true}, {false})'.format(
                             true=self.red.r,
                             false=ColorExact.BACKGROUND.r
                         ))
        self.assertEqual(colors._expression(band='a', nodata=2),
                         'where(n == 0, {true}, {false})'.format(
                             true=self.red.a,
                             false=ColorExact.BACKGROUND.a
                         ))

    def test_palette_0(self):
        # Empty
        colors = ColorPalette()
        self.assertEqual(colors._clauses(band='r'),
                         [])
        self.assertEqual(colors._clauses(band='a'),
                         [])
        self.assertEqual(colors._expression(band='r'),
                         None)
        self.assertEqual(colors._expression(band='a'),
                         None)

        # Empty, with nodata - no-op
        self.assertEqual(colors._clauses(band='r', nodata=0),
                         [])
        self.assertEqual(colors._clauses(band='a', nodata=0),
                         [])
        self.assertEqual(colors._expression(band='r', nodata=0),
                         None)
        self.assertEqual(colors._expression(band='a', nodata=0),
                         None)

    def test_palette_1(self):
        # One color
        colors = ColorPalette({0: self.red})
        self.assertEqual(colors._clauses(band='r'),
                         [('n >= 0', self.red.r)])
        self.assertEqual(colors._clauses(band='a'),
                         [('n >= 0', self.red.a)])
        self.assertEqual(colors._expression(band='r'),
                         'where(n >= 0, {true}, {false})'.format(
                             true=self.red.r,
                             false=ColorPalette.BACKGROUND.r
                         ))
        self.assertEqual(colors._expression(band='a'),
                         'where(n >= 0, {true}, {false})'.format(
                             true=self.red.a,
                             false=ColorPalette.BACKGROUND.a
                         ))

        # One color, with nodata value before it
        colors = ColorPalette({0: self.red})
        self.assertEqual(colors._clauses(band='r',
                                                 nodata=float('-inf')),
                         [('n >= 0', self.red.r)])
        self.assertEqual(colors._clauses(band='a',
                                                 nodata=float('-inf')),
                         [('n >= 0', self.red.a)])
        self.assertEqual(colors._expression(band='r', nodata=float('-inf')),
                         'where(n >= 0, {true}, {false})'.format(
                             true=self.red.r,
                             false=ColorPalette.BACKGROUND.r
                         ))
        self.assertEqual(colors._expression(band='a', nodata=float('-inf')),
                         'where(n >= 0, {true}, {false})'.format(
                             true=self.red.a,
                             false=ColorPalette.BACKGROUND.a
                         ))

        # One color, with nodata value after it
        colors = ColorPalette({0: self.red})
        self.assertEqual(colors._clauses(band='r',
                                                 nodata=float('inf')),
                         [('n >= 0', self.red.r)])
        self.assertEqual(colors._clauses(band='a',
                                                 nodata=float('inf')),
                         [('n >= 0', self.red.a),
                          ('n == inf', ColorPalette.BACKGROUND.a)])
        self.assertEqual(colors._expression(band='r', nodata=float('inf')),
                         'where(n >= 0, {true}, {false})'.format(
                             true=self.red.r,
                             false=ColorPalette.BACKGROUND.r
                         ))
        self.assertEqual(
            colors._expression(band='a', nodata=float('inf')),
            'where(n == inf, {false}, where(n >= 0, {true}, {false}))'.format(
                true=self.red.a,
                false=ColorPalette.BACKGROUND.a
            ))

    def test_palette_2(self):
        # Two colors
        colors = ColorPalette({0: self.red,
                               2: self.green})
        self.assertEqual(colors._clauses(band='r'),
                         [('n >= 0', self.red.r),
                          ('n >= 2', self.green.r)])
        self.assertEqual(colors._clauses(band='g'),
                         [('n >= 2', self.green.g)])
        self.assertEqual(colors._clauses(band='a'),
                         [('n >= 0', self.red.a)])
        self.assertEqual(
            colors._expression(band='r'),
            'where(n >= 2, {green}, where(n >= 0, {red}, {false}))'.format(
                red=self.red.r,
                green=self.green.r,
                false=ColorPalette.BACKGROUND.r
            ))
        self.assertEqual(
            colors._expression(band='g'),
            'where(n >= 2, {green}, {false})'.format(
                green=self.green.g,
                false=ColorPalette.BACKGROUND.g
            ))
        self.assertEqual(
            colors._expression(band='a'),
            'where(n >= 0, {red}, {false})'.format(
                red=self.red.a,
                false=ColorPalette.BACKGROUND.a
            ))

        # Two colors, with a nodata value in between them
        colors = ColorPalette({0: self.red,
                               2: self.green})
        self.assertEqual(colors._clauses(band='r', nodata=1),
                         [('n >= 0', self.red.r),
                          ('n >= 2', self.green.r)])
        self.assertEqual(colors._clauses(band='g', nodata=1),
                         [('n >= 2', self.green.g)])
        self.assertEqual(colors._clauses(band='a', nodata=1),
                         [('n >= 0', self.red.a),
                          ('n == 1', ColorPalette.BACKGROUND.a)])
        self.assertEqual(
            colors._expression(band='r', nodata=1),
            'where(n >= 2, {green}, where(n >= 0, {red}, {false}))'.format(
                red=self.red.r,
                green=self.green.r,
                false=ColorPalette.BACKGROUND.r
            ))
        self.assertEqual(
            colors._expression(band='g', nodata=1),
            'where(n >= 2, {green}, {false})'.format(
                green=self.green.g,
                false=ColorPalette.BACKGROUND.g
            ))
        self.assertEqual(
            colors._expression(band='a', nodata=1),
            'where(n == 1, {false}, where(n >= 0, {red}, {false}))'.format(
                red=self.red.a,
                false=ColorPalette.BACKGROUND.a
            ))

        # Two colors, with nodata value replacing one of them
        colors = ColorPalette({0: self.red,
                               2: self.green})
        self.assertEqual(colors._clauses(band='r', nodata=0),
                         [('n >= 0', self.red.r),
                          ('n >= 2', self.green.r)])
        self.assertEqual(colors._clauses(band='g', nodata=0),
                         [('n >= 2', self.green.g)])
        self.assertEqual(colors._clauses(band='a', nodata=0),
                         [('n >= 0', self.red.a),
                          ('n == 0', ColorPalette.BACKGROUND.a)])
        self.assertEqual(
            colors._expression(band='r', nodata=0),
            'where(n >= 2, {green}, where(n >= 0, {red}, {false}))'.format(
                red=self.red.r,
                green=self.green.r,
                false=ColorPalette.BACKGROUND.r
            ))
        self.assertEqual(
            colors._expression(band='g', nodata=0),
            'where(n >= 2, {green}, {false})'.format(
                green=self.green.g,
                false=ColorPalette.BACKGROUND.g
            ))
        self.assertEqual(
            colors._expression(band='a', nodata=0),
            'where(n == 0, {false}, where(n >= 0, {red}, {false}))'.format(
                red=self.red.a,
                false=ColorPalette.BACKGROUND.a
            ))

    def test_gradient_0(self):
        # Empty
        colors = ColorGradient()
        self.assertEqual(colors._clauses(band='r'),
                         [])
        self.assertEqual(colors._clauses(band='a'),
                         [])
        self.assertEqual(colors._expression(band='r'),
                         None)
        self.assertEqual(colors._expression(band='a'),
                         None)

        # Empty, with nodata - no-op
        self.assertEqual(colors._clauses(band='r', nodata=0),
                         [])
        self.assertEqual(colors._clauses(band='a', nodata=0),
                         [])
        self.assertEqual(colors._expression(band='r', nodata=0),
                         None)
        self.assertEqual(colors._expression(band='a', nodata=0),
                         None)

    def test_gradient_1(self):
        # One color
        colors = ColorGradient({0: self.red})
        self.assertEqual(colors._clauses(band='r'),
                         [('n >= 0', self.red.r)])
        self.assertEqual(colors._clauses(band='a'),
                         [('n >= 0', self.red.a)])
        self.assertEqual(colors._expression(band='r'),
                         'where(n >= 0, {true}, {false})'.format(
                             true=self.red.r,
                             false=ColorGradient.BACKGROUND.r
                         ))
        self.assertEqual(colors._expression(band='a'),
                         'where(n >= 0, {true}, {false})'.format(
                             true=self.red.a,
                             false=ColorGradient.BACKGROUND.a
                         ))

        # One color, with nodata value before it
        colors = ColorGradient({0: self.red})
        self.assertEqual(colors._clauses(band='r',
                                                 nodata=float('-inf')),
                         [('n >= 0', self.red.r)])
        self.assertEqual(colors._clauses(band='a',
                                                 nodata=float('-inf')),
                         [('n >= 0', self.red.a)])
        self.assertEqual(colors._expression(band='r', nodata=float('-inf')),
                         'where(n >= 0, {true}, {false})'.format(
                             true=self.red.r,
                             false=ColorGradient.BACKGROUND.r
                         ))
        self.assertEqual(colors._expression(band='a', nodata=float('-inf')),
                         'where(n >= 0, {true}, {false})'.format(
                             true=self.red.a,
                             false=ColorGradient.BACKGROUND.a
                         ))

        # One color, with nodata value after it
        colors = ColorGradient({0: self.red})
        self.assertEqual(colors._clauses(band='r',
                                                 nodata=float('inf')),
                         [('n >= 0', self.red.r)])
        self.assertEqual(colors._clauses(band='a',
                                                 nodata=float('inf')),
                         [('n >= 0', self.red.a),
                          ('n == inf', ColorGradient.BACKGROUND.a)])
        self.assertEqual(colors._expression(band='r', nodata=float('inf')),
                         'where(n >= 0, {true}, {false})'.format(
                             true=self.red.r,
                             false=ColorGradient.BACKGROUND.r
                         ))
        self.assertEqual(
            colors._expression(band='a', nodata=float('inf')),
            'where(n == inf, {false}, where(n >= 0, {true}, {false}))'.format(
                true=self.red.a,
                false=ColorGradient.BACKGROUND.a
            ))

    def test_gradient_2(self):
        # Two colors
        colors = ColorGradient({0: self.red,
                                255: self.green})
        self.assertEqual(
            colors._clauses(band='r'),
            [('n >= 0', '-1.0 * n + {0}'.format(float(self.red.r))),
             ('n >= 255', self.green.r)]
        )
        self.assertEqual(
            colors._clauses(band='g'),
            [('n >= 0', '1.0 * n + {0}'.format(float(self.red.g))),
             ('n >= 255', self.green.g)]
        )
        self.assertEqual(colors._clauses(band='a'),
                         [('n >= 0', self.red.a)])
        self.assertEqual(
            colors._expression(band='r'),
            'where(n >= 255, {green}, '
            'where(n >= 0, -1.0 * n + {red}, {false}))'.format(
                red=float(self.red.r),
                green=self.green.r,
                false=ColorGradient.BACKGROUND.r
            )
        )
        self.assertEqual(
            colors._expression(band='g'),
            'where(n >= 255, {green}, '
            'where(n >= 0, 1.0 * n + {red}, {false}))'.format(
                red=float(self.red.g),
                green=self.green.g,
                false=ColorGradient.BACKGROUND.g
            )
        )
        self.assertEqual(
            colors._expression(band='a'),
            'where(n >= 0, {red}, {false})'.format(
                red=self.red.a,
                false=ColorGradient.BACKGROUND.a
            )
        )

        # Two colors, with a nodata value in between them
        colors = ColorGradient({0: self.red,
                                255: self.green})
        self.assertEqual(
            colors._clauses(band='r', nodata=1),
            [('n >= 0', '-1.0 * n + {0}'.format(float(self.red.r))),
             ('n >= 255', self.green.r)]
        )
        self.assertEqual(
            colors._clauses(band='g', nodata=1),
            [('n >= 0', '1.0 * n + {0}'.format(float(self.red.g))),
             ('n >= 255', self.green.g)]
        )
        self.assertEqual(colors._clauses(band='a', nodata=1),
                         [('n >= 0', self.red.a),
                          ('n == 1', ColorGradient.BACKGROUND.a)])
        self.assertEqual(
            colors._expression(band='r', nodata=1),
            'where(n >= 255, {green}, '
            'where(n >= 0, -1.0 * n + {red}, {false}))'.format(
                red=float(self.red.r),
                green=self.green.r,
                false=ColorGradient.BACKGROUND.r
            )
        )
        self.assertEqual(
            colors._expression(band='g', nodata=1),
            'where(n >= 255, {green}, '
            'where(n >= 0, 1.0 * n + {red}, {false}))'.format(
                red=float(self.red.g),
                green=self.green.g,
                false=ColorGradient.BACKGROUND.g
            )
        )
        self.assertEqual(
            colors._expression(band='a', nodata=1),
            'where(n == 1, {false}, where(n >= 0, {red}, {false}))'.format(
                red=self.red.a,
                false=ColorGradient.BACKGROUND.a
            )
        )

        # Two colors, with nodata value replacing one of them
        colors = ColorGradient({0: self.red,
                                255: self.green})
        self.assertEqual(
            colors._clauses(band='r', nodata=0),
            [('n >= 0', '-1.0 * n + {0}'.format(float(self.red.r))),
             ('n >= 255', self.green.r)]
         )
        self.assertEqual(
            colors._clauses(band='g', nodata=0),
            [('n >= 0', '1.0 * n + {0}'.format(float(self.red.g))),
             ('n >= 255', self.green.g)]
        )
        self.assertEqual(colors._clauses(band='a', nodata=0),
                         [('n >= 0', self.red.a),
                          ('n == 0', ColorGradient.BACKGROUND.a)])
        self.assertEqual(
            colors._expression(band='r', nodata=0),
            'where(n >= 255, {green}, '
            'where(n >= 0, -1.0 * n + {red}, {false}))'.format(
                red=float(self.red.r),
                green=self.green.r,
                false=ColorGradient.BACKGROUND.r
            )
        )
        self.assertEqual(
            colors._expression(band='g', nodata=0),
            'where(n >= 255, {green}, '
            'where(n >= 0, 1.0 * n + {red}, {false}))'.format(
                red=float(self.red.g),
                green=self.green.g,
                false=ColorGradient.BACKGROUND.g
            )
        )
        self.assertEqual(
            colors._expression(band='a', nodata=0),
            'where(n == 0, {false}, where(n >= 0, {red}, {false}))'.format(
                red=self.red.a,
                false=ColorGradient.BACKGROUND.a
            )
        )

    def test_gradient_3(self):
        # Three colors - one gradient split in half
        dark_red = rgba(127, 0, 0, 255)
        colors = ColorGradient({0: self.red,
                                128: dark_red,
                                255: self.black})
        self.assertEqual(
            colors._clauses(band='r'),
            [('n >= 0', '-1.0 * n + {0}'.format(float(self.red.r))),
             ('n >= 255', self.black.r)]
        )
        self.assertEqual(colors._clauses(band='g'),
                         [])
        self.assertEqual(colors._clauses(band='a'),
                         [('n >= 0', self.red.a)])
        self.assertEqual(colors._expression(band='r'),
                         'where(n >= 255, {black}, '
                         'where(n >= 0, -1.0 * n + {red}, {false}))'.format(
                             black=self.black.r,
                             red=float(self.red.r),
                             false=ColorGradient.BACKGROUND.r
                         ))
        self.assertEqual(colors._expression(band='g'),
                         None)
        self.assertEqual(colors._expression(band='a'),
                         'where(n >= 0, {red}, {false})'.format(
                             red=self.red.a,
                             false=ColorGradient.BACKGROUND.a
                         ))

        # Three colors - one gradient split in half
        dark_red = rgba(127, 0, 0, 255)
        colors = ColorGradient({0: self.red,
                                64: dark_red,
                                255: self.black})
        self.assertEqual(
            colors._clauses(band='r'),
            [('n >= 0', '-0.5 * n + {0}'.format(float(self.red.r))),
             ('n >= 64', '-1.5039370078740157 * n + 223.251968503937'),
             ('n >= 255', self.black.r)]
        )
        self.assertEqual(colors._clauses(band='g'),
                         [])
        self.assertEqual(colors._clauses(band='a'),
                         [('n >= 0', self.red.a)])
        self.assertEqual(
            colors._expression(band='r'),
            'where(n >= 255, {black}, '
            'where(n >= 64, -1.5039370078740157 * n + 223.251968503937, '
            'where(n >= 0, -0.5 * n + {red}, {false})))'.format(
                black=self.black.r,
                red=float(self.red.r),
                false=ColorGradient.BACKGROUND.r
            ))
        self.assertEqual(colors._expression(band='g'),
                         None)
        self.assertEqual(colors._expression(band='a'),
                         'where(n >= 0, {red}, {false})'.format(
                             red=self.red.a,
                             false=ColorGradient.BACKGROUND.a
                         ))
