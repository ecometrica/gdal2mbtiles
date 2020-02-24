# -*- coding: utf-8 -*-

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import unittest
import platform

import pytest

from gdal2mbtiles.renderers import JpegRenderer, PngRenderer, TouchRenderer
from gdal2mbtiles.gd_types import rgba
from gdal2mbtiles.utils import intmd5
from gdal2mbtiles.vips import VImageAdapter

# https://bugs.python.org/issue1322
if platform.system() == 'Linux':
    import distro
    DISTRIBUTION = distro.linux_distribution()
else:
    DISTRIBUTION = platform.system_alias(
        platform.system(),
        platform.release(),
        platform.version()
    )

PNG8_OS_HASHES = {
    ('Ubuntu', '16.04', 'xenial'): 106831624867432276165545554861383631224,
    ('Ubuntu', '18.04', 'bionic'): 93909651943814796643456367818041361877,
    ('Ubuntu', '20.04', 'focal'): 226470660062402177473163372260043882022,
}

require_png8_os_hash = pytest.mark.skipif(
    DISTRIBUTION not in PNG8_OS_HASHES,
    reason="Result of png8 not specified for OS version"
)


class TestJpegRenderer(unittest.TestCase):
    def test_simple(self):
        renderer = JpegRenderer()

        # Black 1×1 image
        image = VImageAdapter.new_rgba(width=1, height=1,
                                ink=rgba(r=0, g=0, b=0, a=255))

        black = renderer.render(image=image)
        black_md5 = intmd5(black)

        # Transparent 1×1 image
        image = VImageAdapter.new_rgba(width=1, height=1,
                                ink=rgba(r=0, g=0, b=0, a=0))

        transparent = renderer.render(image=image)
        self.assertEqual(intmd5(transparent), black_md5)

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
        self.image = VImageAdapter.new_rgba(width=1, height=1,
                                     ink=rgba(r=0, g=0, b=0, a=0))

    def test_simple(self):
        renderer = PngRenderer(png8=False, optimize=False)
        contents = renderer.render(image=self.image)
        self.assertEqual(intmd5(contents),
                         89446660811628514001822794642426893173)

    def test_compression(self):
        renderer = PngRenderer(compression=1, png8=False, optimize=False)
        contents = renderer.render(image=self.image)
        self.assertEqual(intmd5(contents),
                         227024021824580215543073313661866089265)

    def test_interlace(self):
        renderer = PngRenderer(interlace=1, png8=False, optimize=False)
        contents = renderer.render(image=self.image)
        self.assertEqual(intmd5(contents),
                         197686704564132731296723533976357306757)

    def test_optimize(self):
        renderer = PngRenderer(png8=False, optimize=2)
        contents = renderer.render(image=self.image)
        self.assertEqual(intmd5(contents),
                         227024021824580215543073313661866089265)

        # Default is PNG8=False and optimize=2
        renderer = PngRenderer()
        contents = renderer.render(image=self.image)
        self.assertEqual(intmd5(contents),
                         89446660811628514001822794642426893173)

    @require_png8_os_hash
    def test_png8(self):
        content_hash = PNG8_OS_HASHES[DISTRIBUTION]
        renderer = PngRenderer(png8=True, optimize=False)
        contents = renderer.render(image=self.image)
        self.assertEqual(intmd5(contents), content_hash)

    @require_png8_os_hash
    def test_png8_optimize(self):
        content_hash = PNG8_OS_HASHES[DISTRIBUTION]
        renderer = PngRenderer(png8=True, optimize=2)
        contents = renderer.render(image=self.image)
        # same hash as test_png8 since optipng treats it as already optimised
        self.assertEqual(intmd5(contents), content_hash)

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
        self.assertEqual(contents, b'')

    def test_suffix(self):
        # Default
        renderer = TouchRenderer()
        self.assertEqual(renderer.suffix, '')

        # Specified
        renderer = TouchRenderer(suffix='.bin')
        self.assertEqual(renderer.suffix, '.bin')
