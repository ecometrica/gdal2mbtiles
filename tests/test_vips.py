from contextlib import contextmanager
import os
import re
from shutil import rmtree
from tempfile import mkdtemp
import unittest

from gdal2mbtiles.exceptions import UnalignedInputError
from gdal2mbtiles.gdal import Dataset
from gdal2mbtiles.types import XY
from gdal2mbtiles.utils import recursive_listdir
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

    def normalize_filenames(self, filenames):
        """Returns a list of hashes in filenames with the word 'hash'."""
        return [self.file_re.sub(r'\1-hash.png', f) for f in filenames]

    def test_simple(self):
        with NamedTemporaryDir() as outputdir:
            image_slice(inputfile=self.inputfile, outputdir=outputdir)
            dataset = Dataset(self.inputfile)
            lower_left, upper_right = dataset.GetTmsExtents()

            files = set(self.normalize_filenames(os.listdir(outputdir)))
            self.assertEqual(
                files,
                set((
                    '0-0-hash.png',
                    '0-1-hash.png',
                    '0-2-hash.png',
                    '0-3-hash.png',
                    '1-0-hash.png',
                    '1-1-hash.png',
                    '1-2-hash.png',
                    '1-3-hash.png',
                    '2-0-hash.png',
                    '2-1-hash.png',
                    '2-2-hash.png',
                    '2-3-hash.png',
                    '3-0-hash.png',
                    '3-1-hash.png',
                    '3-2-hash.png',
                    '3-3-hash.png',
                ))
            )

    def test_aligned(self):
        with NamedTemporaryDir() as outputdir:
            image_slice(inputfile=self.alignedfile, outputdir=outputdir)
            dataset = Dataset(self.alignedfile)
            lower_left, upper_right = dataset.GetTmsExtents()

            files = set(self.normalize_filenames(os.listdir(outputdir)))
            self.assertEqual(
                files,
                set((
                    '1-1-hash.png',
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

    def normalize_filenames(self, filenames):
        """Returns a list of hashes in filenames with the word 'hash'."""
        return [self.file_re.sub(r'\1-hash.png', f) for f in filenames]

    def test_simple(self):
        with NamedTemporaryDir() as outputdir:
            image_pyramid(inputfile=self.inputfile, outputdir=outputdir)
            dataset = Dataset(self.inputfile)
            lower_left, upper_right = dataset.GetTmsExtents()

            files = set(self.normalize_filenames(recursive_listdir(outputdir)))
            self.assertEqual(
                files,
                set((
                    '0/',
                    '0/0-0-hash.png',
                    '1/',
                    '1/0-0-hash.png',
                    '1/0-1-hash.png',
                    '1/1-0-hash.png',
                    '1/1-1-hash.png',
                    '2/',
                    '2/0-0-hash.png',
                    '2/0-1-hash.png',
                    '2/0-2-hash.png',
                    '2/0-3-hash.png',
                    '2/1-0-hash.png',
                    '2/1-1-hash.png',
                    '2/1-2-hash.png',
                    '2/1-3-hash.png',
                    '2/2-0-hash.png',
                    '2/2-1-hash.png',
                    '2/2-2-hash.png',
                    '2/2-3-hash.png',
                    '2/3-0-hash.png',
                    '2/3-1-hash.png',
                    '2/3-2-hash.png',
                    '2/3-3-hash.png',
                ))
            )

    def test_aligned(self):
        with NamedTemporaryDir() as outputdir:
            image_pyramid(inputfile=self.alignedfile, outputdir=outputdir)
            dataset = Dataset(self.alignedfile)
            lower_left, upper_right = dataset.GetTmsExtents()

            files = set(self.normalize_filenames(recursive_listdir(outputdir)))
            self.assertEqual(
                files,
                set((
                    '0/',
                    '0/0-0-hash.png',
                    '1/',
                    '1/0-0-hash.png',
                    '2/',
                    '2/1-1-hash.png',
                ))
            )

    def test_spanning(self):
        with NamedTemporaryDir() as outputdir:
            self.assertRaises(UnalignedInputError,
                              image_pyramid,
                              inputfile=self.spanningfile, outputdir=outputdir)
