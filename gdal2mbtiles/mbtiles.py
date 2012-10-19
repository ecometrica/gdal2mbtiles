from distutils.version import LooseVersion
import errno
import os
import sqlite3
from UserDict import DictMixin

from .types import enum


class MBTilesError(RuntimeError):
    pass


class InvalidFileError(MBTilesError):
    pass


class UnknownVersionError(MBTilesError):
    pass


class MetadataError(MBTilesError):
    pass


class MetadataKeyError(MetadataError, KeyError):
    pass


class MetadataValueError(MetadataError, ValueError):
    pass


class Metadata(object, DictMixin):
    """
    Key-value metadata table expressed as a dictionary
    """
    VERSION = None

    MANDATORY = None
    OPTIONAL = None

    _all = None

    def __init__(self, mbtiles):
        """Links this Metadata wrapper to the MBTiles wrapper."""
        self.mbtiles = mbtiles

    def __delitem__(self, y):
        """Removes key `y` from the database."""
        if y in self.MANDATORY:
            raise MetadataKeyError(
                "Cannot delete mandatory key: {0!r}".format(y)
            )
        return self._delitem(y)

    def _delitem(self, y):
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
                raise MetadataKeyError(repr(y))

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
            raise MetadataKeyError(repr(y))
        return value[0]

    def __setitem__(self, i, y):
        validator = getattr(self, '_validate_' + i, None)
        if validator is not None:
            validator(y)
        return self._setitem(i, y)

    def _setitem(self, i, y):
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
        try:
            cursor = self.mbtiles._conn.execute(
                """
                SELECT name FROM metadata
                """,
            )
        except sqlite3.OperationalError:
            raise InvalidFileError("Invalid MBTiles file.")
        result = cursor.fetchall()
        if not result:
            return result
        return zip(*result)[0]

    def _setup(self, metadata):
        missing = set(self.MANDATORY) - set(metadata.keys())
        if missing:
            raise MetadataKeyError(
                "Required keys missing from metadata: {0}".format(
                    ', '.join(missing)
                )
            )
        self.update(metadata)

    @classmethod
    def _detect(cls, keys):
        version = None
        for ver, M in sorted(cls.all().items()):
            if set(keys).issuperset(set(M.MANDATORY)):
                version = ver
        if version is None:
            raise InvalidFileError("Invalid MBTiles file.")
        return version

    @classmethod
    def detect(cls, mbtiles):
        """Returns the Metadata version detected from `mbtiles`."""
        return cls._detect(keys=cls(mbtiles=mbtiles).keys())

    @classmethod
    def all(cls):
        """Returns all Metadata classes."""
        if cls._all is None:
            def subclasses(base):
                for m in base.__subclasses__():
                    yield m
                    for n in subclasses(base=m):
                        yield n

            cls._all = dict((m.VERSION, m)
                            for m in subclasses(base=Metadata))
        return cls._all

    @classmethod
    def latest(cls):
        """Returns the latest Metadata class."""
        return sorted(cls.all().items(),
                      key=(lambda k: LooseVersion(k[0])),
                      reverse=True)[0][1]


class Metadata_1_0(Metadata):
    """
    Mandatory metadata:
    name: The plain-english name of the tileset.
    type: mbtiles.TYPES.OVERLAY or mbtiles.TYPES.BASELAYER
    version: The version of the tileset, as a plain number.
    description: A description of the layer as plain text.
    """

    VERSION = '1.0'

    MANDATORY = ('name', 'type', 'version', 'description')
    OPTIONAL = ()

    TYPES = enum(OVERLAY='overlay',
                 BASELAYER='baselayer')

    def _validate_type(self, value):
        if value not in self.TYPES:
            raise MetadataValueError(
                "type {value!r} must be one of: {types}".format(
                    value=value,
                    types=', '.join(sorted(self.TYPES))
                )
            )


class Metadata_1_1(Metadata_1_0):
    """
    Mandatory metadata:
    name: The plain-english name of the tileset.
    type: mbtiles.TYPES.OVERLAY or mbtiles.TYPES.BASELAYER
    version: The version of the tileset, as a plain number.
    description: A description of the layer as plain text.
    format: The image file format of the tile data:
            mbtiles.FORMATS.PNG or mbtiles.FORMATS.JPG

    Optional metadata:
    bounds: The maximum extent of the rendered map area. Bounds must define
            an area covered by all zoom levels. The bounds are represented
            in WGS:84 latitude and longitude values, in the OpenLayers
            Bounds format (left, bottom, right, top).
            Example of the full earth: '-180.0,-85,180,85'.
    """
    VERSION = '1.1'

    MANDATORY = Metadata_1_0.MANDATORY + ('format',)
    OPTIONAL = Metadata_1_0.OPTIONAL + ('bounds',)

    FORMATS = enum(PNG='png',
                   JPG='jpg')

    def _validate_format(self, value):
        if value not in self.FORMATS:
            raise MetadataValueError(
                "format {value!r} must be one of: {formats}".format(
                    value=value,
                    formats=', '.join(sorted(self.FORMATS))
                )
            )

    def _validate_bounds(self, value):
        try:
            left, bottom, right, top = [float(b) for b in value.split(',')]
            if left >= right or bottom >= top or \
               left < -180.0 or right > 180.0 or \
               bottom < -90.0 or top > 90.0:
                raise ValueError()
        except ValueError:
            raise MetadataValueError("Invalid bounds: {0!r}".format(value))


