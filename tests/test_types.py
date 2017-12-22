# -*- coding: utf-8 -*-

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import unittest

from gdal2mbtiles.gd_types import rgba


class TestRgba(unittest.TestCase):
    def test_create(self):
        self.assertEqual(rgba(0, 0, 0),
                         rgba(0, 0, 0, 255))

    def test_webcolor_named(self):
        self.assertEqual(rgba.webcolor('red'),
                         rgba(255, 0, 0, 255))
        self.assertEqual(rgba.webcolor('RED'),
                         rgba(255, 0, 0, 255))

        # http://en.wikipedia.org/wiki/The_Colour_of_Magic
        self.assertRaises(ValueError, rgba.webcolor, 'octarine')

    def test_webcolor_hex(self):
        # Abbreviated
        self.assertEqual(rgba.webcolor('#0f0'),
                         rgba(0, 255, 0, 255))
        self.assertEqual(rgba.webcolor('#0F0'),
                         rgba(0, 255, 0, 255))

        # Full
        self.assertEqual(rgba.webcolor('#0000ff'),
                         rgba(0, 0, 255, 255))
        self.assertEqual(rgba.webcolor('#0000FF'),
                         rgba(0, 0, 255, 255))

        # No hash in front
        self.assertRaises(ValueError, rgba.webcolor, '0000ff')
