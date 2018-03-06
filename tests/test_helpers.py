# -*- coding: utf-8 -*-

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import os
from tempfile import NamedTemporaryFile
import unittest

from gdal2mbtiles.exceptions import UnalignedInputError
from gdal2mbtiles.gdal import Dataset
from gdal2mbtiles.helpers import (image_mbtiles, image_pyramid, image_slice,
                                  warp_mbtiles, warp_pyramid, warp_slice)
from gdal2mbtiles.renderers import TouchRenderer
from gdal2mbtiles.storages import MbtilesStorage
from gdal2mbtiles.utils import intmd5, NamedTemporaryDir, recursive_listdir

__dir__ = os.path.dirname(__file__)


class TestImageMbtiles(unittest.TestCase):
    def setUp(self):
        self.inputfile = os.path.join(__dir__, 'bluemarble-aligned-ll.tif')

    def test_simple(self):
        with NamedTemporaryFile(suffix='.mbtiles') as outputfile:
            metadata = dict(
                name='bluemarble-aligned',
                type='baselayer',
                version='1.0.0',
                description='BlueMarble 2004-07 Aligned',
                format='png',
            )
            image_mbtiles(inputfile=self.inputfile, outputfile=outputfile.name,
                          metadata=metadata,
                          min_resolution=0, max_resolution=3,
                          renderer=TouchRenderer(suffix='.png'))
            with MbtilesStorage(renderer=None,
                                filename=outputfile.name) as storage:
                self.assertEqual(
                    set((z, x, y) for z, x, y, data in storage.mbtiles.all()),
                    set([(0, 0, 0)] +
                        [(1, x, y) for x in range(0, 2) for y in range(0, 2)] +
                        [(2, x, y) for x in range(0, 4) for y in range(0, 4)] +
                        [(3, x, y) for x in range(0, 8) for y in range(0, 8)])
                )
                self.assertEqual(
                    storage.mbtiles.metadata['bounds'],
                    '-90.0,-90.0,0.0,0.0'
                )
                self.assertEqual(storage.mbtiles.metadata['x-minzoom'], '0')
                self.assertEqual(storage.mbtiles.metadata['x-maxzoom'], '3')


