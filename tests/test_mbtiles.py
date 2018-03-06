# -*- coding: utf-8 -*-

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import errno
import os
from tempfile import NamedTemporaryFile
import unittest

from gdal2mbtiles.mbtiles import (InvalidFileError, MetadataKeyError,
                                  MetadataValueError, Metadata, MBTiles)


class TestMBTiles(unittest.TestCase):
    def setUp(self):
        self.tempfile = NamedTemporaryFile(suffix='.mbtiles')
        self.filename = self.tempfile.name
        self.version = '1.0'
        self.metadata = dict(
            name='transparent',
            type=Metadata.latest().TYPES.BASELAYER,
            version='1.0.0',
            description='Transparent World 2012',
        )

    def tearDown(self):
        try:
            self.tempfile.close()
        except OSError as e:
            if e.errno != errno.ENOENT:
                raise

    def test_open(self):
        with MBTiles.create(filename=self.filename,
                            metadata=self.metadata,
                            version=self.version):
            pass

        mbtiles = MBTiles(filename=self.filename)

        # Version detection
        self.assertEqual(mbtiles.version, self.version)

        # File are auto-opened
        self.assertFalse(mbtiles.closed)
        conn = mbtiles._conn

        # Open again
        self.assertNotEqual(mbtiles.open(), conn)

        # Close
        mbtiles.close()
        self.assertTrue(mbtiles.closed)

    def test_open_invalid(self):
        # Empty file
        self.assertRaises(InvalidFileError,
                          MBTiles, filename=self.filename)

        # Python file
        self.assertRaises(InvalidFileError,
                          MBTiles, filename=__file__)

        # Missing file
        self.assertRaises(IOError,
                          MBTiles, filename='/dev/missing')
        self.assertRaises(IOError,
                          MBTiles, filename='/missing')

    def test_create(self):
        # Create when filename does not exist
        os.remove(self.filename)
        mbtiles1 = MBTiles.create(filename=self.filename,
                                  metadata=self.metadata,
                                  version=self.version)
        self.assertFalse(mbtiles1.closed)

        # Create again when it exists
        mbtiles2 = MBTiles.create(filename=self.filename,
                                  metadata=self.metadata,
                                  version=self.version)
        self.assertFalse(mbtiles2.closed)

        self.assertNotEqual(mbtiles1, mbtiles2)

        # Create without version
        mbtiles3 = MBTiles.create(filename=self.filename,
                                  metadata=self.metadata)
        self.assertEqual(mbtiles3.version, self.version)

    def test_tiles(self):
        mbtiles = MBTiles.create(filename=':memory:',
                                 metadata=self.metadata,
                                 version=self.version)
        data = 'PNG image'
        hashed = hash(data)

        # Get missing tile
        self.assertEqual(mbtiles.get(x=0, y=0, z=0), None)

        # Insert tile
        mbtiles.insert(x=0, y=0, z=0, hashed=hashed, data=data)

        # Get inserted tile
        self.assertEqual(mbtiles.get(x=0, y=0, z=0), data)

        # Link tile
        mbtiles.insert(x=1, y=1, z=1, hashed=hashed)

        # Get linked tile
        self.assertEqual(mbtiles.get(x=1, y=1, z=1), data)

    def test_out_of_order_tile(self):
        mbtiles = MBTiles.create(filename=':memory:',
                                 metadata=self.metadata,
                                 version=self.version)
        data = 'PNG image'
        hashed = hash(data)

        # Link tile to nonexistent data
        mbtiles.insert(x=1, y=1, z=1, hashed=hashed)

        # Get linked tile
        self.assertEqual(mbtiles.get(x=1, y=1, z=1), None)

        # Add nonexistent data
        mbtiles.insert(x=0, y=0, z=0, hashed=hashed, data=data)

        # Get tile again
        self.assertEqual(mbtiles.get(x=1, y=1, z=1), data)

    def test_autocommit(self):
        mbtiles = MBTiles.create(filename=self.filename,
                                 metadata=self.metadata,
                                 version=self.version)
        data = 'PNG image'
        hashed = hash(data)

        # Insert tile
        mbtiles.insert(x=0, y=0, z=0, hashed=hashed, data=data)
        self.assertEqual(mbtiles.get(x=0, y=0, z=0), data)

        # Reopen
        mbtiles.open()
        self.assertEqual(mbtiles.get(x=0, y=0, z=0), data)


