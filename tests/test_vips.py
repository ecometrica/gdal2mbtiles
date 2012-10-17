from fnmatch import fnmatch
import os
import re
import unittest

from gdal2mbtiles.exceptions import UnalignedInputError
from gdal2mbtiles.gdal import Dataset
from gdal2mbtiles.types import XY
from gdal2mbtiles.utils import intmd5, NamedTemporaryDir, recursive_listdir
from gdal2mbtiles.vips import image_pyramid, image_slice, VImage


__dir__ = os.path.dirname(__file__)


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
                        hasher=intmd5)

            files = set(os.listdir(outputdir))
            self.assertEqual(
                files,
                set((
                    '2-1-1-99c4a766657c5b65a62ef7da9906508b.png',
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
                    '2-0-0-2884b0a95c6396d62082d18ec1bfae1d.png',
                    '2-0-1-3a32ed5c6fb3cc90250af471c285a42.png',
                    '2-0-2-18afcdf7a913666913c595c296cfd03e.png',
                    '2-0-3-c4ec8c1279fa96cd90458b77c958c998.png',
                    '2-1-0-7b0a7ac32c27ac1d945158db86cf26bf.png',
                    '2-1-1-300f6831956650386ffdd110a5d83fd8.png',
                    '2-1-2-64bd81c269c44a54b7acc6d960e693ac.png',
                    '2-1-3-eefeafcbddc5ff5eccda0b3d1201855.png',
                    '2-2-0-bb90c2ceaf024ae9171f60121fbbf0e6.png',
                    '2-2-1-da2376bbe16f8156d98e6917573e4341.png',
                    '2-2-2-aa19d8b479de0400ac766419091beca2.png',
                    '2-2-3-b696b40998a89d928ec9e35141070a00.png',
                    '2-3-0-b4ac40ff44a06433db00412be5c7402a.png',
                    '2-3-1-565ac38cb22c44d4abf435d5627c33f.png',
                    '2-3-2-58785c65e6dfa2eed8ffa72fbcd3f968.png',
                    '2-3-3-8cbdbb18dc83be0706d9a9baac5b573b.png',
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
                    '0-0-0-627aaefacc772544e88eba1fcfb3db93.png',
                    '1-0-0-fbeef8e228c567c76cbb1cd55a2f8a13.png',
                    '1-0-1-7f6ad44480a24cd5c08cc1fd3aa27c08.png',
                    '1-1-0-50e5d3dafafe48053844735c4faa4549.png',
                    '1-1-1-e6310e144fc9cd695a527bc405c52317.png',
                    '2-0-0-2884b0a95c6396d62082d18ec1bfae1d.png',
                    '2-0-1-3a32ed5c6fb3cc90250af471c285a42.png',
                    '2-0-2-18afcdf7a913666913c595c296cfd03e.png',
                    '2-0-3-c4ec8c1279fa96cd90458b77c958c998.png',
                    '2-1-0-7b0a7ac32c27ac1d945158db86cf26bf.png',
                    '2-1-1-300f6831956650386ffdd110a5d83fd8.png',
                    '2-1-2-64bd81c269c44a54b7acc6d960e693ac.png',
                    '2-1-3-eefeafcbddc5ff5eccda0b3d1201855.png',
                    '2-2-0-bb90c2ceaf024ae9171f60121fbbf0e6.png',
                    '2-2-1-da2376bbe16f8156d98e6917573e4341.png',
                    '2-2-2-aa19d8b479de0400ac766419091beca2.png',
                    '2-2-3-b696b40998a89d928ec9e35141070a00.png',
                    '2-3-0-b4ac40ff44a06433db00412be5c7402a.png',
                    '2-3-1-565ac38cb22c44d4abf435d5627c33f.png',
                    '2-3-2-58785c65e6dfa2eed8ffa72fbcd3f968.png',
                    '2-3-3-8cbdbb18dc83be0706d9a9baac5b573b.png',
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
                    '0-0-0-739d3b20e9a4b75726ea452ea328c6a2.png',
                    '1-0-0-207ceec6dbcefd8e6c9a0a0f284f42e2.png',
                    '2-1-1-8c5b02bdf31c7803bad912e28873fe69.png',
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
                    '2-0-0-2884b0a95c6396d62082d18ec1bfae1d.png',
                    '2-0-1-3a32ed5c6fb3cc90250af471c285a42.png',
                    '2-0-2-18afcdf7a913666913c595c296cfd03e.png',
                    '2-0-3-c4ec8c1279fa96cd90458b77c958c998.png',
                    '2-1-0-7b0a7ac32c27ac1d945158db86cf26bf.png',
                    '2-1-1-300f6831956650386ffdd110a5d83fd8.png',
                    '2-1-2-64bd81c269c44a54b7acc6d960e693ac.png',
                    '2-1-3-eefeafcbddc5ff5eccda0b3d1201855.png',
                    '2-2-0-bb90c2ceaf024ae9171f60121fbbf0e6.png',
                    '2-2-1-da2376bbe16f8156d98e6917573e4341.png',
                    '2-2-2-aa19d8b479de0400ac766419091beca2.png',
                    '2-2-3-b696b40998a89d928ec9e35141070a00.png',
                    '2-3-0-b4ac40ff44a06433db00412be5c7402a.png',
                    '2-3-1-565ac38cb22c44d4abf435d5627c33f.png',
                    '2-3-2-58785c65e6dfa2eed8ffa72fbcd3f968.png',
                    '2-3-3-8cbdbb18dc83be0706d9a9baac5b573b.png',
                    '3-0-0-c2bfbcd3bd8343b2bec8fbcb5ed27c5e.png',
                    '3-0-1-14122f10ab9b0d59503cc027cb659b01.png',
                    '3-0-2-20720bbc59265695cd01ad4edde7e6b6.png',
                    '3-0-3-5ea335b25bdf69533f7ef61e58cda825.png',
                    '3-0-4-ef6805ad6a35ca15224e4e3534fae669.png',
                    '3-0-5-3c1ed342ae53eb11eb145942a82b0177.png',
                    '3-0-6-a1eb3fd57a35399bfd4491c73a1b07fe.png',
                    '3-0-7-3638ab4aac715eb4d0110d74049a254f.png',
                    '3-1-0-9ced1fbcd2f44c000b1f3369d22286fc.png',
                    '3-1-1-87f82adc3e57f97c9c83a685410a430b.png',
                    '3-1-2-5236495ed41312509b408452ed3c6918.png',
                    '3-1-3-5845c075c46ff0a3e8058f460349a67b.png',
                    '3-1-4-169ce35f71fa4a7d6021d8822a70e392.png',
                    '3-1-5-6445d857b1512a5f082c0034594dbb48.png',
                    '3-1-6-964fe154fd2925a577380175cc13da2c.png',
                    '3-1-7-9ee16dcdc86e4408b070cbab16e4aee4.png',
                    '3-2-0-1bcfe20c32c3c650dab50b0ff79f7365.png',
                    '3-2-1-850dc22af2562bab28515fb4141d3088.png',
                    '3-2-2-6e03e65a33c19e695a87a7359ae4f1c0.png',
                    '3-2-3-a8a815825adddf6ff994ac4cdda34861.png',
                    '3-2-4-18eae6326fad6a15a654fafe756344a.png',
                    '3-2-5-943b4ab2b9821daeb2b64a6f284f3726.png',
                    '3-2-6-11a1425b0919710c6e679b6c1eedb632.png',
                    '3-2-7-924229f3c94bdebc5ffbc84078d2288d.png',
                    '3-3-0-1b3dd1c7626cafbca6ef8f4d3a03d50d.png',
                    '3-3-1-2b11751ad790f0d0c759961f71ca43aa.png',
                    '3-3-2-6380b12cb514795f1fb6ed8b184eb2ef.png',
                    '3-3-3-92f353aae8b15da6d0e0cbc41ecf1f4d.png',
                    '3-3-4-6d1b691081478a417c2afcc4fac04030.png',
                    '3-3-5-48147b8cd13357d21ee425dde6acdf36.png',
                    '3-3-6-10db62b5324408ad1a5170abde22a306.png',
                    '3-3-7-d8320e9b45c9dbebd389d1eb345e35f6.png',
                    '3-4-0-bb525126eed656ff9879b848dac2b164.png',
                    '3-4-1-131b2deaf2e4756f1a65828d9e46c784.png',
                    '3-4-2-cac289ab28f6f1168521a42c3a2f2b64.png',
                    '3-4-3-f05a907d57a2de879b135e1631df4880.png',
                    '3-4-4-3cd05f816cb51d8e4177bc08f4274536.png',
                    '3-4-5-4fc1962dfa6dd12545899be5e2649232.png',
                    '3-4-6-77a15b6ddf0b653cf0af8fe9d402fd20.png',
                    '3-4-7-3d51c1a53accd7045cf6f038ea0d5916.png',
                    '3-5-0-f98813c6037763e674d89dd998f4170b.png',
                    '3-5-1-9b17e063e12bf1fa8d712ac9df3d5e5c.png',
                    '3-5-2-babd85cce21470be1ee9daa88ff1bde3.png',
                    '3-5-3-76d25ecdca8d1e40d6fb24ebcefc10f4.png',
                    '3-5-4-2815b28bc750dfcf7a6b2f87b72083b3.png',
                    '3-5-5-7095d0572bc6ae68456239c915f505d4.png',
                    '3-5-6-f423d4dd1180101679d7133c6838734f.png',
                    '3-5-7-248ed141d3c11d44bda9885c71105cd6.png',
                    '3-6-0-fd9ad9d2ee1925fa5d1bf0323fe8675e.png',
                    '3-6-1-c5716c819eb6fd9f50b44c38c5a9ae6f.png',
                    '3-6-2-3222a63effd740adbd80651c24eee05f.png',
                    '3-6-3-3edd4eda045cb676d8c3248ca28a5ba.png',
                    '3-6-4-84eca20474ac04711421e990ef65ba00.png',
                    '3-6-5-e07822e1b8582f5dbc819d3998865210.png',
                    '3-6-6-547e61a53c763cef95864dc7557f8a91.png',
                    '3-6-7-a11df42b19f26f43ed65093aadd96e0f.png',
                    '3-7-0-3b11c9c6b0917dfe8d3f8bfa375ffe6a.png',
                    '3-7-1-f4b561c20a4f8615cb74d4189f2e495a.png',
                    '3-7-2-a018a7a9c0c2a95d0e2726d3f3c8d0ec.png',
                    '3-7-3-dafda0bc560a497a35f1d0a36721cda2.png',
                    '3-7-4-a2109f52305ebc77efc05725b32dc8d3.png',
                    '3-7-5-9e835e07678279af926b9f261ec9b334.png',
                    '3-7-6-f093fad23cfac92be1063b7bebe9eb58.png',
                    '3-7-7-795e7f7b59218cc7c1a038a5a62c6abe.png',
                ))
            )

    def test_upsample_symlink(self):
        with NamedTemporaryDir() as outputdir:
            zoom = 3

            dataset = Dataset(self.upsamplingfile)
            image_pyramid(inputfile=self.upsamplingfile, outputdir=outputdir,
                          max_resolution=dataset.GetNativeResolution() + zoom)

            files = set(recursive_listdir(outputdir))
            self.assertEqual(
                files,
                set([
                    '0-0-0-d1fe9e479334c8b68f6e7b6147f47c4d.png',
                    '1-0-0-d76f321ac7a1f43c1e9bec0a52773c0a.png',
                    '1-0-1-1558e31ea6ee968464a911c330ef74cb.png',
                    '1-1-0-363635055244016236d74c512857f16b.png',
                    '1-1-1-9c4a495c5665fdd06b7f7cdf715cc022.png',
                    '2-0-0-790543ee6b5c35eb1480b3db1ed54734.png',
                    '2-0-1-59b833bf6cc17e3f83cef955cb8fff86.png',
                    '2-0-2-930daf2533fdd1e69d638f0946791694.png',
                    '2-0-3-930daf2533fdd1e69d638f0946791694.png',
                    '2-1-0-41d2489eccf21bca85dc662cb424b9d1.png',
                    '2-1-1-97640867dddc74c37b98bb9c1c3c395c.png',
                    '2-1-2-5192bedb9f3e8c0b007b50f7270e4abe.png',
                    '2-1-3-930daf2533fdd1e69d638f0946791694.png',
                    '2-2-0-a9ef287c3c4d329e2a6d49a3ee586d8a.png',
                    '2-2-1-c4c6f9fcccc66d866877e930c8987ed.png',
                    '2-2-2-79c34bc3e7ec07b4e20a68d17b0f7c6d.png',
                    '2-2-3-7a149fdfb8ca95e8b2829ea7aaf1373b.png',
                    '2-3-0-5f16d517d9c0427c68fffa9c6473bc0d.png',
                    '2-3-1-f335eb24d73efe8fef969a27f622cf5d.png',
                    '2-3-2-e5425bbd8991122c2f4f8e1f00bcb205.png',
                    '2-3-3-b2bf40ab041b80820df17362a8847e68.png',
                    '3-0-0-ad6a507db06c218d12f06492a90ab71b.png',
                    '3-0-1-8cdb8a8433529628b084ceabdd2f4df4.png',
                    '3-0-2-fec258edd49fa7ea56b7e9d8ea2dedcf.png',
                    '3-0-3-930daf2533fdd1e69d638f0946791694.png',
                    '3-0-4-930daf2533fdd1e69d638f0946791694.png',
                    '3-0-5-930daf2533fdd1e69d638f0946791694.png',
                    '3-0-6-930daf2533fdd1e69d638f0946791694.png',
                    '3-0-7-930daf2533fdd1e69d638f0946791694.png',
                    '3-1-0-ad6a507db06c218d12f06492a90ab71b.png',
                    '3-1-1-8cdb8a8433529628b084ceabdd2f4df4.png',
                    '3-1-2-fec258edd49fa7ea56b7e9d8ea2dedcf.png',
                    '3-1-3-930daf2533fdd1e69d638f0946791694.png',
                    '3-1-4-930daf2533fdd1e69d638f0946791694.png',
                    '3-1-5-930daf2533fdd1e69d638f0946791694.png',
                    '3-1-6-930daf2533fdd1e69d638f0946791694.png',
                    '3-1-7-930daf2533fdd1e69d638f0946791694.png',
                    '3-2-0-ad6a507db06c218d12f06492a90ab71b.png',
                    '3-2-1-8cdb8a8433529628b084ceabdd2f4df4.png',
                    '3-2-2-fec258edd49fa7ea56b7e9d8ea2dedcf.png',
                    '3-2-3-930daf2533fdd1e69d638f0946791694.png',
                    '3-2-4-930daf2533fdd1e69d638f0946791694.png',
                    '3-2-5-930daf2533fdd1e69d638f0946791694.png',
                    '3-2-6-930daf2533fdd1e69d638f0946791694.png',
                    '3-2-7-930daf2533fdd1e69d638f0946791694.png',
                    '3-3-0-ad6a507db06c218d12f06492a90ab71b.png',
                    '3-3-1-5386c94e1c9ea0b0de73933c2316d71.png',
                    '3-3-2-d5fa340113834607e11579e8d9c494dc.png',
                    '3-3-3-842a42d789878eeabe81cad2c32eed80.png',
                    '3-3-4-9afd58965ac078b515e50b857c6be3b9.png',
                    '3-3-5-930daf2533fdd1e69d638f0946791694.png',
                    '3-3-6-930daf2533fdd1e69d638f0946791694.png',
                    '3-3-7-930daf2533fdd1e69d638f0946791694.png',
                    '3-4-0-ad6a507db06c218d12f06492a90ab71b.png',
                    '3-4-1-6b09fadd2ca27ecb9d71b2a1225779c.png',
                    '3-4-2-86857a498537a72dec0e52dd8fd19261.png',
                    '3-4-3-adb1c02fcfb5981967f916fada2f43a9.png',
                    '3-4-4-34d783f63711e4e54a665e7e8f58d8be.png',
                    '3-4-5-930daf2533fdd1e69d638f0946791694.png',
                    '3-4-6-930daf2533fdd1e69d638f0946791694.png',
                    '3-4-7-930daf2533fdd1e69d638f0946791694.png',
                    '3-5-0-ad6a507db06c218d12f06492a90ab71b.png',
                    '3-5-1-d44412bf6152915d8ed11115108aff71.png',
                    '3-5-2-b685d69600b2bad855912ce0fdb5b355.png',
                    '3-5-3-eee3e8a7a3349e21ae3129e079eb090c.png',
                    '3-5-4-17898f2cd48c799b6957faa9180b9a34.png',
                    '3-5-5-47d8a28e099742fb84cbaf1f27590148.png',
                    '3-5-6-47d8a28e099742fb84cbaf1f27590148.png',
                    '3-5-7-47d8a28e099742fb84cbaf1f27590148.png',
                    '3-6-0-ad6a507db06c218d12f06492a90ab71b.png',
                    '3-6-1-144d86da21c132ff90c2bb193935ca78.png',
                    '3-6-2-f7409d191512b8772842af0b95a5426d.png',
                    '3-6-3-a4efee8727463a4f4acc8aa37b38f1f9.png',
                    '3-6-4-4998ae16ef14049beb0a44d95ac654c2.png',
                    '3-6-5-82894a96f782d0ec1cd9b7d0413b8267.png',
                    '3-6-6-82894a96f782d0ec1cd9b7d0413b8267.png',
                    '3-6-7-82894a96f782d0ec1cd9b7d0413b8267.png',
                    '3-7-0-ad6a507db06c218d12f06492a90ab71b.png',
                    '3-7-1-ad6a507db06c218d12f06492a90ab71b.png',
                    '3-7-2-ad6a507db06c218d12f06492a90ab71b.png',
                    '3-7-3-ad6a507db06c218d12f06492a90ab71b.png',
                    '3-7-4-ad6a507db06c218d12f06492a90ab71b.png',
                    '3-7-5-ad6a507db06c218d12f06492a90ab71b.png',
                    '3-7-6-ad6a507db06c218d12f06492a90ab71b.png',
                    '3-7-7-ad6a507db06c218d12f06492a90ab71b.png',
                ])
            )

            # Test that symlinks are actually created
            same_hashes = [
                os.path.join(outputdir, f) for f in files
                if fnmatch(f, '*-930daf2533fdd1e69d638f0946791694.png')
            ]
            real_files = set([f for f in same_hashes if not os.path.islink(f)])
            self.assertTrue(len(real_files) < zoom,
                            'Too many real files: {0}'.format(real_files))

            symlinks = [f for f in same_hashes if os.path.islink(f)]
            self.assertTrue(symlinks)
            for f in symlinks:
                source = os.path.realpath(os.path.join(os.path.dirname(f),
                                                       os.readlink(f)))
                self.assertTrue(source in real_files,
                                '{0} -> {1} is not in {2}'.format(source, f,
                                                                  real_files))