class TestImagePyramid(unittest.TestCase):
    def setUp(self):
        self.inputfile = os.path.join(__dir__, 'bluemarble.tif')
        self.alignedfile = os.path.join(__dir__, 'bluemarble-aligned-ll.tif')
        self.spanningfile = os.path.join(__dir__, 'bluemarble-spanning-ll.tif')
        self.upsamplingfile = os.path.join(__dir__, 'upsampling.tif')

    def test_simple(self):
        with NamedTemporaryDir() as outputdir:
            # Native resolution only
            image_pyramid(inputfile=self.inputfile, outputdir=outputdir,
                          renderer=TouchRenderer(suffix='.png'))

            self.assertEqual(
                set(recursive_listdir(outputdir)),
                set((
                    '2/',
                    '2/0/',
                    '2/0/0.png',
                    '2/0/1.png',
                    '2/0/2.png',
                    '2/0/3.png',
                    '2/1/',
                    '2/1/0.png',
                    '2/1/1.png',
                    '2/1/2.png',
                    '2/1/3.png',
                    '2/2/',
                    '2/2/0.png',
                    '2/2/1.png',
                    '2/2/2.png',
                    '2/2/3.png',
                    '2/3/',
                    '2/3/0.png',
                    '2/3/1.png',
                    '2/3/2.png',
                    '2/3/3.png',
                ))
            )

    def test_downsample(self):
        with NamedTemporaryDir() as outputdir:
            image_pyramid(inputfile=self.inputfile, outputdir=outputdir,
                          min_resolution=0,
                          renderer=TouchRenderer(suffix='.png'))

            files = set(recursive_listdir(outputdir))
            self.assertEqual(
                files,
                set((
                    '0/',
                    '0/0/',
                    '0/0/0.png',
                    '1/',
                    '1/0/',
                    '1/0/0.png',
                    '1/0/1.png',
                    '1/1/',
                    '1/1/0.png',
                    '1/1/1.png',
                    '2/',
                    '2/0/',
                    '2/0/0.png',
                    '2/0/1.png',
                    '2/0/2.png',
                    '2/0/3.png',
                    '2/1/',
                    '2/1/0.png',
                    '2/1/1.png',
                    '2/1/2.png',
                    '2/1/3.png',
                    '2/2/',
                    '2/2/0.png',
                    '2/2/1.png',
                    '2/2/2.png',
                    '2/2/3.png',
                    '2/3/',
                    '2/3/0.png',
                    '2/3/1.png',
                    '2/3/2.png',
                    '2/3/3.png',
                ))
            )

    def test_downsample_aligned(self):
        with NamedTemporaryDir() as outputdir:
            image_pyramid(inputfile=self.alignedfile, outputdir=outputdir,
                          min_resolution=0,
                          renderer=TouchRenderer(suffix='.png'))

            files = set(recursive_listdir(outputdir))
            self.assertEqual(
                files,
                set((
                    '0/',
                    '0/0/',
                    '0/0/0.png',
                    '1/',
                    '1/0/',
                    '1/1/',
                    '1/0/0.png',
                    '2/',
                    '2/0/',
                    '2/1/',
                    '2/2/',
                    '2/3/',
                    '2/1/1.png',
                    # The following are the borders
                    '1/0/1.png',
                    '1/1/0.png',
                    '1/1/1.png',
                    '2/0/0.png',
                    '2/0/1.png',
                    '2/0/2.png',
                    '2/0/3.png',
                    '2/1/0.png',
                    '2/1/2.png',
                    '2/1/3.png',
                    '2/2/0.png',
                    '2/2/1.png',
                    '2/2/2.png',
                    '2/2/3.png',
                    '2/3/0.png',
                    '2/3/1.png',
                    '2/3/2.png',
                    '2/3/3.png',
                ))
            )

    def test_downsample_spanning(self):
        with NamedTemporaryDir() as outputdir:
            self.assertRaises(UnalignedInputError,
                              image_pyramid,
                              inputfile=self.spanningfile, outputdir=outputdir,
                              min_resolution=0,
                              renderer=TouchRenderer(suffix='.png'))

    def test_upsample(self):
        with NamedTemporaryDir() as outputdir:
            dataset = Dataset(self.inputfile)
            image_pyramid(inputfile=self.inputfile, outputdir=outputdir,
                          max_resolution=dataset.GetNativeResolution() + 1,
                          renderer=TouchRenderer(suffix='.png'))

            files = set(recursive_listdir(outputdir))
            self.assertEqual(
                files,
                set((
                    '2/',
                    '2/0/',
                    '2/0/0.png',
                    '2/0/1.png',
                    '2/0/2.png',
                    '2/0/3.png',
                    '2/1/',
                    '2/1/0.png',
                    '2/1/1.png',
                    '2/1/2.png',
                    '2/1/3.png',
                    '2/2/',
                    '2/2/0.png',
                    '2/2/1.png',
                    '2/2/2.png',
                    '2/2/3.png',
                    '2/3/',
                    '2/3/0.png',
                    '2/3/1.png',
                    '2/3/2.png',
                    '2/3/3.png',
                    '3/',
                    '3/0/',
                    '3/0/0.png',
                    '3/0/1.png',
                    '3/0/2.png',
                    '3/0/3.png',
                    '3/0/4.png',
                    '3/0/5.png',
                    '3/0/6.png',
                    '3/0/7.png',
                    '3/1/',
                    '3/1/0.png',
                    '3/1/1.png',
                    '3/1/2.png',
                    '3/1/3.png',
                    '3/1/4.png',
                    '3/1/5.png',
                    '3/1/6.png',
                    '3/1/7.png',
                    '3/2/',
                    '3/2/0.png',
                    '3/2/1.png',
                    '3/2/2.png',
                    '3/2/3.png',
                    '3/2/4.png',
                    '3/2/5.png',
                    '3/2/6.png',
                    '3/2/7.png',
                    '3/3/',
                    '3/3/0.png',
                    '3/3/1.png',
                    '3/3/2.png',
                    '3/3/3.png',
                    '3/3/4.png',
                    '3/3/5.png',
                    '3/3/6.png',
                    '3/3/7.png',
                    '3/4/',
                    '3/4/0.png',
                    '3/4/1.png',
                    '3/4/2.png',
                    '3/4/3.png',
                    '3/4/4.png',
                    '3/4/5.png',
                    '3/4/6.png',
                    '3/4/7.png',
                    '3/5/',
                    '3/5/0.png',
                    '3/5/1.png',
                    '3/5/2.png',
                    '3/5/3.png',
                    '3/5/4.png',
                    '3/5/5.png',
                    '3/5/6.png',
                    '3/5/7.png',
                    '3/6/',
                    '3/6/0.png',
                    '3/6/1.png',
                    '3/6/2.png',
                    '3/6/3.png',
                    '3/6/4.png',
                    '3/6/5.png',
                    '3/6/6.png',
                    '3/6/7.png',
                    '3/7/',
                    '3/7/0.png',
                    '3/7/1.png',
                    '3/7/2.png',
                    '3/7/3.png',
                    '3/7/4.png',
                    '3/7/5.png',
                    '3/7/6.png',
                    '3/7/7.png',
                ))
            )

    def test_upsample_symlink(self):
        with NamedTemporaryDir() as outputdir:
            zoom = 3

            dataset = Dataset(self.upsamplingfile)
            image_pyramid(inputfile=self.upsamplingfile, outputdir=outputdir,
                          max_resolution=dataset.GetNativeResolution() + zoom,
                          renderer=TouchRenderer(suffix='.png'))

            files = set(recursive_listdir(outputdir))
            self.assertEqual(
                files,
                set([
                    '0/',
                    '0/0/',
                    '0/0/0.png',
                    '1/',
                    '1/0/',
                    '1/0/0.png',
                    '1/0/1.png',
                    '1/1/',
                    '1/1/0.png',
                    '1/1/1.png',
                    '2/',
                    '2/0/',
                    '2/0/0.png',
                    '2/0/1.png',
                    '2/0/2.png',
                    '2/0/3.png',
                    '2/1/',
                    '2/1/0.png',
                    '2/1/1.png',
                    '2/1/2.png',
                    '2/1/3.png',
                    '2/2/',
                    '2/2/0.png',
                    '2/2/1.png',
                    '2/2/2.png',
                    '2/2/3.png',
                    '2/3/',
                    '2/3/0.png',
                    '2/3/1.png',
                    '2/3/2.png',
                    '2/3/3.png',
                    '3/',
                    '3/0/',
                    '3/0/0.png',
                    '3/0/1.png',
                    '3/0/2.png',
                    '3/0/3.png',
                    '3/0/4.png',
                    '3/0/5.png',
                    '3/0/6.png',
                    '3/0/7.png',
                    '3/1/',
                    '3/1/0.png',
                    '3/1/1.png',
                    '3/1/2.png',
                    '3/1/3.png',
                    '3/1/4.png',
                    '3/1/5.png',
                    '3/1/6.png',
                    '3/1/7.png',
                    '3/2/',
                    '3/2/0.png',
                    '3/2/1.png',
                    '3/2/2.png',
                    '3/2/3.png',
                    '3/2/4.png',
                    '3/2/5.png',
                    '3/2/6.png',
                    '3/2/7.png',
                    '3/3/',
                    '3/3/0.png',
                    '3/3/1.png',
                    '3/3/2.png',
                    '3/3/3.png',
                    '3/3/4.png',
                    '3/3/5.png',
                    '3/3/6.png',
                    '3/3/7.png',
                    '3/4/',
                    '3/4/0.png',
                    '3/4/1.png',
                    '3/4/2.png',
                    '3/4/3.png',
                    '3/4/4.png',
                    '3/4/5.png',
                    '3/4/6.png',
                    '3/4/7.png',
                    '3/5/',
                    '3/5/0.png',
                    '3/5/1.png',
                    '3/5/2.png',
                    '3/5/3.png',
                    '3/5/4.png',
                    '3/5/5.png',
                    '3/5/6.png',
                    '3/5/7.png',
                    '3/6/',
                    '3/6/0.png',
                    '3/6/1.png',
                    '3/6/2.png',
                    '3/6/3.png',
                    '3/6/4.png',
                    '3/6/5.png',
                    '3/6/6.png',
                    '3/6/7.png',
                    '3/7/',
                    '3/7/0.png',
                    '3/7/1.png',
                    '3/7/2.png',
                    '3/7/3.png',
                    '3/7/4.png',
                    '3/7/5.png',
                    '3/7/6.png',
                    '3/7/7.png',
                ])
            )


