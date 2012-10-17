import os
from tempfile import NamedTemporaryFile
import unittest

from gdal2mbtiles.mbtiles import MBTiles


class TestMBTiles(unittest.TestCase):
    def setUp(self):
        self.tempfile = NamedTemporaryFile(suffix='.mbtiles')
        self.filename = self.tempfile.name

    def tearDown(self):
        self.tempfile.close()

    def test_open(self):
        mbtiles = MBTiles(filename=self.filename)

        # File are auto-opened
        self.assertFalse(mbtiles.closed)
        conn = mbtiles._conn

        # Open again
        self.assertNotEqual(mbtiles.open(), conn)

        # Close
        mbtiles.close()
        self.assertTrue(mbtiles.closed)

    def test_create(self):
        # Create when filename does not exist
        os.remove(self.filename)
        mbtiles1 = MBTiles.create(filename=self.filename)
        self.assertFalse(mbtiles1.closed)

        # Create again when it exists
        mbtiles2 = MBTiles.create(filename=self.filename)
        self.assertFalse(mbtiles2.closed)

        self.assertNotEqual(mbtiles1, mbtiles2)

    def test_metadata(self):
        mbtiles = MBTiles.create(filename=self.filename)
        metadata = mbtiles.metadata

        # Set
        metadata['name'] = ''
        self.assertEqual(metadata['name'], '')

        # Set again
        metadata['name'] = 'Tileset'
        self.assertEqual(metadata['name'], 'Tileset')

        # Get missing
        self.assertRaises(KeyError, metadata.__getitem__, 'missing')
        self.assertEqual(metadata.get('missing'), None)
        self.assertEqual(metadata.get('missing', False), False)

        # Contains
        self.assertTrue('name' in metadata)
        self.assertFalse('missing' in metadata)

        # Delete
        del metadata['name']
        self.assertFalse('name' in metadata)

        # Delete missing
        self.assertRaises(KeyError, metadata.__delitem__, 'missing')

        # Pop
        metadata['name'] = 'Tileset'
        self.assertEqual(metadata.pop('name'), 'Tileset')

        # Pop missing
        self.assertRaises(KeyError, metadata.pop, 'name')
        self.assertEqual(metadata.pop('name', None), None)

        # Update
        data = {
            'name': 'Tileset',
            'description': 'This is a test tileset.',
        }
        metadata.update(data)

        # Keys
        self.assertEqual(set(metadata.keys()), set(data.keys()))

        # Values
        self.assertEqual(set(metadata.values()), set(data.values()))

        # Items
        self.assertEqual(set(metadata.items()), set(data.items()))

        # Compare with dictionary
        self.assertEqual(metadata, data)

    def test_tiles(self):
        mbtiles = MBTiles.create(filename=self.filename)
        data = 'PNG image'
        hashed = hash(data)

        # Get missing tile
        self.assertEqual(mbtiles.get_tile(x=0, y=0, z=0), None)

        # Insert tile
        mbtiles.insert_tile(x=0, y=0, z=0, hashed=hashed, data=data)

        # Get inserted tile
        self.assertEqual(mbtiles.get_tile(x=0, y=0, z=0), data)

        # Link tile
        mbtiles.insert_tile(x=1, y=1, z=1, hashed=hashed)

        # Get linked tile
        self.assertEqual(mbtiles.get_tile(x=1, y=1, z=1), data)

    def test_out_of_order_tile(self):
        mbtiles = MBTiles.create(filename=self.filename)
        data = 'PNG image'
        hashed = hash(data)

        # Link tile to nonexistent data
        mbtiles.insert_tile(x=1, y=1, z=1, hashed=hashed)

        # Get linked tile
        self.assertEqual(mbtiles.get_tile(x=1, y=1, z=1), None)

        # Add nonexistent data
        mbtiles.insert_tile(x=0, y=0, z=0, hashed=hashed, data=data)

        # Get tile again
        self.assertEqual(mbtiles.get_tile(x=1, y=1, z=1), data)

    def test_autocommit(self):
        mbtiles = MBTiles.create(filename=self.filename)
        data = 'PNG image'
        hashed = hash(data)

        # Insert tile
        mbtiles.insert_tile(x=0, y=0, z=0, hashed=hashed, data=data)
        self.assertEqual(mbtiles.get_tile(x=0, y=0, z=0), data)

        # Reopen
        mbtiles.open()
        self.assertEqual(mbtiles.get_tile(x=0, y=0, z=0), data)

        # Insert metadata
        mbtiles.metadata['name'] = 'Tileset'
        self.assertEqual(mbtiles.metadata['name'], 'Tileset')

        # Reopen
        mbtiles.open()
        self.assertEqual(mbtiles.metadata['name'], 'Tileset')

        # Delete metadata
        del mbtiles.metadata['name']
        self.assertRaises(KeyError, mbtiles.metadata.__getitem__, 'name')

        # Reopen
        mbtiles.open()
        self.assertRaises(KeyError, mbtiles.metadata.__getitem__, 'name')
