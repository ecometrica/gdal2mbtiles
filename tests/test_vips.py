# -*- coding: utf-8 -*-

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import unittest

from gdal2mbtiles.constants import TILE_SIDE
from gdal2mbtiles.storages import Storage
from gdal2mbtiles.types import rgba, XY
from gdal2mbtiles.vips import (ColorExact, ColorPalette,
                               LibVips, TmsTiles, VImage, VIPS)


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


class TestVImage(unittest.TestCase):
    def test_new_rgba(self):
        image = VImage.new_rgba(width=1, height=2)
        self.assertEqual(image.Xsize(), 1)
        self.assertEqual(image.Ysize(), 2)
        self.assertEqual(image.Bands(), 4)

    def test_from_vimage(self):
        image = VImage.new_rgba(width=1, height=1)
        self.assertEqual(VImage.from_vimage(image).tostring(),
                         image.tostring())

    def test_stretch(self):
        image = VImage.new_rgba(width=16, height=16)

        # No stretch
        stretched = image.stretch(xscale=1.0, yscale=1.0)
        self.assertEqual(stretched.Xsize(), image.Xsize())
        self.assertEqual(stretched.Ysize(), image.Ysize())

        # X direction
        stretched = image.stretch(xscale=2.0, yscale=1.0)
        self.assertEqual(stretched.Xsize(), image.Xsize() * 2.0)
        self.assertEqual(stretched.Ysize(), image.Ysize())

        # Y direction
        stretched = image.stretch(xscale=1.0, yscale=4.0)
        self.assertEqual(stretched.Xsize(), image.Xsize())
        self.assertEqual(stretched.Ysize(), image.Ysize() * 4.0)

        # Both directions
        stretched = image.stretch(xscale=2.0, yscale=4.0)
        self.assertEqual(stretched.Xsize(), image.Xsize() * 2.0)
        self.assertEqual(stretched.Ysize(), image.Ysize() * 4.0)

        # Not a power of 2
        stretched = image.stretch(xscale=3.0, yscale=5.0)
        self.assertEqual(stretched.Xsize(), image.Xsize() * 3.0)
        self.assertEqual(stretched.Ysize(), image.Ysize() * 5.0)

        # Out of bounds
        self.assertRaises(ValueError,
                          image.stretch, xscale=0.5, yscale=1.0)
        self.assertRaises(ValueError,
                          image.stretch, xscale=1.0, yscale=0.5)

    def test_shrink(self):
        image = VImage.new_rgba(width=16, height=16)

        # No shrink
        shrunk = image.shrink(xscale=1.0, yscale=1.0)
        self.assertEqual(shrunk.Xsize(), image.Xsize())
        self.assertEqual(shrunk.Ysize(), image.Ysize())

        # X direction
        shrunk = image.shrink(xscale=0.25, yscale=1.0)
        self.assertEqual(shrunk.Xsize(), image.Xsize() * 0.25)
        self.assertEqual(shrunk.Ysize(), image.Ysize())

        # Y direction
        shrunk = image.shrink(xscale=1.0, yscale=0.5)
        self.assertEqual(shrunk.Xsize(), image.Xsize())
        self.assertEqual(shrunk.Ysize(), image.Ysize() * 0.5)

        # Both directions
        shrunk = image.shrink(xscale=0.25, yscale=0.5)
        self.assertEqual(shrunk.Xsize(), image.Xsize() * 0.25)
        self.assertEqual(shrunk.Ysize(), image.Ysize() * 0.5)

        # Not a power of 2
        shrunk = image.shrink(xscale=0.1, yscale=0.2)
        self.assertEqual(shrunk.Xsize(), int(image.Xsize() * 0.1))
        self.assertEqual(shrunk.Ysize(), int(image.Ysize() * 0.2))

        # Out of bounds
        self.assertRaises(ValueError,
                          image.shrink, xscale=0.0, yscale=1.0)
        self.assertRaises(ValueError,
                          image.shrink, xscale=2.0, yscale=1.0)
        self.assertRaises(ValueError,
                          image.shrink, xscale=1.0, yscale=0.0)
        self.assertRaises(ValueError,
                          image.shrink, xscale=1.0, yscale=2.0)

    def test_tms_align(self):
        image = VImage.new_rgba(width=16, height=16)

        # Already aligned to integer offsets
        result = image.tms_align(tile_width=16, tile_height=16,
                                 offset=XY(1, 1))
        self.assertEqual(result.Xsize(), image.Xsize())
        self.assertEqual(result.Ysize(), image.Ysize())

        # Spanning by half tiles in both X and Y directions
        result = image.tms_align(tile_width=16, tile_height=16,
                                 offset=XY(1.5, 1.5))
        self.assertEqual(result.Xsize(), image.Xsize() * 2)
        self.assertEqual(result.Ysize(), image.Ysize() * 2)

        # Image is quarter tile
        result = image.tms_align(tile_width=32, tile_height=32,
                                 offset=XY(1, 1))
        self.assertEqual(result.Xsize(), image.Xsize() * 2)
        self.assertEqual(result.Ysize(), image.Ysize() * 2)