class TestImageSlice(unittest.TestCase):
    def setUp(self):
        self.inputfile = os.path.join(__dir__, 'bluemarble.tif')
        self.alignedfile = os.path.join(__dir__, 'bluemarble-aligned-ll.tif')
        self.spanningfile = os.path.join(__dir__, 'bluemarble-spanning-ll.tif')

    def test_simple(self):
        with NamedTemporaryDir() as outputdir:
            image_slice(inputfile=self.inputfile, outputdir=outputdir,
                        renderer=TouchRenderer(suffix='.png'))

            files = set(os.listdir(outputdir))
            self.assertEqual(
                files,
                set((
                    '2-0-0-79f8c5f88c49812a4171f0f6263b01b1.png',
                    '2-0-1-4e1061ab62c06d63eed467cca58883d1.png',
                    '2-0-2-2b2617db83b03d9cd96e8a68cb07ced5.png',
                    '2-0-3-44b9bb8a7bbdd6b8e01df1dce701b38c.png',
                    '2-1-0-f1d310a7a502fece03b96acb8c704330.png',
                    '2-1-1-194af8a96a88d76d424382d6f7b6112a.png',
                    '2-1-2-1269123b2c3fd725c39c0a134f4c0e95.png',
                    '2-1-3-62aec6122aade3337b8ebe9f6b9540fe.png',
                    '2-2-0-6326c9b0cae2a8959d6afda71127dc52.png',
                    '2-2-1-556518834b1015c6cf9a7a90bc9ec73.png',
                    '2-2-2-730e6a45a495d1289f96e09b7b7731ef.png',
                    '2-2-3-385dac69cdbf4608469b8538a0e47e2b.png',
                    '2-3-0-66644871022656b835ea6cea03c3dc0f.png',
                    '2-3-1-c81a64912d77024b3170d7ab2fb82310.png',
                    '2-3-2-7ced761dd1dbe412c6f5b9511f0b291.png',
                    '2-3-3-3f42d6a0e36064ca452aed393a303dd1.png',
                ))
            )

    def test_aligned(self):
        with NamedTemporaryDir() as outputdir:
            image_slice(inputfile=self.alignedfile, outputdir=outputdir,
                        renderer=TouchRenderer(suffix='.png'))

            files = set(os.listdir(outputdir))
            self.assertEqual(
                files,
                set((
                    '2-1-1-99c4a766657c5b65a62ef7da9906508b.png',
                    # The following are the borders
                    '2-0-0-ec87a838931d4d5d2e94a04644788a55.png',
                    '2-0-1-ec87a838931d4d5d2e94a04644788a55.png',
                    '2-0-2-ec87a838931d4d5d2e94a04644788a55.png',
                    '2-0-3-ec87a838931d4d5d2e94a04644788a55.png',
                    '2-1-0-ec87a838931d4d5d2e94a04644788a55.png',
                    '2-1-2-ec87a838931d4d5d2e94a04644788a55.png',
                    '2-1-3-ec87a838931d4d5d2e94a04644788a55.png',
                    '2-2-0-ec87a838931d4d5d2e94a04644788a55.png',
                    '2-2-1-ec87a838931d4d5d2e94a04644788a55.png',
                    '2-2-2-ec87a838931d4d5d2e94a04644788a55.png',
                    '2-2-3-ec87a838931d4d5d2e94a04644788a55.png',
                    '2-3-0-ec87a838931d4d5d2e94a04644788a55.png',
                    '2-3-1-ec87a838931d4d5d2e94a04644788a55.png',
                    '2-3-2-ec87a838931d4d5d2e94a04644788a55.png',
                    '2-3-3-ec87a838931d4d5d2e94a04644788a55.png',
                ))
            )

    def test_spanning(self):
        with NamedTemporaryDir() as outputdir:
            self.assertRaises(UnalignedInputError,
                              image_slice,
                              inputfile=self.spanningfile, outputdir=outputdir)


