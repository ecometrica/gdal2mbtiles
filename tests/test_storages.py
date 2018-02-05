# -*- coding: utf-8 -*-

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import errno
import os
from shutil import rmtree
from tempfile import NamedTemporaryFile
import unittest

from gdal2mbtiles.mbtiles import Metadata
from gdal2mbtiles.renderers import PngRenderer, TouchRenderer
from gdal2mbtiles.storages import (MbtilesStorage,
                                   NestedFileStorage, SimpleFileStorage)
from gdal2mbtiles.gd_types import rgba
from gdal2mbtiles.utils import intmd5, NamedTemporaryDir, recursive_listdir
from gdal2mbtiles.vips import VImageAdapter


class TestSimpleFileStorage(unittest.TestCase):
    def setUp(self):
        self.tempdir = NamedTemporaryDir()
        self.outputdir = self.tempdir.__enter__()
        self.renderer = TouchRenderer(suffix='.png')
        self.storage = SimpleFileStorage(outputdir=self.outputdir,
                                         renderer=self.renderer)

    def tearDown(self):
        self.tempdir.__exit__(None, None, None)

    def test_create(self):
        # Make a new directory if it doesn't exist
        os.rmdir(self.outputdir)
        storage = SimpleFileStorage(outputdir=self.outputdir,
                                    renderer=self.renderer)
        self.assertEqual(storage.outputdir, self.outputdir)
        self.assertTrue(os.path.isdir(self.outputdir))

        # Make a duplicate directory
        SimpleFileStorage(outputdir=self.outputdir,
                          renderer=self.renderer)
        self.assertTrue(os.path.isdir(self.outputdir))

    def test_filepath(self):
        self.assertEqual(self.storage.filepath(x=0, y=1, z=2,
                                               hashed=0xdeadbeef),
                         '2-0-1-deadbeef' + self.renderer.suffix)

    def test_get_hash(self):
        image = VImageAdapter.new_rgba(width=1, height=1,
                                ink=rgba(r=0, g=0, b=0, a=0))
        self.assertEqual(self.storage.get_hash(image=image),
                         int('f1d3ff8443297732862df21dc4e57262', base=16))

    def test_save(self):
        image = VImageAdapter.new_rgba(width=1, height=1,
                                ink=rgba(r=0, g=0, b=0, a=0))
        self.storage.save(x=0, y=1, z=2, image=image)
        self.storage.save(x=1, y=0, z=2, image=image)
        self.assertEqual(set(os.listdir(self.outputdir)),
                         set([
                             '2-0-1-f1d3ff8443297732862df21dc4e57262.png',
                             '2-1-0-f1d3ff8443297732862df21dc4e57262.png'
                         ]))

        # Is this a real file?
        self.assertFalse(
            os.path.islink(os.path.join(
                self.outputdir, '2-0-1-f1d3ff8443297732862df21dc4e57262.png'
            ))
        )

        # Does the symlinking work?
        self.assertEqual(
            os.readlink(os.path.join(
                self.outputdir, '2-1-0-f1d3ff8443297732862df21dc4e57262.png'
            )),
            '2-0-1-f1d3ff8443297732862df21dc4e57262.png'
        )

    def test_symlink(self):
        # Same directory
        src = 'source'
        dst = 'destination'
        self.storage.symlink(src=src, dst=dst)
        self.assertEqual(os.listdir(self.outputdir),
                         [dst])
        self.assertEqual(os.readlink(os.path.join(self.outputdir, dst)),
                         src)

        # Subdirs
        subdir = os.path.join(self.outputdir, 'subdir')
        os.mkdir(subdir)
        self.storage.symlink(src=src, dst=os.path.join(subdir, dst))
        self.assertEqual(os.listdir(subdir),
                         [dst])
        self.assertEqual(os.readlink(os.path.join(subdir, dst)),
                         os.path.join(os.path.pardir, src))

    def test_save_border(self):
        # Western hemisphere is border
        self.storage.save_border(x=0, y=0, z=1)
        self.storage.save_border(x=0, y=1, z=1)
        self.assertEqual(set(sorted(os.listdir(self.outputdir))),
                         set(sorted([
                             '1-0-0-ec87a838931d4d5d2e94a04644788a55.png',
                             '1-0-1-ec87a838931d4d5d2e94a04644788a55.png',
                         ])))

        # Is this a real file?
        self.assertFalse(
            os.path.islink(os.path.join(
                self.outputdir, '1-0-0-ec87a838931d4d5d2e94a04644788a55.png'
            ))
        )

        # Does the symlinking work?
        self.assertEqual(
            os.readlink(os.path.join(
                self.outputdir, '1-0-1-ec87a838931d4d5d2e94a04644788a55.png'
            )),
            '1-0-0-ec87a838931d4d5d2e94a04644788a55.png'
        )


