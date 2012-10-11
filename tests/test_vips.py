from contextlib import contextmanager
import os
import re
from shutil import rmtree
from tempfile import mkdtemp
import unittest

from gdal2mbtiles.exceptions import UnalignedInputError
from gdal2mbtiles.gdal import Dataset
from gdal2mbtiles.types import XY
from gdal2mbtiles.utils import intmd5, recursive_listdir
from gdal2mbtiles.vips import image_pyramid, image_slice, VImage


__dir__ = os.path.dirname(__file__)


@contextmanager
def NamedTemporaryDir(**kwargs):
    dirname = mkdtemp(**kwargs)
    yield dirname
    rmtree(dirname, ignore_errors=True)


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
        stretched = image.stretch(xscale=2.0, yscale=4.0)
        self.assertEqual(stretched.Xsize(), image.Xsize() * 2.0)
        self.assertEqual(stretched.Ysize(), image.Ysize() * 4.0)

    def test_shrink(self):
        image = VImage.new_rgba(width=16, height=16)
        shrunk = image.shrink(xscale=0.25, yscale=0.5)
        self.assertEqual(shrunk.Xsize(), image.Xsize() * 0.25)
        self.assertEqual(shrunk.Ysize(), image.Ysize() * 0.5)

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


class TestImageSlice(unittest.TestCase):
    def setUp(self):
        self.inputfile = os.path.join(__dir__, 'bluemarble.tif')
        self.alignedfile = os.path.join(__dir__, 'bluemarble-aligned-ll.tif')
        self.spanningfile = os.path.join(__dir__, 'bluemarble-spanning-ll.tif')
        self.file_re = re.compile(r'(\d+-\d+)-[0-9a-f]+\.png')

    def test_simple(self):
        with NamedTemporaryDir() as outputdir:
            image_slice(inputfile=self.inputfile, outputdir=outputdir,
                        hasher=intmd5)
            dataset = Dataset(self.inputfile)
            lower_left, upper_right = dataset.GetTmsExtents()

            files = set(os.listdir(outputdir))
            self.assertEqual(
                files,
                set((
                    '0-0-79f8c5f88c49812a4171f0f6263b01b1.png',
                    '0-1-4e1061ab62c06d63eed467cca58883d1.png',
                    '0-2-2b2617db83b03d9cd96e8a68cb07ced5.png',
                    '0-3-44b9bb8a7bbdd6b8e01df1dce701b38c.png',
                    '1-0-f1d310a7a502fece03b96acb8c704330.png',
                    '1-1-194af8a96a88d76d424382d6f7b6112a.png',
                    '1-2-1269123b2c3fd725c39c0a134f4c0e95.png',
                    '1-3-62aec6122aade3337b8ebe9f6b9540fe.png',
                    '2-0-6326c9b0cae2a8959d6afda71127dc52.png',
                    '2-1-556518834b1015c6cf9a7a90bc9ec73.png',
                    '2-2-730e6a45a495d1289f96e09b7b7731ef.png',
                    '2-3-385dac69cdbf4608469b8538a0e47e2b.png',
                    '3-0-66644871022656b835ea6cea03c3dc0f.png',
                    '3-1-c81a64912d77024b3170d7ab2fb82310.png',
                    '3-2-7ced761dd1dbe412c6f5b9511f0b291.png',
                    '3-3-3f42d6a0e36064ca452aed393a303dd1.png',
                ))
            )

    def test_aligned(self):
        with NamedTemporaryDir() as outputdir:
            image_slice(inputfile=self.alignedfile, outputdir=outputdir,
                        hasher=intmd5)
            dataset = Dataset(self.alignedfile)
            lower_left, upper_right = dataset.GetTmsExtents()

            files = set(os.listdir(outputdir))
            self.assertEqual(
                files,
                set((
                    '1-1-99c4a766657c5b65a62ef7da9906508b.png',
                ))
            )

    def test_spanning(self):
        with NamedTemporaryDir() as outputdir:
            self.assertRaises(UnalignedInputError,
                              image_slice,
                              inputfile=self.spanningfile, outputdir=outputdir)


class TestImagePyramid(unittest.TestCase):
    def setUp(self):
        self.inputfile = os.path.join(__dir__, 'bluemarble.tif')
        self.alignedfile = os.path.join(__dir__, 'bluemarble-aligned-ll.tif')
        self.spanningfile = os.path.join(__dir__, 'bluemarble-spanning-ll.tif')
        self.file_re = re.compile(r'(\d+-\d+)-[0-9a-f]+\.png')

    def test_simple(self):
        with NamedTemporaryDir() as outputdir:
            image_pyramid(inputfile=self.inputfile, outputdir=outputdir)
            dataset = Dataset(self.inputfile)
            lower_left, upper_right = dataset.GetTmsExtents()

            files = set(recursive_listdir(outputdir))
            self.assertEqual(
                files,
                set((
                    '0/',
                    '0/0-0-627aaefacc772544e88eba1fcfb3db93.png',
                    '1/',
                    '1/0-0-fbeef8e228c567c76cbb1cd55a2f8a13.png',
                    '1/0-1-7f6ad44480a24cd5c08cc1fd3aa27c08.png',
                    '1/1-0-50e5d3dafafe48053844735c4faa4549.png',
                    '1/1-1-e6310e144fc9cd695a527bc405c52317.png',
                    '2/',
                    '2/0-0-2884b0a95c6396d62082d18ec1bfae1d.png',
                    '2/0-1-3a32ed5c6fb3cc90250af471c285a42.png',
                    '2/0-2-18afcdf7a913666913c595c296cfd03e.png',
                    '2/0-3-c4ec8c1279fa96cd90458b77c958c998.png',
                    '2/1-0-7b0a7ac32c27ac1d945158db86cf26bf.png',
                    '2/1-1-300f6831956650386ffdd110a5d83fd8.png',
                    '2/1-2-64bd81c269c44a54b7acc6d960e693ac.png',
                    '2/1-3-eefeafcbddc5ff5eccda0b3d1201855.png',
                    '2/2-0-bb90c2ceaf024ae9171f60121fbbf0e6.png',
                    '2/2-1-da2376bbe16f8156d98e6917573e4341.png',
                    '2/2-2-aa19d8b479de0400ac766419091beca2.png',
                    '2/2-3-b696b40998a89d928ec9e35141070a00.png',
                    '2/3-0-b4ac40ff44a06433db00412be5c7402a.png',
                    '2/3-1-565ac38cb22c44d4abf435d5627c33f.png',
                    '2/3-2-58785c65e6dfa2eed8ffa72fbcd3f968.png',
                    '2/3-3-8cbdbb18dc83be0706d9a9baac5b573b.png',
                ))
            )

    def test_aligned(self):
        with NamedTemporaryDir() as outputdir:
            image_pyramid(inputfile=self.alignedfile, outputdir=outputdir)
            dataset = Dataset(self.alignedfile)
            lower_left, upper_right = dataset.GetTmsExtents()

            files = set(recursive_listdir(outputdir))
            self.assertEqual(
                files,
                set((
                    '0/',
                    '0/0-0-739d3b20e9a4b75726ea452ea328c6a2.png',
                    '1/',
                    '1/0-0-207ceec6dbcefd8e6c9a0a0f284f42e2.png',
                    '2/',
                    '2/1-1-8c5b02bdf31c7803bad912e28873fe69.png',
                ))
            )

    def test_spanning(self):
        with NamedTemporaryDir() as outputdir:
            self.assertRaises(UnalignedInputError,
                              image_pyramid,
                              inputfile=self.spanningfile, outputdir=outputdir)