class TestWarpMbtiles(unittest.TestCase):
    def setUp(self):
        self.inputfile = os.path.join(__dir__, 'bluemarble-spanning-ll.tif')

    def test_simple(self):
        with NamedTemporaryFile(suffix='.mbtiles') as outputfile:
            metadata = dict(
                name='bluemarble-aligned',
                type='baselayer',
                version='1.0.0',
                description='BlueMarble 2004-07 Aligned',
                format='png',
            )
            warp_mbtiles(inputfile=self.inputfile, outputfile=outputfile.name,
                         metadata=metadata,
                         min_resolution=0, max_resolution=3,
                         renderer=TouchRenderer(suffix='.png'))
            with MbtilesStorage(renderer=None,
                                filename=outputfile.name) as storage:
                self.assertEqual(
                    set((z, x, y) for z, x, y, data in storage.mbtiles.all()),
                    set([(0, 0, 0)] +
                        [(1, x, y) for x in range(0, 2) for y in range(0, 2)] +
                        [(2, x, y) for x in range(0, 4) for y in range(0, 4)] +
                        [(3, x, y) for x in range(0, 8) for y in range(0, 8)])
                )
                self.assertEqual(
                    storage.mbtiles.metadata['bounds'],
                    '-180.0,-90.0,0.0,0.0'
                )
                self.assertEqual(storage.mbtiles.metadata['x-minzoom'], '0')
                self.assertEqual(storage.mbtiles.metadata['x-maxzoom'], '3')

    def test_zoom_offset(self):
        with NamedTemporaryFile(suffix='.mbtiles') as outputfile:
            metadata = dict(
                name='bluemarble-aligned',
                type='baselayer',
                version='1.0.0',
                description='BlueMarble 2004-07 Aligned',
                format='png',
            )
            warp_mbtiles(inputfile=self.inputfile, outputfile=outputfile.name,
                         metadata=metadata,
                         min_resolution=0, max_resolution=3, zoom_offset=2,
                         renderer=TouchRenderer(suffix='.png'))

            with MbtilesStorage(renderer=None, filename=outputfile.name) as storage:
                self.assertEqual(
                    set((z, x, y) for z, x, y, data in storage.mbtiles.all()),
                    set([(2, 0, 0)] +
                        [(3, x, y) for x in range(0, 2) for y in range(0, 2)] +
                        [(4, x, y) for x in range(0, 4) for y in range(0, 4)] +
                        [(5, x, y) for x in range(0, 8) for y in range(0, 8)])
                )
                self.assertEqual(
                    storage.mbtiles.metadata['bounds'],
                    '-180.0,-90.0,0.0,0.0'
                )
                self.assertEqual(storage.mbtiles.metadata['x-minzoom'], '2')
                self.assertEqual(storage.mbtiles.metadata['x-maxzoom'], '5')