class TestMetadata(unittest.TestCase):
    def setUp(self):
        self.filename = ':memory:'
        self.version = '1.0'
        self.metadata = dict(
            name='transparent',
            type=Metadata.latest().TYPES.BASELAYER,
            version='1.0.0',
            description='Transparent World 2012',
        )

    def test_simple(self):
        mbtiles = MBTiles.create(filename=self.filename,
                                 metadata=self.metadata,
                                 version=self.version)
        metadata = mbtiles.metadata

        # Set
        metadata['test'] = ''
        self.assertEqual(metadata['test'], '')

        # Set again
        metadata['test'] = 'Tileset'
        self.assertEqual(metadata['test'], 'Tileset')

        # Get missing
        self.assertRaises(MetadataKeyError, metadata.__getitem__, 'missing')
        self.assertEqual(metadata.get('missing'), None)
        self.assertEqual(metadata.get('missing', False), False)

        # Contains
        self.assertTrue('test' in metadata)
        self.assertFalse('missing' in metadata)

        # Delete
        del metadata['test']
        self.assertFalse('test' in metadata)

        # Delete mandatory
        self.assertRaises(MetadataKeyError,
                          metadata.__delitem__, 'name')

        # Pop
        metadata['test'] = 'Tileset'
        self.assertEqual(metadata.pop('test'), 'Tileset')

        # Pop missing
        self.assertRaises(MetadataKeyError, metadata.pop, 'test')
        self.assertEqual(metadata.pop('test', None), None)

        # Update
        data = dict(list(self.metadata.items()),
                    name='Tileset',
                    description='This is a test tileset.')
        metadata.update(data)

        # Keys
        self.assertEqual(set(metadata.keys()), set(data.keys()))

        # Values
        self.assertEqual(set(metadata.values()), set(data.values()))

        # Items
        self.assertEqual(set(metadata.items()), set(data.items()))

        # Compare with dictionary
        self.assertEqual(metadata, data)

    def test_validate_1_0(self):
        version = '1.0'
        metadata = dict(
            name='transparent',
            type=Metadata.all()[version].TYPES.BASELAYER,
            version='1.0.0',
        )

        self.assertRaises(MetadataKeyError,
                          MBTiles.create, filename=self.filename, metadata={},
                          version=version)
        metadata.update(dict(
            description='Transparent World 2012',
        ))

        with MBTiles.create(filename=self.filename,
                            metadata=metadata) as mbtiles:
            self.assertEqual(mbtiles.version, version)

        with MBTiles.create(filename=self.filename,
                            metadata=metadata,
                            version=version) as mbtiles:
            metadata = mbtiles.metadata
            self.assertRaises(MetadataKeyError,
                              metadata.__delitem__, 'name')
            self.assertRaises(MetadataKeyError,
                              metadata.__delitem__, 'type')
            self.assertRaises(MetadataKeyError,
                              metadata.__delitem__, 'version')
            self.assertRaises(MetadataKeyError,
                              metadata.__delitem__, 'description')

            metadata['type'] = metadata.TYPES.OVERLAY
            self.assertEqual(metadata['type'], 'overlay')
            metadata['type'] = metadata.TYPES.BASELAYER
            self.assertEqual(metadata['type'], 'baselayer')
            self.assertRaises(MetadataValueError,
                              metadata.__setitem__, 'type', 'invalid')

    def test_validate_1_1(self):
        version = '1.1'
        metadata = dict(
            name='transparent',
            type=Metadata.all()[version].TYPES.BASELAYER,
            version='1.0.0',
            description='Transparent World 2012',
        )

        self.assertRaises(MetadataKeyError,
                          MBTiles.create, filename=self.filename,
                          metadata=self.metadata, version=version)
        metadata.update(dict(
            format=Metadata.all()[version].FORMATS.PNG,
            bounds='-180.0,-85,180,85',
        ))

        with MBTiles.create(filename=self.filename,
                            metadata=metadata,
                            version=version) as mbtiles:
            metadata = mbtiles.metadata
            self.assertRaises(MetadataKeyError,
                              metadata.__delitem__, 'name')
            self.assertRaises(MetadataKeyError,
                              metadata.__delitem__, 'type')
            self.assertRaises(MetadataKeyError,
                              metadata.__delitem__, 'version')
            self.assertRaises(MetadataKeyError,
                              metadata.__delitem__, 'description')
            self.assertRaises(MetadataKeyError,
                              metadata.__delitem__, 'format')

            metadata['type'] = metadata.TYPES.OVERLAY
            self.assertEqual(metadata['type'], 'overlay')
            metadata['type'] = metadata.TYPES.BASELAYER
            self.assertEqual(metadata['type'], 'baselayer')
            self.assertRaises(MetadataValueError,
                              metadata.__setitem__, 'type', 'invalid')

            metadata['format'] = metadata.FORMATS.PNG
            self.assertEqual(metadata['format'], 'png')
            metadata['format'] = metadata.FORMATS.JPG
            self.assertEqual(metadata['format'], 'jpg')
            self.assertRaises(MetadataValueError,
                              metadata.__setitem__, 'format', 'invalid')

            metadata['bounds'] = '-1,-1,1,1'
            metadata['bounds'] = '-1.0,-1.0,1.0,1.0'
            metadata['bounds'] = '-1.0,-1.0,1.0,1.0'
            # left < -180
            self.assertRaises(MetadataValueError,
                              metadata.__setitem__, 'bounds', '-180.1,-1,1,1')
            # bottom < -90
            self.assertRaises(MetadataValueError,
                              metadata.__setitem__, 'bounds', '-1,-90.1,1,1')
            # right > 180
            self.assertRaises(MetadataValueError,
                              metadata.__setitem__, 'bounds', '-1,-1,180.1,1')
            # top > 90
            self.assertRaises(MetadataValueError,
                              metadata.__setitem__, 'bounds', '-1,-1,1,90.1')
            # left == right
            self.assertRaises(MetadataValueError,
                              metadata.__setitem__, 'bounds', '1,-1,1,1')
            # left > right
            self.assertRaises(MetadataValueError,
                              metadata.__setitem__, 'bounds', '1.1,-1,1,1')
            # bottom == top
            self.assertRaises(MetadataValueError,
                              metadata.__setitem__, 'bounds', '-1,1,1,1')
            # bottom > top
            self.assertRaises(MetadataValueError,
                              metadata.__setitem__, 'bounds', '-1,1.1,1,1')

    def test_validate_1_2(self):
        version = '1.2'
        metadata = dict(
            name='transparent',
            type=Metadata.all()[version].TYPES.BASELAYER,
            version='1.0.0',
            description='Transparent World 2012',
        )

        self.assertRaises(MetadataKeyError,
                          MBTiles.create, filename=self.filename,
                          metadata=self.metadata, version=version)
        metadata.update(dict(
            format=Metadata.all()[version].FORMATS.PNG,
            bounds='-180.0,-85,180,85',
            attribution='Brought to you by the letter A and the number 1.',
        ))

        with MBTiles.create(filename=self.filename,
                            metadata=metadata) as mbtiles:
            self.assertEqual(mbtiles.version, version)

        with MBTiles.create(filename=self.filename,
                            metadata=metadata,
                            version=version) as mbtiles:
            metadata = mbtiles.metadata
            self.assertRaises(MetadataKeyError,
                              metadata.__delitem__, 'name')
            self.assertRaises(MetadataKeyError,
                              metadata.__delitem__, 'type')
            self.assertRaises(MetadataKeyError,
                              metadata.__delitem__, 'version')
            self.assertRaises(MetadataKeyError,
                              metadata.__delitem__, 'description')
            self.assertRaises(MetadataKeyError,
                              metadata.__delitem__, 'format')

            metadata['type'] = metadata.TYPES.OVERLAY
            self.assertEqual(metadata['type'], 'overlay')
            metadata['type'] = metadata.TYPES.BASELAYER
            self.assertEqual(metadata['type'], 'baselayer')
            self.assertRaises(MetadataValueError,
                              metadata.__setitem__, 'type', 'invalid')

            metadata['format'] = metadata.FORMATS.PNG
            self.assertEqual(metadata['format'], 'png')
            metadata['format'] = metadata.FORMATS.JPG
            self.assertEqual(metadata['format'], 'jpg')
            self.assertRaises(MetadataValueError,
                              metadata.__setitem__, 'format', 'invalid')

            metadata['bounds'] = '-1,-1,1,1'
            metadata['bounds'] = '-1.0,-1.0,1.0,1.0'
            metadata['bounds'] = '-1.0,-1.0,1.0,1.0'
            # left < -180
            self.assertRaises(MetadataValueError,
                              metadata.__setitem__, 'bounds', '-180.1,-1,1,1')
            # bottom < -90
            self.assertRaises(MetadataValueError,
                              metadata.__setitem__, 'bounds', '-1,-90.1,1,1')
            # right > 180
            self.assertRaises(MetadataValueError,
                              metadata.__setitem__, 'bounds', '-1,-1,180.1,1')
            # top > 90
            self.assertRaises(MetadataValueError,
                              metadata.__setitem__, 'bounds', '-1,-1,1,90.1')
            # left == right
            self.assertRaises(MetadataValueError,
                              metadata.__setitem__, 'bounds', '1,-1,1,1')
            # left > right
            self.assertRaises(MetadataValueError,
                              metadata.__setitem__, 'bounds', '1.1,-1,1,1')
            # bottom == top
            self.assertRaises(MetadataValueError,
                              metadata.__setitem__, 'bounds', '-1,1,1,1')
            # bottom > top
            self.assertRaises(MetadataValueError,
                              metadata.__setitem__, 'bounds', '-1,1.1,1,1')

    def test_autocommit(self):
        with NamedTemporaryFile(suffix='.mbtiles') as tempfile:
            mbtiles = MBTiles.create(filename=tempfile.name,
                                     metadata=self.metadata,
                                     version=self.version)

            # Insert metadata
            mbtiles.metadata['test'] = 'Tileset'
            self.assertEqual(mbtiles.metadata['test'], 'Tileset')

            # Reopen
            mbtiles.open()
            self.assertEqual(mbtiles.metadata['test'], 'Tileset')

            # Delete metadata
            del mbtiles.metadata['test']
            self.assertRaises(KeyError, mbtiles.metadata.__getitem__, 'test')

            # Reopen
            mbtiles.open()
            self.assertRaises(KeyError, mbtiles.metadata.__getitem__, 'test')