class TestNestedFileStorage(unittest.TestCase):
    def setUp(self):
        self.tempdir = NamedTemporaryDir()
        self.outputdir = self.tempdir.__enter__()
        self.renderer = TouchRenderer(suffix='.png')
        self.storage = NestedFileStorage(outputdir=self.outputdir,
                                         renderer=self.renderer)

    def tearDown(self):
        self.tempdir.__exit__(None, None, None)

    def test_create(self):
        # Make a new directory if it doesn't exist
        os.rmdir(self.outputdir)
        storage = NestedFileStorage(outputdir=self.outputdir,
                                    renderer=self.renderer)
        self.assertEqual(storage.outputdir, self.outputdir)
        self.assertTrue(os.path.isdir(self.outputdir))

        # Make a duplicate directory
        NestedFileStorage(outputdir=self.outputdir,
                          renderer=self.renderer)
        self.assertTrue(os.path.isdir(self.outputdir))

    def test_filepath(self):
        self.assertEqual(self.storage.filepath(x=0, y=1, z=2,
                                               hashed=0xdeadbeef),
                         '2/0/1' + self.renderer.suffix)

    def test_makedirs(self):
        # Cache should be empty
        self.assertFalse(self.storage.madedirs)

        self.storage.makedirs(x=0, y=1, z=2)
        self.assertEqual(set(recursive_listdir(self.outputdir)),
                         set(['2/',
                              '2/0/']))

        # Is cache populated?
        self.assertTrue(self.storage.madedirs[2][0])

        # Delete and readd without clearing cache
        rmtree(os.path.join(self.outputdir, '2'))
        self.assertEqual(os.listdir(self.outputdir), [])
        self.storage.makedirs(x=0, y=1, z=2)
        self.assertEqual(os.listdir(self.outputdir), [])

    def test_save(self):
        image = VImageAdapter.new_rgba(width=1, height=1,
                                ink=rgba(r=0, g=0, b=0, a=0))
        self.storage.save(x=0, y=1, z=2, image=image)
        self.storage.save(x=1, y=0, z=2, image=image)
        self.storage.save(x=1, y=0, z=3, image=image)
        self.assertEqual(set(recursive_listdir(self.outputdir)),
                         set(['2/',
                              '2/0/',
                              '2/0/1.png',
                              '2/1/',
                              '2/1/0.png',
                              '3/',
                              '3/1/',
                              '3/1/0.png']))

        # Is this a real file?
        self.assertFalse(
            os.path.islink(os.path.join(self.outputdir, '2', '0', '1.png'))
        )

        # Does the symlinking work?
        self.assertEqual(
            os.readlink(os.path.join(self.outputdir, '2', '1', '0.png')),
            os.path.join(os.path.pardir, '0', '1.png')
        )
        self.assertEqual(
            os.readlink(os.path.join(self.outputdir, '3', '1', '0.png')),
            os.path.join(os.path.pardir, os.path.pardir, '2', '0', '1.png')
        )

    def test_save_border(self):
        # Western hemisphere is border
        self.storage.save_border(x=0, y=0, z=1)
        self.storage.save_border(x=0, y=1, z=1)
        self.storage.save_border(x=0, y=1, z=2)
        self.assertEqual(set(recursive_listdir(self.outputdir)),
                         set([
                             '1/',
                             '1/0/',
                             '1/0/0.png',
                             '1/0/1.png',
                             '2/',
                             '2/0/',
                             '2/0/1.png',
                         ]))

        # Is this a real file?
        self.assertFalse(
            os.path.islink(os.path.join(
                self.outputdir, '1/0/0.png'
            ))
        )

        # Does the symlinking work?
        self.assertEqual(
            os.readlink(os.path.join(
                self.outputdir, '1/0/1.png'
            )),
            '0.png'
        )
        self.assertEqual(
            os.readlink(os.path.join(
                self.outputdir, '2/0/1.png'
            )),
            os.path.join(os.path.pardir, os.path.pardir, '1', '0', '0.png')
        )