class TestWarpPyramid(unittest.TestCase):
    def setUp(self):
        self.inputfile = os.path.join(__dir__, 'bluemarble-spanning-ll.tif')

    def test_simple(self):
        with NamedTemporaryDir() as outputdir:
            warp_pyramid(inputfile=self.inputfile, outputdir=outputdir,
                         min_resolution=0, max_resolution=3,
                         renderer=TouchRenderer(suffix='.png'))
            self.assertEqual(
                set(recursive_listdir(outputdir)),
                set((
                    '0/',
                    '0/0/',
                    '0/0/0.png',
                    '1/',
                    '1/0/',
                    '1/0/0.png',
                    '1/1/',
                    '2/',
                    '2/0/',
                    '2/0/0.png',
                    '2/0/1.png',
                    '2/1/',
                    '2/1/0.png',
                    '2/1/1.png',
                    '2/2/',
                    '2/3/',
                    '3/',
                    '3/0/',
                    '3/0/0.png',
                    '3/0/1.png',
                    '3/0/2.png',
                    '3/0/3.png',
                    '3/1/',
                    '3/1/0.png',
                    '3/1/1.png',
                    '3/1/2.png',
                    '3/1/3.png',
                    '3/2/',
                    '3/2/0.png',
                    '3/2/1.png',
                    '3/2/2.png',
                    '3/2/3.png',
                    '3/3/',
                    '3/3/0.png',
                    '3/3/1.png',
                    '3/3/2.png',
                    '3/3/3.png',
                    '3/4/',
                    '3/5/',
                    '3/6/',
                    '3/7/',
                    # The following are the borders
                    '1/0/1.png',
                    '1/1/0.png',
                    '1/1/1.png',
                    '2/0/2.png',
                    '2/0/3.png',
                    '2/1/2.png',
                    '2/1/3.png',
                    '2/2/0.png',
                    '2/2/1.png',
                    '2/2/2.png',
                    '2/2/3.png',
                    '2/3/0.png',
                    '2/3/1.png',
                    '2/3/2.png',
                    '2/3/3.png',
                    '3/0/4.png',
                    '3/0/5.png',
                    '3/0/6.png',
                    '3/0/7.png',
                    '3/1/4.png',
                    '3/1/5.png',
                    '3/1/6.png',
                    '3/1/7.png',
                    '3/2/4.png',
                    '3/2/5.png',
                    '3/2/6.png',
                    '3/2/7.png',
                    '3/3/4.png',
                    '3/3/5.png',
                    '3/3/6.png',
                    '3/3/7.png',
                    '3/4/0.png',
                    '3/4/1.png',
                    '3/4/2.png',
                    '3/4/3.png',
                    '3/4/4.png',
                    '3/4/5.png',
                    '3/4/6.png',
                    '3/4/7.png',
                    '3/5/0.png',
                    '3/5/1.png',
                    '3/5/2.png',
                    '3/5/3.png',
                    '3/5/4.png',
                    '3/5/5.png',
                    '3/5/6.png',
                    '3/5/7.png',
                    '3/6/0.png',
                    '3/6/1.png',
                    '3/6/2.png',
                    '3/6/3.png',
                    '3/6/4.png',
                    '3/6/5.png',
                    '3/6/6.png',
                    '3/6/7.png',
                    '3/7/0.png',
                    '3/7/1.png',
                    '3/7/2.png',
                    '3/7/3.png',
                    '3/7/4.png',
                    '3/7/5.png',
                    '3/7/6.png',
                    '3/7/7.png',
                ))
            )


