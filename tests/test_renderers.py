# -*- coding: utf-8 -*-

from tempfile import NamedTemporaryFile
import unittest

from gdal2mbtiles.renderers import PngRenderer, TouchRenderer
from gdal2mbtiles.types import rgba
from gdal2mbtiles.utils import intmd5
from gdal2mbtiles.vips import VImage


class TestPngRenderer(unittest.TestCase):
    def test_simple(self):
        with NamedTemporaryFile() as outfile:
            # Transparent 1×1 image
            image = VImage.new_rgba(width=1, height=1)
            image.draw_flood(0, 0, rgba(r=0, g=0, b=0, a=0))

            renderer = PngRenderer()
            renderer.render(image=image, filename=outfile.name)

            # Read
            outfile.seek(0)
            self.assertEqual(intmd5(outfile.read()),
                             89446660811628514001822794642426893173)

    def test_suffix(self):
        # Default
        renderer = PngRenderer()
        self.assertEqual(renderer.suffix, '.png')

        # Specified
        renderer = PngRenderer(suffix='.PNG')
        self.assertEqual(renderer.suffix, '.PNG')


class TestTouchRenderer(unittest.TestCase):
    def test_simple(self):
        with NamedTemporaryFile() as outfile:
            renderer = TouchRenderer()
            renderer.render(image=None, filename=outfile.name)

            # Read
            outfile.seek(0)
            self.assertEqual(outfile.read(), '')

    def test_suffix(self):
        # Default
        renderer = TouchRenderer()
        self.assertEqual(renderer.suffix, '')

        # Specified
        renderer = TouchRenderer(suffix='.bin')
        self.assertEqual(renderer.suffix, '.bin')