class TestMbtilesStorage(unittest.TestCase):
    def setUp(self):
        self.tempfile = NamedTemporaryFile()
        # Use the PngRenderer because we want to know that callback
        # works properly.
        self.renderer = PngRenderer(png8=False, optimize=False)
        self.metadata = dict(
            name='transparent',
            type=Metadata.latest().TYPES.BASELAYER,
            version='1.0.0',
            description='Transparent World 2012',
            format=Metadata.latest().FORMATS.PNG,
        )
        self.storage = MbtilesStorage.create(renderer=self.renderer,
                                             filename=':memory:',
                                             metadata=self.metadata)

    def tearDown(self):
        try:
            self.tempfile.close()
        except OSError as e:
            if e.errno != errno.ENOENT:
                raise

    def test_create(self):
        # Make a new file if it doesn't exist
        os.remove(self.tempfile.name)
        storage = MbtilesStorage.create(renderer=self.renderer,
                                        filename=self.tempfile.name,
                                        metadata=self.metadata)
        self.assertEqual(storage.filename, self.tempfile.name)
        self.assertEqual(storage.mbtiles.metadata, self.metadata)
        self.assertTrue(os.path.isfile(self.tempfile.name))

        # Make a duplicate file
        MbtilesStorage.create(renderer=self.renderer,
                              filename=self.tempfile.name,
                              metadata=self.metadata)
        self.assertEqual(storage.filename, self.tempfile.name)
        self.assertTrue(os.path.isfile(self.tempfile.name))

    def test_get_hash(self):
        image = VImageAdapter.new_rgba(width=1, height=1,
                                ink=rgba(r=0, g=0, b=0, a=0))
        self.assertEqual(self.storage.get_hash(image=image),
                         int('f1d3ff8443297732862df21dc4e57262', base=16))

    def test_save(self):
        # We must create this on disk
        self.storage = MbtilesStorage.create(renderer=self.renderer,
                                             filename=self.tempfile.name,
                                             metadata=self.metadata)

        # Transparent 1×1 image
        image = VImageAdapter.new_rgba(width=1, height=1,
                                ink=rgba(r=0, g=0, b=0, a=0))

        # Save it twice, assuming that MBTiles will deduplicate
        self.storage.save(x=0, y=1, z=2, image=image)
        self.storage.save(x=1, y=0, z=2, image=image)

        # Assert that things were saved properly
        self.assertEqual(
            [(z, x, y, intmd5(data))
             for z, x, y, data in self.storage.mbtiles.all()],
            [
                (2, 0, 1, 89446660811628514001822794642426893173),
                (2, 1, 0, 89446660811628514001822794642426893173),
            ]
        )

        # Close the existing database.
        self.storage.mbtiles.close()

        # Re-open the created file
        storage = MbtilesStorage(renderer=self.renderer,
                                 filename=self.tempfile.name)

        # Read out of the backend
        self.assertEqual(
            [(z, x, y, intmd5(data))
             for z, x, y, data in storage.mbtiles.all()],
            [
                (2, 0, 1, 89446660811628514001822794642426893173),
                (2, 1, 0, 89446660811628514001822794642426893173),
            ]
        )

    def test_save_border(self):
        # Western hemisphere is border
        self.storage.save_border(x=0, y=0, z=1)
        self.storage.save_border(x=0, y=1, z=1)

        # Assert that things were saved properly
        self.assertEqual(
            [(z, x, y, intmd5(data))
             for z, x, y, data in self.storage.mbtiles.all()],
            [
                (1, 0, 0, 182760986852492185208562855341207287999),
                (1, 0, 1, 182760986852492185208562855341207287999),
            ]
        )