class Metadata_1_2(Metadata_1_1):
    """
    Mandatory metadata:
    name: The plain-english name of the tileset.
    type: mbtiles.TYPES.OVERLAY or mbtiles.TYPES.BASELAYER
    version: The version of the tileset, as a plain number.
    description: A description of the layer as plain text.
    format: The image file format of the tile data:
            mbtiles.FORMATS.PNG or mbtiles.FORMATS.JPG

    Optional metadata:
    bounds: The maximum extent of the rendered map area. Bounds must define
            an area covered by all zoom levels. The bounds are represented
            in WGS:84 latitude and longitude values, in the OpenLayers
            Bounds format (left, bottom, right, top).
            Example of the full earth: '-180.0,-85,180,85'.
    attribution: An attribution string, which explains in English (and
                 HTML) the sources of data and/or style for the map.
    """

    VERSION = '1.2'
    OPTIONAL = Metadata_1_1.OPTIONAL + ('attribution',)


class MBTiles(object):
    """Represents an MBTiles file."""

    # Pragmas for the SQLite connection
    _connection_options = {
        'auto_vacuum': 'NONE',
        'encoding': '"UTF-8"',
        'foreign_keys': '0',
        'journal_mode': 'TRUNCATE',
        'locking_mode': 'EXCLUSIVE',
        'synchronous': 'OFF',
    }

    def __init__(self, filename, version=None, options=None):
        """Opens an MBTiles file named `filename`"""
        self.filename = filename
        self._conn = None
        self._metadata = None
        self._version = version

        self.open(options=options)

    def __del__(self):
        self.close()

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.close()

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
        result = self._open(options=options)
        self.metadata
        return result

    def _open(self, options=None):
        self.close()
        try:
            self._conn = sqlite3.connect(self.filename)
        except sqlite3.OperationalError:
            raise InvalidFileError("Invalid MBTiles file.")

        # Pragmas derived from options
        if options is None:
            options = self._connection_options
        try:
            self._conn.executescript(
                '\n'.join('PRAGMA {0} = {1};'.format(k, v)
                          for k, v in options.iteritems())
            )
        except sqlite3.DatabaseError:
            raise InvalidFileError("Invalid MBTiles file.")
        return self._conn

    @classmethod
    def create(cls, filename, metadata, version=None):
        """Create a new MBTiles file. See `Metadata`"""
        if version is None:
            version = Metadata._detect(keys=metadata.keys())
        mbtiles = cls._create(filename=filename, version=version)
        mbtiles.metadata._setup(metadata)
        return mbtiles

    @classmethod
    def _create(cls, filename, version):
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

        mbtiles = cls(filename=filename, version=version)

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
    def version(self):
        if self._version is None:
            self._version = Metadata.detect(mbtiles=self)
        return self._version

    @property
    def metadata(self):
        """Returns a dictionary-like Metadata object."""
        if self._metadata is None:
            try:
                M = Metadata.all()[self.version]
            except KeyError:
                raise UnknownVersionError(
                    'Unknown version {0}'.format(self._version)
                )
            self._metadata = M(mbtiles=self)
        return self._metadata

    def insert(self, x, y, z, hashed, data=None):
        """
        Inserts a tile in the database at coordinates `x`, `y`, `z`.

        x, y, z: TMS coordinates for the tile.
        hashed: Integer hash of the raw image data, not compressed or encoded.
        data: Compressed and encoded image buffer.
        """
        hashed = int(hashed % 2 ** 32)    # hashed is only an INTEGER

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

    def get(self, x, y, z):
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

    def all(self):
        """
        Returns all of the compressed image data
        """
        cursor = self._conn.execute(
            """
            SELECT zoom_level, tile_column, tile_row, tile_data FROM tiles
            ORDER BY zoom_level, tile_column, tile_row
            """
        )
        while True:
            rows = cursor.fetchmany()
            if not rows:
                return
            for z, x, y, data in rows:
                yield z, x, y, data
