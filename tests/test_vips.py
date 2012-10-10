from contextlib import contextmanager
import os
import re
from shutil import rmtree
from tempfile import mkdtemp
import unittest

from gdal2mbtiles.exceptions import UnalignedInputError
from gdal2mbtiles.gdal import Dataset
from gdal2mbtiles.utils import recursive_listdir
from gdal2mbtiles.vips import image_slice


__dir__ = os.path.dirname(__file__)


@contextmanager
def NamedTemporaryDir(**kwargs):
    dirname = mkdtemp(**kwargs)
    yield dirname
    rmtree(dirname, ignore_errors=True)


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
            resolution = dataset.GetNativeResolution()

            files = set(self.normalize_filenames(recursive_listdir(outputdir)))
            self.assertEqual(
                files,
                (set('{z}/{x}-{y}-hash.png'.format(z=resolution, x=x, y=y)
                    for x in range(lower_left.x, upper_right.x)
                    for y in range(lower_left.y, upper_right.y)) |
                set([str(resolution)]))
            )

    def test_aligned(self):
        with NamedTemporaryDir() as outputdir:
            image_slice(inputfile=self.alignedfile, outputdir=outputdir)
            dataset = Dataset(self.alignedfile)
            lower_left, upper_right = dataset.GetTmsExtents()
            resolution = dataset.GetNativeResolution()

            files = set(self.normalize_filenames(recursive_listdir(outputdir)))
            self.assertEqual(
                files,
                (set('{z}/{x}-{y}-hash.png'.format(z=resolution, x=x, y=y)
                     for x in range(lower_left.x, upper_right.x)
                     for y in range(lower_left.y, upper_right.y)) |
                 set([str(resolution)]))
            )

    def test_spanning(self):
        with NamedTemporaryDir() as outputdir:
            self.assertRaises(UnalignedInputError,
                              image_slice,
                              inputfile=self.spanningfile, outputdir=outputdir)