class TestTmsTiles(unittest.TestCase):
    def test_dimensions(self):
        # Very small WGS84 map. :-)
        image = VImage.new_rgba(width=2, height=1)
        tiles = TmsTiles(image=image,
                         storage=Storage(renderer=None),
                         tile_width=1, tile_height=1,
                         offset=XY(0, 0), resolution=0)
        self.assertEqual(tiles.image_width, 2)
        self.assertEqual(tiles.image_height, 1)

    def test_downsample(self):
        resolution = 2
        image = VImage.new_rgba(width=TILE_SIDE * 2 ** resolution,
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
        image = VImage.new_rgba(width=TILE_SIDE * 2 ** resolution,
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
        self.assertEqual(colors._numexpr_clauses(band='r'),
                         [])
        self.assertEqual(colors._numexpr_clauses(band='a'),
                         [])
        self.assertEqual(colors._as_numexpr(band='r'),
                         '0')
        self.assertEqual(colors._as_numexpr(band='a'),
                         '0')

        # Empty, with nodata - no-op
        self.assertEqual(colors._numexpr_clauses(band='r', nodata=0),
                         [])
        self.assertEqual(colors._numexpr_clauses(band='a', nodata=0),
                         [])
        self.assertEqual(colors._as_numexpr(band='r', nodata=0),
                         '0')
        self.assertEqual(colors._as_numexpr(band='a', nodata=0),
                         '0')

    def test_exact_1(self):
        # One color
        colors = ColorExact({0: self.red})
        self.assertEqual(colors._numexpr_clauses(band='r'),
                         [('n == 0', self.red.r)])
        self.assertEqual(colors._numexpr_clauses(band='a'),
                         [('n == 0', self.red.a)])
        self.assertEqual(colors._as_numexpr(band='r'),
                         'where(n == 0, {true}, {false})'.format(
                             true=self.red.r,
                             false=ColorExact.BACKGROUND.r
                         ))
        self.assertEqual(colors._as_numexpr(band='a'),
                         'where(n == 0, {true}, {false})'.format(
                             true=self.red.a,
                             false=ColorExact.BACKGROUND.a
                         ))

    def test_exact_2(self):
        # Two colors
        colors = ColorExact({0: self.red,
                             2: self.green})
        self.assertEqual(colors._numexpr_clauses(band='r'),
                         [('n == 0', self.red.r)])
        self.assertEqual(colors._numexpr_clauses(band='g'),
                         [('n == 2', self.green.g)])
        self.assertEqual(colors._numexpr_clauses(band='a'),
                         [('n == 0', self.red.a),
                          ('n == 2', self.green.a)])
        self.assertEqual(
            colors._as_numexpr(band='r'),
            'where(n == 0, {red}, {false})'.format(
                red=self.red.r,
                false=ColorExact.BACKGROUND.r
            ))
        self.assertEqual(
            colors._as_numexpr(band='g'),
            'where(n == 2, {green}, {false})'.format(
                green=self.green.g,
                false=ColorExact.BACKGROUND.g
            ))
        self.assertEqual(
            colors._as_numexpr(band='a'),
            'where(n == 2, {green}, where(n == 0, {red}, {false}))'.format(
                red=self.red.a,
                green=self.green.a,
                false=ColorExact.BACKGROUND.a
            ))

        # Two colors, with no data - should look like "One color" above.
        colors = ColorExact({0: self.red,
                             2: self.green})
        self.assertEqual(colors._numexpr_clauses(band='r', nodata=2),
                         [('n == 0', self.red.r)])
        self.assertEqual(colors._numexpr_clauses(band='a', nodata=2),
                         [('n == 0', self.red.a)])
        self.assertEqual(colors._as_numexpr(band='r', nodata=2),
                         'where(n == 0, {true}, {false})'.format(
                             true=self.red.r,
                             false=ColorExact.BACKGROUND.r
                         ))
        self.assertEqual(colors._as_numexpr(band='a', nodata=2),
                         'where(n == 0, {true}, {false})'.format(
                             true=self.red.a,
                             false=ColorExact.BACKGROUND.a
                         ))

    def test_palette_0(self):
        # Empty
        colors = ColorPalette()
        self.assertEqual(colors._numexpr_clauses(band='r'),
                         [])
        self.assertEqual(colors._numexpr_clauses(band='a'),
                         [])
        self.assertEqual(colors._as_numexpr(band='r'),
                         '0')
        self.assertEqual(colors._as_numexpr(band='a'),
                         '0')

        # Empty, with nodata - no-op
        self.assertEqual(colors._numexpr_clauses(band='r', nodata=0),
                         [])
        self.assertEqual(colors._numexpr_clauses(band='a', nodata=0),
                         [])
        self.assertEqual(colors._as_numexpr(band='r', nodata=0),
                         '0')
        self.assertEqual(colors._as_numexpr(band='a', nodata=0),
                         '0')

    def test_palette_1(self):
        # One color
        colors = ColorPalette({0: self.red})
        self.assertEqual(colors._numexpr_clauses(band='r'),
                         [('n >= 0', self.red.r)])
        self.assertEqual(colors._numexpr_clauses(band='a'),
                         [('n >= 0', self.red.a)])
        self.assertEqual(colors._as_numexpr(band='r'),
                         'where(n >= 0, {true}, {false})'.format(
                             true=self.red.r,
                             false=ColorPalette.BACKGROUND.r
                         ))
        self.assertEqual(colors._as_numexpr(band='a'),
                         'where(n >= 0, {true}, {false})'.format(
                             true=self.red.a,
                             false=ColorPalette.BACKGROUND.a
                         ))

        # One color, with nodata value before it
        colors = ColorPalette({0: self.red})
        self.assertEqual(colors._numexpr_clauses(band='r',
                                                 nodata=float('-inf')),
                         [('n >= 0', self.red.r)])
        self.assertEqual(colors._numexpr_clauses(band='a',
                                                 nodata=float('-inf')),
                         [('n >= 0', self.red.a)])
        self.assertEqual(colors._as_numexpr(band='r', nodata=float('-inf')),
                         'where(n >= 0, {true}, {false})'.format(
                             true=self.red.r,
                             false=ColorPalette.BACKGROUND.r
                         ))
        self.assertEqual(colors._as_numexpr(band='a', nodata=float('-inf')),
                         'where(n >= 0, {true}, {false})'.format(
                             true=self.red.a,
                             false=ColorPalette.BACKGROUND.a
                         ))

        # One color, with nodata value after it
        colors = ColorPalette({0: self.red})
        self.assertEqual(colors._numexpr_clauses(band='r',
                                                 nodata=float('inf')),
                         [('n >= 0', self.red.r)])
        self.assertEqual(colors._numexpr_clauses(band='a',
                                                 nodata=float('inf')),
                         [('n >= 0', self.red.a),
                          ('n == inf', ColorPalette.BACKGROUND.a)])
        self.assertEqual(colors._as_numexpr(band='r', nodata=float('inf')),
                         'where(n >= 0, {true}, {false})'.format(
                             true=self.red.r,
                             false=ColorPalette.BACKGROUND.r
                         ))
        self.assertEqual(
            colors._as_numexpr(band='a', nodata=float('inf')),
            'where(n == inf, {false}, where(n >= 0, {true}, {false}))'.format(
                true=self.red.a,
                false=ColorPalette.BACKGROUND.a
            ))

    def test_palette_2(self):
        # Two colors
        colors = ColorPalette({0: self.red,
                               2: self.green})
        self.assertEqual(colors._numexpr_clauses(band='r'),
                         [('n >= 0', self.red.r),
                          ('n >= 2', self.green.r)])
        self.assertEqual(colors._numexpr_clauses(band='g'),
                         [('n >= 2', self.green.g)])
        self.assertEqual(colors._numexpr_clauses(band='a'),
                         [('n >= 0', self.red.a)])
        self.assertEqual(
            colors._as_numexpr(band='r'),
            'where(n >= 2, {green}, where(n >= 0, {red}, {false}))'.format(
                red=self.red.r,
                green=self.green.r,
                false=ColorPalette.BACKGROUND.r
            ))
        self.assertEqual(
            colors._as_numexpr(band='g'),
            'where(n >= 2, {green}, {false})'.format(
                green=self.green.g,
                false=ColorPalette.BACKGROUND.g
            ))
        self.assertEqual(
            colors._as_numexpr(band='a'),
            'where(n >= 0, {red}, {false})'.format(
                red=self.red.a,
                false=ColorPalette.BACKGROUND.a
            ))

        # Two colors, with a nodata value in between them
        colors = ColorPalette({0: self.red,
                               2: self.green})
        self.assertEqual(colors._numexpr_clauses(band='r', nodata=1),
                         [('n >= 0', self.red.r),
                          ('n >= 2', self.green.r)])
        self.assertEqual(colors._numexpr_clauses(band='g', nodata=1),
                         [('n >= 2', self.green.g)])
        self.assertEqual(colors._numexpr_clauses(band='a', nodata=1),
                         [('n >= 0', self.red.a),
                          ('n == 1', ColorPalette.BACKGROUND.a)])
        self.assertEqual(
            colors._as_numexpr(band='r', nodata=1),
            'where(n >= 2, {green}, where(n >= 0, {red}, {false}))'.format(
                red=self.red.r,
                green=self.green.r,
                false=ColorPalette.BACKGROUND.r
            ))
        self.assertEqual(
            colors._as_numexpr(band='g', nodata=1),
            'where(n >= 2, {green}, {false})'.format(
                green=self.green.g,
                false=ColorPalette.BACKGROUND.g
            ))
        self.assertEqual(
            colors._as_numexpr(band='a', nodata=1),
            'where(n == 1, {false}, where(n >= 0, {red}, {false}))'.format(
                red=self.red.a,
                false=ColorPalette.BACKGROUND.a
            ))

        # Two colors, with nodata value replacing one of them
        colors = ColorPalette({0: self.red,
                               2: self.green})
        self.assertEqual(colors._numexpr_clauses(band='r', nodata=0),
                         [('n >= 0', self.red.r),
                          ('n >= 2', self.green.r)])
        self.assertEqual(colors._numexpr_clauses(band='g', nodata=0),
                         [('n >= 2', self.green.g)])
        self.assertEqual(colors._numexpr_clauses(band='a', nodata=0),
                         [('n >= 0', self.red.a),
                          ('n == 0', ColorPalette.BACKGROUND.a)])
        self.assertEqual(
            colors._as_numexpr(band='r', nodata=0),
            'where(n >= 2, {green}, where(n >= 0, {red}, {false}))'.format(
                red=self.red.r,
                green=self.green.r,
                false=ColorPalette.BACKGROUND.r
            ))
        self.assertEqual(
            colors._as_numexpr(band='g', nodata=0),
            'where(n >= 2, {green}, {false})'.format(
                green=self.green.g,
                false=ColorPalette.BACKGROUND.g
            ))
        self.assertEqual(
            colors._as_numexpr(band='a', nodata=0),
            'where(n == 0, {false}, where(n >= 0, {red}, {false}))'.format(
                red=self.red.a,
                false=ColorPalette.BACKGROUND.a
            ))
