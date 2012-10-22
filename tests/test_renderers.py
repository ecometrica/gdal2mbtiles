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
    def setUp(self):
        # Transparent 1×1 image
        self.image = VImage.new_rgba(width=1, height=1,
                                     ink=rgba(r=0, g=0, b=0, a=0))

    def test_simple(self):
        renderer = PngRenderer(png8=False, optimize=False)
        contents = renderer.render(image=self.image)
        with open('/tmp/png/simple.png', 'wb') as f:
            f.write(contents)
        self.assertEqual(intmd5(contents),
                         89446660811628514001822794642426893173)

    def test_compression(self):
        renderer = PngRenderer(compression=0, png8=False, optimize=False)
        contents = renderer.render(image=self.image)
        with open('/tmp/png/compression.png', 'wb') as f:
            f.write(contents)
        self.assertEqual(intmd5(contents),
                         12841159377787173134361510884891270318)

    def test_interlace(self):
        renderer = PngRenderer(interlace=1, png8=False, optimize=False)
        contents = renderer.render(image=self.image)
        with open('/tmp/png/interlace.png', 'wb') as f:
            f.write(contents)
        self.assertEqual(intmd5(contents),
                         197686704564132731296723533976357306757)

    def test_png8(self):
        renderer = PngRenderer(png8=True, optimize=False)
        contents = renderer.render(image=self.image)
        with open('/tmp/png/png8.png', 'wb') as f:
            f.write(contents)
        self.assertEqual(intmd5(contents),
                         151059771043192964835020617733646275057)

    def test_optimize(self):
        renderer = PngRenderer(png8=False, optimize=2)
        contents = renderer.render(image=self.image)
        with open('/tmp/png/optimize.png', 'wb') as f:
            f.write(contents)
        self.assertEqual(intmd5(contents),
                         86467695395038688928059075665951437140)

        # Default is PNG8=False and optimize=2
        renderer = PngRenderer()
        contents = renderer.render(image=self.image)
        self.assertEqual(intmd5(contents),
                         86467695395038688928059075665951437140)

    def test_png8_optimize(self):
        renderer = PngRenderer(png8=True, optimize=2)
        contents = renderer.render(image=self.image)
        with open('/tmp/png/png8_optimize.png', 'wb') as f:
            f.write(contents)
        self.assertEqual(intmd5(contents),
                         151059771043192964835020617733646275057)

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
