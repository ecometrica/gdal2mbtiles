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

        # No stretch
        stretched = image.stretch(xscale=1.0, yscale=1.0)
        self.assertEqual(stretched.Xsize(), image.Xsize())
        self.assertEqual(stretched.Ysize(), image.Ysize())

        # X direction
        stretched = image.stretch(xscale=2.0, yscale=1.0)
        self.assertEqual(stretched.Xsize(), image.Xsize() * 2.0)
        self.assertEqual(stretched.Ysize(), image.Ysize())

        # Y direction
        stretched = image.stretch(xscale=1.0, yscale=4.0)
        self.assertEqual(stretched.Xsize(), image.Xsize())
        self.assertEqual(stretched.Ysize(), image.Ysize() * 4.0)

        # Both directions
        stretched = image.stretch(xscale=2.0, yscale=4.0)
        self.assertEqual(stretched.Xsize(), image.Xsize() * 2.0)
        self.assertEqual(stretched.Ysize(), image.Ysize() * 4.0)

        # Not a power of 2
        stretched = image.stretch(xscale=3.0, yscale=5.0)
        self.assertEqual(stretched.Xsize(), image.Xsize() * 3.0)
        self.assertEqual(stretched.Ysize(), image.Ysize() * 5.0)

        # Out of bounds
        self.assertRaises(ValueError,
                          image.stretch, xscale=0.5, yscale=1.0)
        self.assertRaises(ValueError,
                          image.stretch, xscale=1.0, yscale=0.5)

    def test_shrink(self):
        image = VImage.new_rgba(width=16, height=16)

        # No shrink
        shrunk = image.shrink(xscale=1.0, yscale=1.0)
        self.assertEqual(shrunk.Xsize(), image.Xsize())
        self.assertEqual(shrunk.Ysize(), image.Ysize())

        # X direction
        shrunk = image.shrink(xscale=0.25, yscale=1.0)
        self.assertEqual(shrunk.Xsize(), image.Xsize() * 0.25)
        self.assertEqual(shrunk.Ysize(), image.Ysize())

        # Y direction
        shrunk = image.shrink(xscale=1.0, yscale=0.5)
        self.assertEqual(shrunk.Xsize(), image.Xsize())
        self.assertEqual(shrunk.Ysize(), image.Ysize() * 0.5)

        # Both directions
        shrunk = image.shrink(xscale=0.25, yscale=0.5)
        self.assertEqual(shrunk.Xsize(), image.Xsize() * 0.25)
        self.assertEqual(shrunk.Ysize(), image.Ysize() * 0.5)

        # Not a power of 2
        shrunk = image.shrink(xscale=0.1, yscale=0.2)
        self.assertEqual(shrunk.Xsize(), int(image.Xsize() * 0.1))
        self.assertEqual(shrunk.Ysize(), int(image.Ysize() * 0.2))

        # Out of bounds
        self.assertRaises(ValueError,
                          image.shrink, xscale=0.0, yscale=1.0)
        self.assertRaises(ValueError,
                          image.shrink, xscale=2.0, yscale=1.0)
        self.assertRaises(ValueError,
                          image.shrink, xscale=1.0, yscale=0.0)
        self.assertRaises(ValueError,
                          image.shrink, xscale=1.0, yscale=2.0)

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
        self.upsamplingfile = os.path.join(__dir__, 'upsampling.tif')
        self.file_re = re.compile(r'(\d+-\d+)-[0-9a-f]+\.png')

    def test_simple(self):
        with NamedTemporaryDir() as outputdir:
            # Native resolution only
            image_pyramid(inputfile=self.inputfile, outputdir=outputdir)

            files = set(recursive_listdir(outputdir))
            self.assertEqual(
                files,
                set((
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

    def test_downsample(self):
        with NamedTemporaryDir() as outputdir:
            image_pyramid(inputfile=self.inputfile, outputdir=outputdir,
                          min_resolution=0)

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

    def test_downsample_aligned(self):
        with NamedTemporaryDir() as outputdir:
            image_pyramid(inputfile=self.alignedfile, outputdir=outputdir,
                          min_resolution=0)

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

    def test_downsample_spanning(self):
        with NamedTemporaryDir() as outputdir:
            self.assertRaises(UnalignedInputError,
                              image_pyramid,
                              inputfile=self.spanningfile, outputdir=outputdir,
                              min_resolution=0)

    def test_upsample(self):
        with NamedTemporaryDir() as outputdir:
            dataset = Dataset(self.inputfile)
            image_pyramid(inputfile=self.inputfile, outputdir=outputdir,
                          max_resolution=dataset.GetNativeResolution() + 1)

            files = set(recursive_listdir(outputdir))
            self.assertEqual(
                files,
                set((
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
                    '3/',
                    '3/0-0-d73f9c492a925f7e128c974eaadf286f.png',
                    '3/0-1-1147c955fdea6e44d4469d8158016642.png',
                    '3/0-2-a5a767942004e52e2c61ff857f4bf198.png',
                    '3/0-3-b40396be19889ee85cbc391a9df37428.png',
                    '3/0-4-72da9cb7800c863d9970cbe3b52f5e84.png',
                    '3/0-5-8652f623de9436653425600ba4dc66fe.png',
                    '3/0-6-abf5090f37636743cb950bc197d2205f.png',
                    '3/0-7-15419e36360000d07d3455b954f9517.png',
                    '3/1-0-752c36106840beeb87e5375a80d965ac.png',
                    '3/1-1-9368100619528b438c2ea8ba528393af.png',
                    '3/1-2-caca3b3314a5ae73589820f4083b4dc6.png',
                    '3/1-3-9c2580338424b0204a4a7810d015ffd7.png',
                    '3/1-4-855d00a911979f0ccdf60ebd93c1b91b.png',
                    '3/1-5-46c542abec8b744a562dcc1e579a7f72.png',
                    '3/1-6-eeeb79a272edcd770197335cb9d13f74.png',
                    '3/1-7-bc1ff9f09b10451361ca06a01ebac61e.png',
                    '3/2-0-14b73bb1167799aba8c62ef83a3b5193.png',
                    '3/2-1-bf75eaad897bab2085274f6ff69b5837.png',
                    '3/2-2-cad7530db77e6871320b2ffb15145e8d.png',
                    '3/2-3-eb651cb2336fbb9fff1f5050cc473406.png',
                    '3/2-4-2f8d9c13e1f66708c2f4bad94df6321f.png',
                    '3/2-5-bbe07066b2b7cca2887d795db9187eea.png',
                    '3/2-6-43dd34655c022e1e122634e399090e0c.png',
                    '3/2-7-e1602171347a72b3c3472302d4690c4d.png',
                    '3/3-0-4bfe4550bab33f9e61327fe4d79c7f9b.png',
                    '3/3-1-e0c280809cc9d4c872249e617347f238.png',
                    '3/3-2-144ab56c5da6fbd2e2e5cbed7f9b2545.png',
                    '3/3-3-aa4471890d96d39dc34fcb58e862eb86.png',
                    '3/3-4-b185ea411afa13eed8c368bbca157427.png',
                    '3/3-5-4fc366d8f2d46f32df065b3c22ef3a9e.png',
                    '3/3-6-4a6a874b0e2aeff7f05bfc8ed174785e.png',
                    '3/3-7-b7f753453cc8fd23c54006ca85841eb0.png',
                    '3/4-0-49c096f736d7293bf2f9ee9da10c8e8c.png',
                    '3/4-1-e1f1cf14d90139f6f7cdfeb199f2db46.png',
                    '3/4-2-2ff16d375b00cbfe575c007bf09b59e7.png',
                    '3/4-3-33e60f8117ff0b3c1a0dabea6c641f93.png',
                    '3/4-4-6c363ebb6908635666bdf1befe9818bb.png',
                    '3/4-5-982cc97629372affeba6f4f6661bd34b.png',
                    '3/4-6-c0290013901d9dae10047d2ada11a074.png',
                    '3/4-7-b6a41ccc489289d0ac1ebaa738d1f9da.png',
                    '3/5-0-1fe95585a6f8cb4111eafdf1219f80c6.png',
                    '3/5-1-274217387ec50c5442482f7ab8f5ae46.png',
                    '3/5-2-a13501ef59882ccf9b9ff8ce950b9360.png',
                    '3/5-3-fb1743a6a2743da26f3143374645d58a.png',
                    '3/5-4-1aa3608f043933a231eb2591ad101b7c.png',
                    '3/5-5-9b5a63c032869114483435c7c2760a03.png',
                    '3/5-6-9411847a494c599e407edd91363fd22d.png',
                    '3/5-7-fd24f2e1a2d7abf0824905a80791b5f1.png',
                    '3/6-0-a25815711266cb939b664cd4cd2a90c3.png',
                    '3/6-1-ed699d5a638b17603c17433119c14c5a.png',
                    '3/6-2-8ece8bc1b94e0c15fe85813259a58a21.png',
                    '3/6-3-6c890ac65368a21f50c82f289f55bc5f.png',
                    '3/6-4-c57d9f9cf836e9bf770db3fed027e78b.png',
                    '3/6-5-167cb56a031b36892c844dc179c3ab15.png',
                    '3/6-6-a1a967a6aac39fdbda3bbdd4bdae50da.png',
                    '3/6-7-c110d34d5fe83311544c30e4693887de.png',
                    '3/7-0-75bb056dcd2d86e5deb38653d2f9caee.png',
                    '3/7-1-942bac25c968851e1117e3cbdaf02b23.png',
                    '3/7-2-b8d30ba7453c60ef9b914f8d08da295a.png',
                    '3/7-3-9d613d7e4a4589c9d2ffc34fc2213985.png',
                    '3/7-4-bf0e658bae8fbcfb3f7ac1cf186ee6f1.png',
                    '3/7-5-510493d6de30bc83dd8de8a18e4797c3.png',
                    '3/7-6-23d5a2b400f44505b126c6e428cc3dbb.png',
                    '3/7-7-aec8102ba8d9fab22550a6fa41f0f725.png',
                ))
            )

    def test_upsample_symlink(self):
        with NamedTemporaryDir() as outputdir:
            dataset = Dataset(self.upsamplingfile)
            image_pyramid(inputfile=self.upsamplingfile, outputdir=outputdir,
                          max_resolution=dataset.GetNativeResolution() + 3)

            files = set(recursive_listdir(outputdir))
            self.assertEqual(
                files,
                set([
                    '0/',
                    '0/0-0-d1fe9e479334c8b68f6e7b6147f47c4d.png',
                    '1/',
                    '1/0-0-12f22c8acea1bcde3ab526a6edd49d0f.png',
                    '1/0-1-1558e31ea6ee968464a911c330ef74cb.png',
                    '1/1-0-466d675015b725d42171a84e35b95c5b.png',
                    '1/1-1-397bb4dbb86ffac66a0a3fb206194eb5.png',
                    '2/',
                    '2/0-0-2737a10198e38b6086d42b32442874a7.png',
                    '2/0-1-855f8e6bad98534f518ae66ce80dbbbc.png',
                    '2/0-2-930daf2533fdd1e69d638f0946791694.png',
                    '2/0-3-930daf2533fdd1e69d638f0946791694.png',
                    '2/1-0-aa1f82ce619b8df5c3e54f3fdf00451b.png',
                    '2/1-1-a185dae80b32dd4f538d651c9c74c9cf.png',
                    '2/1-2-852cc7e731748d030ecad2dbe8b31069.png',
                    '2/1-3-930daf2533fdd1e69d638f0946791694.png',
                    '2/2-0-346f43e49d14cc328b4741ad9164b872.png',
                    '2/2-1-b9e25c00b260df76908660e6b7c4a8ba.png',
                    '2/2-2-cdb30fd4e4d927b43f0f9141020a7af9.png',
                    '2/2-3-e585a652f0e86c1b520df82b9bc2558a.png',
                    '2/3-0-246632bf14371e996b02f729f585b586.png',
                    '2/3-1-dcb681e18b9acf677ce9a72642d9e04f.png',
                    '2/3-2-be311451a86bd4b3c24b00498a9d9065.png',
                    '2/3-3-36e53036a28093c079f22a27d4e94421.png',
                    '3/',
                    '3/0-0-ad6a507db06c218d12f06492a90ab71b.png',
                    '3/0-1-42ed0b9b202d5e174f7544fe4f688d2f.png',
                    '3/0-2-da88c8c3d8aa1c4ddf66de27be36dd3a.png',
                    '3/0-3-930daf2533fdd1e69d638f0946791694.png',
                    '3/0-4-930daf2533fdd1e69d638f0946791694.png',
                    '3/0-5-930daf2533fdd1e69d638f0946791694.png',
                    '3/0-6-930daf2533fdd1e69d638f0946791694.png',
                    '3/0-7-930daf2533fdd1e69d638f0946791694.png',
                    '3/1-0-ad6a507db06c218d12f06492a90ab71b.png',
                    '3/1-1-42ed0b9b202d5e174f7544fe4f688d2f.png',
                    '3/1-2-da88c8c3d8aa1c4ddf66de27be36dd3a.png',
                    '3/1-3-930daf2533fdd1e69d638f0946791694.png',
                    '3/1-4-930daf2533fdd1e69d638f0946791694.png',
                    '3/1-5-930daf2533fdd1e69d638f0946791694.png',
                    '3/1-6-930daf2533fdd1e69d638f0946791694.png',
                    '3/1-7-930daf2533fdd1e69d638f0946791694.png',
                    '3/2-0-ad6a507db06c218d12f06492a90ab71b.png',
                    '3/2-1-42ed0b9b202d5e174f7544fe4f688d2f.png',
                    '3/2-2-da88c8c3d8aa1c4ddf66de27be36dd3a.png',
                    '3/2-3-930daf2533fdd1e69d638f0946791694.png',
                    '3/2-4-930daf2533fdd1e69d638f0946791694.png',
                    '3/2-5-930daf2533fdd1e69d638f0946791694.png',
                    '3/2-6-930daf2533fdd1e69d638f0946791694.png',
                    '3/2-7-930daf2533fdd1e69d638f0946791694.png',
                    '3/3-0-ad6a507db06c218d12f06492a90ab71b.png',
                    '3/3-1-4878177556f00ecd6fa0cc6defd6799e.png',
                    '3/3-2-9f1be404c00d79e2f5078fbb1619fce3.png',
                    '3/3-3-7a9cfa9a7999a6a00a7067b81ec56e09.png',
                    '3/3-4-e8471bed6af98a826c039d462158cdc0.png',
                    '3/3-5-930daf2533fdd1e69d638f0946791694.png',
                    '3/3-6-930daf2533fdd1e69d638f0946791694.png',
                    '3/3-7-930daf2533fdd1e69d638f0946791694.png',
                    '3/4-0-ad6a507db06c218d12f06492a90ab71b.png',
                    '3/4-1-48f92a409799bc4209484302f642e292.png',
                    '3/4-2-27453258f825e513d74a20d90fa0fd63.png',
                    '3/4-3-63df4d8e209128aa23232c9e0891ace2.png',
                    '3/4-4-9e060d484e543a59b53797a12bc99ee9.png',
                    '3/4-5-930daf2533fdd1e69d638f0946791694.png',
                    '3/4-6-930daf2533fdd1e69d638f0946791694.png',
                    '3/4-7-930daf2533fdd1e69d638f0946791694.png',
                    '3/5-0-ad6a507db06c218d12f06492a90ab71b.png',
                    '3/5-1-71da0e2336959a3ae552a85864e788ad.png',
                    '3/5-2-77681df723660005e1e8baddf3229a60.png',
                    '3/5-3-51995cac376ae926b9f98f10a0e895cf.png',
                    '3/5-4-b6a4498eb6b44c32c0d44fa91ee9fbee.png',
                    '3/5-5-173f0117eb96895b2329977f163b9ce3.png',
                    '3/5-6-173f0117eb96895b2329977f163b9ce3.png',
                    '3/5-7-173f0117eb96895b2329977f163b9ce3.png',
                    '3/6-0-ad6a507db06c218d12f06492a90ab71b.png',
                    '3/6-1-82d8c77133511d2bb92deaf8395f281d.png',
                    '3/6-2-af397ecfe9a977bf78e4335873741d5e.png',
                    '3/6-3-9256379f0989e0e1dea800300cd5667e.png',
                    '3/6-4-c5886981b9bbc5d2bf28de3126282ef5.png',
                    '3/6-5-64e091a72968f0d152288b579070d280.png',
                    '3/6-6-64e091a72968f0d152288b579070d280.png',
                    '3/6-7-64e091a72968f0d152288b579070d280.png',
                    '3/7-0-ad6a507db06c218d12f06492a90ab71b.png',
                    '3/7-1-ad6a507db06c218d12f06492a90ab71b.png',
                    '3/7-2-ad6a507db06c218d12f06492a90ab71b.png',
                    '3/7-3-ad6a507db06c218d12f06492a90ab71b.png',
                    '3/7-4-ad6a507db06c218d12f06492a90ab71b.png',
                    '3/7-5-ad6a507db06c218d12f06492a90ab71b.png',
                    '3/7-6-ad6a507db06c218d12f06492a90ab71b.png',
                    '3/7-7-ad6a507db06c218d12f06492a90ab71b.png',
                ])
            )