class TestWarpSlice(unittest.TestCase):
    def setUp(self):
        self.inputfile = os.path.join(__dir__, 'bluemarble-spanning-ll.tif')

    def test_simple(self):
        with NamedTemporaryDir() as outputdir:
            warp_slice(inputfile=self.inputfile, outputdir=outputdir,
                       renderer=TouchRenderer(suffix='.png'))
            self.assertEqual(
                set(os.listdir(outputdir)),
                set((
                    '2-0-0-26ef4e5b789cdc0646ca111264851a62.png',
                    '2-0-1-a760093093243edf3557fddff32eba78.png',
                    '2-0-2-ec87a838931d4d5d2e94a04644788a55.png',
                    '2-1-0-3a60adfe5e110f70397d518d0bebc5fd.png',
                    '2-1-1-fd0f72e802c90f4c3a2cbe25b7975d1.png',
                    # The following are the borders
                    '2-0-2-ec87a838931d4d5d2e94a04644788a55.png',
                    '2-0-3-ec87a838931d4d5d2e94a04644788a55.png',
                    '2-1-2-ec87a838931d4d5d2e94a04644788a55.png',
                    '2-1-3-ec87a838931d4d5d2e94a04644788a55.png',
                    '2-2-0-ec87a838931d4d5d2e94a04644788a55.png',
                    '2-2-1-ec87a838931d4d5d2e94a04644788a55.png',
                    '2-2-2-ec87a838931d4d5d2e94a04644788a55.png',
                    '2-2-3-ec87a838931d4d5d2e94a04644788a55.png',
                    '2-3-0-ec87a838931d4d5d2e94a04644788a55.png',
                    '2-3-1-ec87a838931d4d5d2e94a04644788a55.png',
                    '2-3-2-ec87a838931d4d5d2e94a04644788a55.png',
                    '2-3-3-ec87a838931d4d5d2e94a04644788a55.png',
                ))
            )
