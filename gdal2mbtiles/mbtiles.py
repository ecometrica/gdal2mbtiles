import errno
import os
import sqlite3
from UserDict import DictMixin


class Metadata(DictMixin):
    """Key-value metadata table expressed as a dictionary"""

    # name: The plain-english name of the tileset.
    # type: overlay or baselayer
    # version: The version of the tileset, as a plain number.
    # description: A description of the layer as plain text.
    # format: The image file format of the tile data: png or jpg

    # bounds: The maximum extent of the rendered map area. Bounds must define
    # an area covered by all zoom levels. The bounds are represented in WGS84
    # latitude and longitude values, in the OpenLayers Bounds format: left,
    # bottom, right, top. Example of the full earth: -180.0,-85,180,85.

    # The global-mercator (aka Spherical Mercator) profile is assumed

    # A subset of image file formats are permitted:
    # * png
    # * jpg

    def __init__(self, mbtiles):
        """Links this Metadata wrapper to the MBTiles wrapper."""
        self.mbtiles = mbtiles

    def __delitem__(self, y):
        """Removes key `y` from the database."""
        with self.mbtiles._conn:
            cursor = self.mbtiles._conn.execute(
                """
                DELETE FROM metadata
                WHERE name = :name
                """,
                {'name': y}
            )
            if not cursor.rowcount:
                raise KeyError(repr(y))

    def __getitem__(self, y):
        """Gets value for key `y` from the database."""
        cursor = self.mbtiles._conn.execute(
            """
            SELECT value FROM metadata
            WHERE name = :name
            """,
            {'name': y}
        )
        value = cursor.fetchone()
        if value is None:
            raise KeyError(repr(y))
        return value[0]

    def __setitem__(self, i, y):
        """Sets value `y` for key `i` in the database."""
        with self.mbtiles._conn:
            self.mbtiles._conn.execute(
                """
                INSERT OR REPLACE INTO metadata (name, value)
                    VALUES (:name, :value)
                """,
                {'name': i, 'value': y}
            )

    def keys(self):
        """Returns a list of keys from the database."""
        cursor = self.mbtiles._conn.execute(
            """
            SELECT name FROM metadata
            """,
        )
        return zip(*cursor.fetchall())[0]


class MBTiles(object):
    """Represents an MBTiles file."""

    Metadata = Metadata

    # Pragmas for the SQLite connection
    _connection_options = {
        'auto_vacuum': 'NONE',
        'encoding': '"UTF-8"',
        'foreign_keys': '0',
        'journal_mode': 'TRUNCATE',
        'locking_mode': 'EXCLUSIVE',
        'synchronous': 'OFF',
    }

    def __init__(self, filename, options=None):
        """Opens an MBTiles file named `filename`"""
        self.filename = filename
        self._conn = None
        self._metadata = None
        self.open(options=options)

    def close(self):
        """Closes the file."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    @property
    def closed(self):
        """Returns True if the file is closed."""
        return not bool(self._conn)

    def open(self, options=None):
        """Re-opens the file."""
        self.close()
        self._conn = sqlite3.connect(self.filename)

        # Pragmas derived from options
        if options is None:
            options = self._connection_options
        self._conn.executescript(
            '\n'.join('PRAGMA {0} = {1};'.format(k, v)
                      for k, v in options.iteritems())
        )
        return self._conn

    @classmethod
    def create(cls, filename):
        """
        Creates a new MBTiles file named `filename`.

        If `filename` already exists, it gets deleted and recreated.
        """
        # The MBTiles spec defines a tiles table as:
        #     CREATE TABLE tiles (
        #         zoom_level INTEGER,
        #         tile_column INTEGER,
        #         tile_row INTEGER,
        #         tile_data BLOB
        #     );
        #
        # However, we wish to normalize the tile_data, so we store each
        # in the images table.
        try:
            os.remove(filename)
        except OSError as e:
            if e.errno != errno.ENOENT:  # Removing a non-existent file is OK.
                raise

        mbtiles = cls(filename=filename)

        conn = mbtiles._conn
        with conn:
            conn.execute(
                """
                CREATE TABLE images (
                    tile_id INTEGER PRIMARY KEY,
                    tile_data BLOB NOT NULL
                )
                """
            )

            # Then we reference the Z/X/Y coordinates in the map table.
            conn.execute(
                """
                CREATE TABLE map (
                    zoom_level INTEGER NOT NULL,
                    tile_column INTEGER NOT NULL,
                    tile_row INTEGER NOT NULL,
                    tile_id INTEGER NOT NULL
                        REFERENCES images (tile_id)
                        ON DELETE CASCADE ON UPDATE CASCADE,
                    PRIMARY KEY (zoom_level, tile_column, tile_row)
                )
                """
            )

            # Finally, we emulate the tiles table using a view.
            conn.execute(
                """
                CREATE VIEW tiles AS
                    SELECT zoom_level, tile_column, tile_row, tile_data
                    FROM map, images
                    WHERE map.tile_id = images.tile_id
                """
            )

            # We also need a table to store metadata.
            conn.execute(
                """
                CREATE TABLE metadata (
                    name TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )

        return mbtiles

    @property
    def metadata(self):
        """Returns a dictionary-like Metadata object."""
        if self._metadata is None:
            self._metadata = self.Metadata(mbtiles=self)
        return self._metadata

    def insert_tile(self, x, y, z, hashed, data=None):
        """
        Inserts a tile in the database at coordinates `x`, `y`, `z`.

        x, y, z: TMS coordinates for the tile.
        hashed: Integer hash of the raw image data, not compressed or encoded.
        data: Compressed and encoded image file.
        """
        with self._conn:
            if data is not None:
                # Insert tile data into images
                self._conn.execute(
                    """
                    INSERT OR REPLACE INTO images (tile_id, tile_data)
                    VALUES (:hashed, :data)
                    """,
                    {'hashed': hashed, 'data': data}
                )

            # Always associate map with image
            self._conn.execute(
                """
                INSERT OR REPLACE
                INTO map (zoom_level, tile_column, tile_row, tile_id)
                VALUES (:z, :x, :y, :hashed)
                """,
                {'x': x, 'y': y, 'z': z, 'hashed': hashed}
            )

    def get_tile(self, x, y, z):
        """
        Returns the compressed image data at coordinates `x`, `y`, `z`.

        x, y, z: TMS coordinates for the tile.
        """
        cursor = self._conn.execute(
            """
            SELECT tile_data FROM tiles
            WHERE zoom_level = :z AND
                  tile_column = :x AND
                  tile_row = :y
            """,
            {'x': x, 'y': y, 'z': z}
        )
        result = cursor.fetchone()
        if result is None:
            return None
        return result[0]
