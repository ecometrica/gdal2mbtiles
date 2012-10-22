# -*- coding: utf-8 -*-

import unittest

from gdal2mbtiles.renderers import JpegRenderer, PngRenderer, TouchRenderer
from gdal2mbtiles.types import rgba
from gdal2mbtiles.utils import intmd5
from gdal2mbtiles.vips import VImage


class TestJpegRenderer(unittest.TestCase):
    def test_simple(self):
        renderer = JpegRenderer()

        # Transparent 1×1 image
        image = VImage.new_rgba(width=1, height=1,
                                ink=rgba(r=0, g=0, b=0, a=0))

        contents = renderer.render(image=image)
        self.assertEqual(intmd5(contents),
                         320855993302411795134614280716687425643)

        # Black 1×1 image
        image = VImage.new_rgba(width=1, height=1,
                                ink=rgba(r=0, g=0, b=0, a=255))

        contents = renderer.render(image=image)
        self.assertEqual(intmd5(contents),
                         320855993302411795134614280716687425643)

    def test_suffix(self):
        # Default
        renderer = JpegRenderer()
        self.assertEqual(renderer.suffix, '.jpeg')

        # Specified
        renderer = JpegRenderer(suffix='.JPEG')
        self.assertEqual(renderer.suffix, '.JPEG')


class TestPngRenderer(unittest.TestCase):
    def test_simple(self):
        # Transparent 1×1 image
        image = VImage.new_rgba(width=1, height=1,
                                ink=rgba(r=0, g=0, b=0, a=0))

        renderer = PngRenderer()
        contents = renderer.render(image=image)
        self.assertEqual(intmd5(contents),
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
        renderer = TouchRenderer()
        contents = renderer.render(image=None)
        self.assertEqual(contents, '')

    def test_suffix(self):
        # Default
        renderer = TouchRenderer()
        self.assertEqual(renderer.suffix, '')

        # Specified
        renderer = TouchRenderer(suffix='.bin')
        self.assertEqual(renderer.suffix, '.bin')
