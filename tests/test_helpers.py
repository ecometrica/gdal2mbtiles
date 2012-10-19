from fnmatch import fnmatch
import os
import re
import unittest

from gdal2mbtiles.exceptions import UnalignedInputError
from gdal2mbtiles.gdal import Dataset
from gdal2mbtiles.helpers import (image_pyramid, image_slice, warp_pyramid,
                                  warp_slice)
from gdal2mbtiles.renderers import TouchRenderer
from gdal2mbtiles.utils import intmd5, NamedTemporaryDir, recursive_listdir

__dir__ = os.path.dirname(__file__)


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
            image_pyramid(inputfile=self.inputfile, outputdir=outputdir,
                          hasher=intmd5,
                          renderer=TouchRenderer(suffix='.png'))

            files = set(recursive_listdir(outputdir))
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

    def test_downsample(self):
        with NamedTemporaryDir() as outputdir:
            image_pyramid(inputfile=self.inputfile, outputdir=outputdir,
                          min_resolution=0, hasher=intmd5,
                          renderer=TouchRenderer(suffix='.png'))

            files = set(recursive_listdir(outputdir))
            self.assertEqual(
                files,
                set((
                    '0-0-0-d81015f4ce0e20e02d0a24644e92a5b.png',
                    '1-0-0-2375f334816ac0aefacd3e281b2479aa.png',
                    '1-0-1-bc264c28b91c75e465f0871b665df78b.png',
                    '1-1-0-73f4b28ebf24ecd78a40395c44833005.png',
                    '1-1-1-47562836ab31d83589d84d38669faf51.png',
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

    def test_downsample_aligned(self):
        with NamedTemporaryDir() as outputdir:
            image_pyramid(inputfile=self.alignedfile, outputdir=outputdir,
                          min_resolution=0, hasher=intmd5,
                          renderer=TouchRenderer(suffix='.png'))

            files = set(recursive_listdir(outputdir))
            self.assertEqual(
                files,
                set((
                    '0-0-0-a20bf623a6e62ebf4417aba45868ba60.png',
                    '1-0-0-30befce37c5f3569426ab0043c80f28d.png',
                    '2-1-1-99c4a766657c5b65a62ef7da9906508b.png',
                    # The following are the borders
                    '1-0-1-ec87a838931d4d5d2e94a04644788a55.png',
                    '1-1-0-ec87a838931d4d5d2e94a04644788a55.png',
                    '1-1-1-ec87a838931d4d5d2e94a04644788a55.png',
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

    def test_downsample_spanning(self):
        with NamedTemporaryDir() as outputdir:
            self.assertRaises(UnalignedInputError,
                              image_pyramid,
                              inputfile=self.spanningfile, outputdir=outputdir,
                              min_resolution=0, hasher=intmd5,
                              renderer=TouchRenderer(suffix='.png'))

    def test_upsample(self):
        with NamedTemporaryDir() as outputdir:
            dataset = Dataset(self.inputfile)
            image_pyramid(inputfile=self.inputfile, outputdir=outputdir,
                          max_resolution=dataset.GetNativeResolution() + 1,
                          hasher=intmd5,
                          renderer=TouchRenderer(suffix='.png'))

            files = set(recursive_listdir(outputdir))
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
                    '3-0-0-af63e42aab122a28897bedfc17d31f61.png',
                    '3-0-1-ca505cf394f742328e3aa56681c29604.png',
                    '3-0-2-784335faac47dff1334441bcd59aa2ff.png',
                    '3-0-3-f4544a7824429614942ac266257f223c.png',
                    '3-0-4-4e07d04f12a70e17fa620787504d4463.png',
                    '3-0-5-903faeeeda27f8b2ed2ed57119947a74.png',
                    '3-0-6-59c3ddfb6bc82b2cbf82fa7fc4df34c0.png',
                    '3-0-7-2e6e71be898962c89939a3413a4c834e.png',
                    '3-1-0-bbbc36a7697feecf915697ff374b1a75.png',
                    '3-1-1-54dda40831b760e0439ef599d8c90a67.png',
                    '3-1-2-bd34e201be6c16af3a153883ade10007.png',
                    '3-1-3-57ca2e480c368faf47b318a17014a419.png',
                    '3-1-4-9f5b40224edca5ab9bc5c9f4fb83e5b4.png',
                    '3-1-5-dcc718554a575fc5c8cf82f4cc5bcabe.png',
                    '3-1-6-9baaca5e3420cd514bbeea387a5ef99d.png',
                    '3-1-7-4911aa40bc5da43b445ee6061c9f2801.png',
                    '3-2-0-1f249682b45ecbdb16e1649288bdc7ee.png',
                    '3-2-1-54be09598044594e79c1e3aa28f1c88b.png',
                    '3-2-2-f352f7645b16ec549eb56a3545f03b45.png',
                    '3-2-3-24d5b0703691b0dc81b04939492ce8dd.png',
                    '3-2-4-7874efb30183b64ab4782dc24263256a.png',
                    '3-2-5-35c32e1136b18862edf4c5877e097892.png',
                    '3-2-6-25ba933861be13b3d7e91fe8e382546a.png',
                    '3-2-7-7745feb0c54580d90af072a87e0015fb.png',
                    '3-3-0-cf4aa5225950130375cbc6a69bc3cd.png',
                    '3-3-1-3a0dd2ca2d38cf713a685a41c356c17c.png',
                    '3-3-2-c8a8da8c1f033ed294b7036725eb5a3c.png',
                    '3-3-3-801b301aed5e5457740d821a8a6a0ae9.png',
                    '3-3-4-78ab00702cc45441f591716877ce986b.png',
                    '3-3-5-48b9527cdf11abf2688d9d198c00d7fd.png',
                    '3-3-6-fb5ad4b44a8448e7be57138495cba995.png',
                    '3-3-7-aa636455acfd4b929ed73665730086e4.png',
                    '3-4-0-f72b42adc3eac126a1599650c88a13e6.png',
                    '3-4-1-f00f98843634b409e2f085df30a858ca.png',
                    '3-4-2-94be219ccc9070631264d8807e30542e.png',
                    '3-4-3-43af661b38c388509a286186a10b69a8.png',
                    '3-4-4-ba2e4837c062b88c3efa6ef7b14f9efb.png',
                    '3-4-5-84b15b624209a0affc66bed5a2db4d18.png',
                    '3-4-6-fce302dfbaec0486a2bf5a03ba30016a.png',
                    '3-4-7-5d3ae6827df949708b2b5bcf5f1dcd17.png',
                    '3-5-0-f3b7f64a268887b308e4debac2eebb2d.png',
                    '3-5-1-ed3b249f1bf66c42baadb272eb1efee6.png',
                    '3-5-2-e9daf1bc490dff742033c81785f55e86.png',
                    '3-5-3-1ac0459c55cae4355d13242a968a1889.png',
                    '3-5-4-6d89fa2568bf1118d6df8c3cbadf5a23.png',
                    '3-5-5-a52246b1baa5ac7a94edd0ab2d2f01c5.png',
                    '3-5-6-bc6d2c66512ebb62d2cb06f08b449af7.png',
                    '3-5-7-64cceb0fc03ef8b418076710de427f74.png',
                    '3-6-0-6f6f98f3402d5ac3ef5e031aa0669c78.png',
                    '3-6-1-3349ad5b78ed084bf649e249fb33d44.png',
                    '3-6-2-4a492072e1a7b57707fc5e877aec0550.png',
                    '3-6-3-edfee917055c9b8a0a5a7422fd9d61a2.png',
                    '3-6-4-cb1c38bf1fed6ee8ae282014d64f73fc.png',
                    '3-6-5-9fb0eea4d1a18e84bdb3010199f0c46f.png',
                    '3-6-6-1eb390725eb175d0cfdc2e744049f2a.png',
                    '3-6-7-aa94cb0196523e7c7c8e0c545377ae4c.png',
                    '3-7-0-4f8d4f30e0e982424144fd90820064f.png',
                    '3-7-1-a5a669c81fd8eb713a6b6631fe2ac0df.png',
                    '3-7-2-735c041952d0ab7b506909fbbac046d2.png',
                    '3-7-3-16cb4b716b07a3b46716e15292d96ced.png',
                    '3-7-4-50c7d83c381d1ed1184946ad0cdcb209.png',
                    '3-7-5-2c5f53a2b65b6878b3655d2077c6cddc.png',
                    '3-7-6-d1f93c905a8fa417270f1154f93b0b60.png',
                    '3-7-7-b9d85629630bd3a34426e7a64efa86e1.png',
                ))
            )

    def test_upsample_symlink(self):
        with NamedTemporaryDir() as outputdir:
            zoom = 3

            dataset = Dataset(self.upsamplingfile)
            image_pyramid(inputfile=self.upsamplingfile, outputdir=outputdir,
                          max_resolution=dataset.GetNativeResolution() + zoom,
                          hasher=intmd5, renderer=TouchRenderer(suffix='.png'))

            files = set(recursive_listdir(outputdir))
            self.assertEqual(
                files,
                set([
                    '0-0-0-556f9a907227d16d2dd86989d6128d11.png',
                    '1-0-0-e57cfbd5e5c7bb219e46678a12924049.png',
                    '1-0-1-48fe74b4035d9f2ee91675a0a7dab574.png',
                    '1-1-0-f1c1b90b9ebca252170f05f65569f52b.png',
                    '1-1-1-70b06322d607e988124c08625d31aa22.png',
                    '2-0-0-e4cf41b885ccbe00c42108e24f746ab2.png',
                    '2-0-1-5cc463d71356fd411e6a025b5cc5ecbe.png',
                    '2-0-2-ac7cc1de12110163c497fa8cc9738e2b.png',
                    '2-0-3-ac7cc1de12110163c497fa8cc9738e2b.png',
                    '2-1-0-71c516b83d39d9f4c369551a97bef9fb.png',
                    '2-1-1-e1020a78a8de9883bdf364525c11f940.png',
                    '2-1-2-b567a1ea8547c41a44c0ff6f495d9996.png',
                    '2-1-3-ac7cc1de12110163c497fa8cc9738e2b.png',
                    '2-2-0-89547f2d1bdd549af98a4f75469603e5.png',
                    '2-2-1-27193ce1be0d7484542e36df3e7119b.png',
                    '2-2-2-ef24822167d75c6ee7321d5eeeaea3e5.png',
                    '2-2-3-7d0d1d0c99690d9a74b8ac90c8b0e35e.png',
                    '2-3-0-cfa24306a21b4dfa40bb6adfc18e970.png',
                    '2-3-1-f6299e7f61b062905db36446fe004f76.png',
                    '2-3-2-3c7bb94d8345a5f15f79353a1bb07859.png',
                    '2-3-3-47f4038d291e551d1621b7fbc1823e67.png',
                    '3-0-0-6e309edac66318b2db00c12303ae3080.png',
                    '3-0-1-41b0711540e87a846214ccfbc6bd75a3.png',
                    '3-0-2-dfcd193f2d36a47707202d719acb7bc5.png',
                    '3-0-3-ac7cc1de12110163c497fa8cc9738e2b.png',
                    '3-0-4-ac7cc1de12110163c497fa8cc9738e2b.png',
                    '3-0-5-ac7cc1de12110163c497fa8cc9738e2b.png',
                    '3-0-6-ac7cc1de12110163c497fa8cc9738e2b.png',
                    '3-0-7-ac7cc1de12110163c497fa8cc9738e2b.png',
                    '3-1-0-6e309edac66318b2db00c12303ae3080.png',
                    '3-1-1-41b0711540e87a846214ccfbc6bd75a3.png',
                    '3-1-2-dfcd193f2d36a47707202d719acb7bc5.png',
                    '3-1-3-ac7cc1de12110163c497fa8cc9738e2b.png',
                    '3-1-4-ac7cc1de12110163c497fa8cc9738e2b.png',
                    '3-1-5-ac7cc1de12110163c497fa8cc9738e2b.png',
                    '3-1-6-ac7cc1de12110163c497fa8cc9738e2b.png',
                    '3-1-7-ac7cc1de12110163c497fa8cc9738e2b.png',
                    '3-2-0-6e309edac66318b2db00c12303ae3080.png',
                    '3-2-1-41b0711540e87a846214ccfbc6bd75a3.png',
                    '3-2-2-dfcd193f2d36a47707202d719acb7bc5.png',
                    '3-2-3-ac7cc1de12110163c497fa8cc9738e2b.png',
                    '3-2-4-ac7cc1de12110163c497fa8cc9738e2b.png',
                    '3-2-5-ac7cc1de12110163c497fa8cc9738e2b.png',
                    '3-2-6-ac7cc1de12110163c497fa8cc9738e2b.png',
                    '3-2-7-ac7cc1de12110163c497fa8cc9738e2b.png',
                    '3-3-0-6e309edac66318b2db00c12303ae3080.png',
                    '3-3-1-6c181d85fccbb50cb4926841145a07be.png',
                    '3-3-2-67e746ccdbc7ba886747ee14948c2a1.png',
                    '3-3-3-8073751ad0ecc5f87a3efe7840cdd668.png',
                    '3-3-4-99693331a6b6ef23f0c4fefaf28e5e81.png',
                    '3-3-5-ac7cc1de12110163c497fa8cc9738e2b.png',
                    '3-3-6-ac7cc1de12110163c497fa8cc9738e2b.png',
                    '3-3-7-ac7cc1de12110163c497fa8cc9738e2b.png',
                    '3-4-0-6e309edac66318b2db00c12303ae3080.png',
                    '3-4-1-4d567b8b76b8c0cec9023d94229d7195.png',
                    '3-4-2-c31a810e418b91d2caacc0221c5df603.png',
                    '3-4-3-a4d04768577f081e4b61238eca29bf03.png',
                    '3-4-4-fba19ec26225d40d5b57c0641a7ce027.png',
                    '3-4-5-ac7cc1de12110163c497fa8cc9738e2b.png',
                    '3-4-6-ac7cc1de12110163c497fa8cc9738e2b.png',
                    '3-4-7-ac7cc1de12110163c497fa8cc9738e2b.png',
                    '3-5-0-6e309edac66318b2db00c12303ae3080.png',
                    '3-5-1-daf4537870e782f3958fc9efe84751b3.png',
                    '3-5-2-78e1ba0e0521f69270e59628c188c154.png',
                    '3-5-3-894f23287ac4bf9ebbc1cb2bda594631.png',
                    '3-5-4-651980687bb4dbe2210feb0cbaac2d23.png',
                    '3-5-5-628998670164f4a93dc30b9e13173169.png',
                    '3-5-6-628998670164f4a93dc30b9e13173169.png',
                    '3-5-7-628998670164f4a93dc30b9e13173169.png',
                    '3-6-0-6e309edac66318b2db00c12303ae3080.png',
                    '3-6-1-d17e7b200cebd8302d8349aea38e9777.png',
                    '3-6-2-b5e32611858aa92804b12562e174fe9e.png',
                    '3-6-3-63dd16542a18a9e18830c5d948d8f54a.png',
                    '3-6-4-c3a0dd7b9307bed2bf7463543d91c91d.png',
                    '3-6-5-702f3c83813f9f7323556887caa76c86.png',
                    '3-6-6-702f3c83813f9f7323556887caa76c86.png',
                    '3-6-7-702f3c83813f9f7323556887caa76c86.png',
                    '3-7-0-6e309edac66318b2db00c12303ae3080.png',
                    '3-7-1-6e309edac66318b2db00c12303ae3080.png',
                    '3-7-2-6e309edac66318b2db00c12303ae3080.png',
                    '3-7-3-6e309edac66318b2db00c12303ae3080.png',
                    '3-7-4-6e309edac66318b2db00c12303ae3080.png',
                    '3-7-5-6e309edac66318b2db00c12303ae3080.png',
                    '3-7-6-6e309edac66318b2db00c12303ae3080.png',
                    '3-7-7-6e309edac66318b2db00c12303ae3080.png',
                ])
            )

            # Test that symlinks are actually created
            same_hashes = [
                os.path.join(outputdir, f) for f in files
                if fnmatch(f, '*-6e309edac66318b2db00c12303ae3080.png')
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


class TestImageSlice(unittest.TestCase):
    def setUp(self):
        self.inputfile = os.path.join(__dir__, 'bluemarble.tif')
        self.alignedfile = os.path.join(__dir__, 'bluemarble-aligned-ll.tif')
        self.spanningfile = os.path.join(__dir__, 'bluemarble-spanning-ll.tif')
        self.file_re = re.compile(r'(\d+-\d+)-[0-9a-f]+\.png')

    def test_simple(self):
        with NamedTemporaryDir() as outputdir:
            image_slice(inputfile=self.inputfile, outputdir=outputdir,
                        hasher=intmd5, renderer=TouchRenderer(suffix='.png'))

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
                        hasher=intmd5, renderer=TouchRenderer(suffix='.png'))

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


class TestWarpPyramid(unittest.TestCase):
    def setUp(self):
        self.inputfile = os.path.join(__dir__, 'bluemarble-spanning-ll.tif')

    def test_simple(self):
        with NamedTemporaryDir() as outputdir:
            warp_pyramid(inputfile=self.inputfile, outputdir=outputdir,
                         min_resolution=0, max_resolution=3,
                         renderer=TouchRenderer(suffix='.png'), hasher=intmd5)
            self.assertEqual(
                set(os.listdir(outputdir)),
                set((
                    '0-0-0-cc5cff96b5fbc19e6d234f000b82a8d7.png',
                    '1-0-0-ac833511a7ce7ba2dd63128879cdcd90.png',
                    '2-0-0-26ef4e5b789cdc0646ca111264851a62.png',
                    '2-0-1-a760093093243edf3557fddff32eba78.png',
                    '2-1-0-3a60adfe5e110f70397d518d0bebc5fd.png',
                    '2-1-1-fd0f72e802c90f4c3a2cbe25b7975d1.png',
                    '3-0-0-5cfd9f8d239c01c7a816fc176b823808.png',
                    '3-0-1-71a71fa62271ba9cdf197c82c96495fd.png',
                    '3-0-2-53da1178ad53283b4394825a6194d827.png',
                    '3-0-3-84543ff0b0b91dafdb8c2ba62d417dd.png',
                    '3-1-0-9462d7456892ff231eb037fc9f9baa3b.png',
                    '3-1-1-dcb4c96902275a429384ec7187c4e819.png',
                    '3-1-2-8efe17f1a59bcaadcf2b72370dc3efa8.png',
                    '3-1-3-5e604384489ce40d2e91251f63fbf722.png',
                    '3-2-0-3dd3751e549dfbac5aa3a2451e7f0e75.png',
                    '3-2-1-392c904d35d27a514ca592e01ee7a446.png',
                    '3-2-2-106a99af2a82c6b5c23bb211db647736.png',
                    '3-2-3-be4603ecc03da7320c6c768351a7c2c3.png',
                    '3-3-0-c778d9a8ddd29a2abd059ea943c3ae22.png',
                    '3-3-1-b1b8c26a3b92ea48e76cc9b9c4d3b7fd.png',
                    '3-3-2-e42b1d10e4330d57d9ac00ce29ba93d9.png',
                    '3-3-3-cdf56e4dcf633d6d9bc1e2d5cfec11c3.png',
                    # The following are the borders
                    '1-0-1-ec87a838931d4d5d2e94a04644788a55.png',
                    '1-1-0-ec87a838931d4d5d2e94a04644788a55.png',
                    '1-1-1-ec87a838931d4d5d2e94a04644788a55.png',
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
                    '3-0-4-ec87a838931d4d5d2e94a04644788a55.png',
                    '3-0-5-ec87a838931d4d5d2e94a04644788a55.png',
                    '3-0-6-ec87a838931d4d5d2e94a04644788a55.png',
                    '3-0-7-ec87a838931d4d5d2e94a04644788a55.png',
                    '3-1-4-ec87a838931d4d5d2e94a04644788a55.png',
                    '3-1-5-ec87a838931d4d5d2e94a04644788a55.png',
                    '3-1-6-ec87a838931d4d5d2e94a04644788a55.png',
                    '3-1-7-ec87a838931d4d5d2e94a04644788a55.png',
                    '3-2-4-ec87a838931d4d5d2e94a04644788a55.png',
                    '3-2-5-ec87a838931d4d5d2e94a04644788a55.png',
                    '3-2-6-ec87a838931d4d5d2e94a04644788a55.png',
                    '3-2-7-ec87a838931d4d5d2e94a04644788a55.png',
                    '3-3-4-ec87a838931d4d5d2e94a04644788a55.png',
                    '3-3-5-ec87a838931d4d5d2e94a04644788a55.png',
                    '3-3-6-ec87a838931d4d5d2e94a04644788a55.png',
                    '3-3-7-ec87a838931d4d5d2e94a04644788a55.png',
                    '3-4-0-ec87a838931d4d5d2e94a04644788a55.png',
                    '3-4-1-ec87a838931d4d5d2e94a04644788a55.png',
                    '3-4-2-ec87a838931d4d5d2e94a04644788a55.png',
                    '3-4-3-ec87a838931d4d5d2e94a04644788a55.png',
                    '3-4-4-ec87a838931d4d5d2e94a04644788a55.png',
                    '3-4-5-ec87a838931d4d5d2e94a04644788a55.png',
                    '3-4-6-ec87a838931d4d5d2e94a04644788a55.png',
                    '3-4-7-ec87a838931d4d5d2e94a04644788a55.png',
                    '3-5-0-ec87a838931d4d5d2e94a04644788a55.png',
                    '3-5-1-ec87a838931d4d5d2e94a04644788a55.png',
                    '3-5-2-ec87a838931d4d5d2e94a04644788a55.png',
                    '3-5-3-ec87a838931d4d5d2e94a04644788a55.png',
                    '3-5-4-ec87a838931d4d5d2e94a04644788a55.png',
                    '3-5-5-ec87a838931d4d5d2e94a04644788a55.png',
                    '3-5-6-ec87a838931d4d5d2e94a04644788a55.png',
                    '3-5-7-ec87a838931d4d5d2e94a04644788a55.png',
                    '3-6-0-ec87a838931d4d5d2e94a04644788a55.png',
                    '3-6-1-ec87a838931d4d5d2e94a04644788a55.png',
                    '3-6-2-ec87a838931d4d5d2e94a04644788a55.png',
                    '3-6-3-ec87a838931d4d5d2e94a04644788a55.png',
                    '3-6-4-ec87a838931d4d5d2e94a04644788a55.png',
                    '3-6-5-ec87a838931d4d5d2e94a04644788a55.png',
                    '3-6-6-ec87a838931d4d5d2e94a04644788a55.png',
                    '3-6-7-ec87a838931d4d5d2e94a04644788a55.png',
                    '3-7-0-ec87a838931d4d5d2e94a04644788a55.png',
                    '3-7-1-ec87a838931d4d5d2e94a04644788a55.png',
                    '3-7-2-ec87a838931d4d5d2e94a04644788a55.png',
                    '3-7-3-ec87a838931d4d5d2e94a04644788a55.png',
                    '3-7-4-ec87a838931d4d5d2e94a04644788a55.png',
                    '3-7-5-ec87a838931d4d5d2e94a04644788a55.png',
                    '3-7-6-ec87a838931d4d5d2e94a04644788a55.png',
                    '3-7-7-ec87a838931d4d5d2e94a04644788a55.png',
                ))
            )


class TestWarpSlice(unittest.TestCase):
    def setUp(self):
        self.inputfile = os.path.join(__dir__, 'bluemarble-spanning-ll.tif')

    def test_simple(self):
        with NamedTemporaryDir() as outputdir:
            warp_slice(inputfile=self.inputfile, outputdir=outputdir,
                       renderer=TouchRenderer(suffix='.png'), hasher=intmd5)
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
