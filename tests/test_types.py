import unittest

from gdal2mbtiles.types import hcolour, rgba


class TestRgba(unittest.TestCase):
    def test_create(self):
        self.assertEqual(rgba(0, 0, 0),
                         rgba(0, 0, 0, 255))


class TestHcolour(unittest.TestCase):
    def test_named(self):
        self.assertEqual(hcolour('red'),
                         rgba(255, 0, 0, 255))
        self.assertEqual(hcolour('RED'),
                         rgba(255, 0, 0, 255))

        # http://en.wikipedia.org/wiki/The_Colour_of_Magic
        self.assertRaises(ValueError, hcolour, 'octarine')

    def test_hex(self):
        # Abbreviated
        self.assertEqual(hcolour('#0f0'),
                         rgba(0, 255, 0, 255))
        self.assertEqual(hcolour('#0F0'),
                         rgba(0, 255, 0, 255))

        # Full
        self.assertEqual(hcolour('#0000ff'),
                         rgba(0, 0, 255, 255))
        self.assertEqual(hcolour('#0000FF'),
                         rgba(0, 0, 255, 255))

        # No hash in front
        self.assertRaises(ValueError, hcolour, '0000ff')
