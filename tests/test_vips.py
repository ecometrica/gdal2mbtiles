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
                    '3/0-0-2c40423bbcd4248f6ee779f2bc0962bc.png',
                    '3/0-1-f6ac6aabd02884bcd09996a0cefdba2f.png',
                    '3/0-2-f4ad4af21f8f4f8f6c9a10bb4a14868b.png',
                    '3/0-3-515de4afd63141a7a0f045a222cf9230.png',
                    '3/0-4-7fba020fa70784cd88b5e57ad74ea5af.png',
                    '3/0-5-f1f87b313e0ef8293ebd800b1772edb1.png',
                    '3/0-6-71fcfa4cf0086b57c4ec13ce4709b4f5.png',
                    '3/0-7-691c231f0cac58c11b9f7c4bde1e011c.png',
                    '3/1-0-ce68b95a47b4b9ceb629a8633318aed3.png',
                    '3/1-1-3587d880e803dd4f2d5a0c37d126bcb2.png',
                    '3/1-2-1eec218998537a9cbde8a23f0ecf70f.png',
                    '3/1-3-47ff8a265069be2bd053a443e1856ef8.png',
                    '3/1-4-20e81100c7608c35c5fb5444cb61aa75.png',
                    '3/1-5-f786df04352689847cd34c23d95ba6c5.png',
                    '3/1-6-194abc9d27a2f9cdf1ed73fd2a616810.png',
                    '3/1-7-4f3080b55dcb094ec66c891f25d8267e.png',
                    '3/2-0-e942bf22b48ce2efd90cb3c5c908b45e.png',
                    '3/2-1-da17dd709a5576a9e290633ef069c58d.png',
                    '3/2-2-72b22b5362479daa9ca23f554f1dc58a.png',
                    '3/2-3-adc3db9162cd4d358a8a2312aa9b1225.png',
                    '3/2-4-9b47ebe095428a4d96178516fd958b1a.png',
                    '3/2-5-b805485d0da650230b28447093b78e43.png',
                    '3/2-6-cea1d1b1c50abe8773ab906ce97695.png',
                    '3/2-7-5e6c80f6637681c3c63400d39a811f95.png',
                    '3/3-0-b38f8aa0597ee685cf1efd8ad2fc2a70.png',
                    '3/3-1-58bb4daee625a42ae76299fc7262938d.png',
                    '3/3-2-3c816fa0bcd773eb23317f6de438aa67.png',
                    '3/3-3-fde62d81ae7358006e79aaedb1f7bed3.png',
                    '3/3-4-aaeda94cbf3b7da9560f529f9ea7d574.png',
                    '3/3-5-7956c10f343fdc16a695b4b00e5cd56d.png',
                    '3/3-6-13ab6d78ee970c72525396eeaf3dc25c.png',
                    '3/3-7-691467c4652496538938031d4dfce0ef.png',
                    '3/4-0-dbc21c44cb14a0ce16c978f0470e4904.png',
                    '3/4-1-e54a65084ac06516273323453ad87cf1.png',
                    '3/4-2-6fe07eba8ea685fa02549884a8b44530.png',
                    '3/4-3-82df7d816b3b744ee149af44e45ff60.png',
                    '3/4-4-aaf860aaceb54aef91e9477e02dbf316.png',
                    '3/4-5-bc1ac204209dceceac2c3d818b5ba58c.png',
                    '3/4-6-b5bcc9a5a18c4c8315f5beaea5815ad.png',
                    '3/4-7-7b814740888c5b56c0a35a97fbcae61b.png',
                    '3/5-0-b6cc008ab79672485a126000757401ad.png',
                    '3/5-1-e38865273b2425c3953e4036c8235507.png',
                    '3/5-2-1944cec77828588240d9f0e5b84e77b6.png',
                    '3/5-3-34b0f40140816bc846a4f486ebf2f99b.png',
                    '3/5-4-948e989f4e39de5eca45c4731b867593.png',
                    '3/5-5-894cb61b400f537acedfe0ff13d471d4.png',
                    '3/5-6-2f9895a2ee7de0262f8ac6e4548a2cb7.png',
                    '3/5-7-a1a1e40578264c2c2b22e7931aa361cd.png',
                    '3/6-0-638dd3bda9a60ad72d2a0a214d794ff2.png',
                    '3/6-1-bdd8cafd27498ba25340db04b569383f.png',
                    '3/6-2-7a3cc1e1317f1c141092e7f87547565d.png',
                    '3/6-3-38e1f45a2d639501deabb791a8ec3ead.png',
                    '3/6-4-209adbf4c9586ea9da929989eb17a98.png',
                    '3/6-5-816812268b67e9f9fcf63a902ee76185.png',
                    '3/6-6-709336aa6b90710e7bc30a74a732c993.png',
                    '3/6-7-a2486d1c5ddda9ee0a713b2e965802fe.png',
                    '3/7-0-438ffc20e36cc13d33a9bda696a328e6.png',
                    '3/7-1-f48d124d11d8502e1ac8631f0faeb717.png',
                    '3/7-2-f05d64e5a0900b685c5e2ed616535d41.png',
                    '3/7-3-3460d73d7fcb5439cacb5521c1199230.png',
                    '3/7-4-66a7efd96b97247a8a5b50e72245964f.png',
                    '3/7-5-6044644b505fa40b32a6369e1906de0a.png',
                    '3/7-6-c0cdde5bccb51fdd7d0a9a49995ac1b6.png',
                    '3/7-7-321e33ff84bd92a7d397c925a1d3de85.png',
                ))
            )
