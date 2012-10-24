# -*- coding: utf-8 -*-

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import os
from subprocess import check_call
import sys
from tempfile import NamedTemporaryFile
import unittest

from gdal2mbtiles.mbtiles import MBTiles


__dir__ = os.path.dirname(__file__)


class TestGdal2mbtilesScript(unittest.TestCase):
    def setUp(self):
        self.repo_dir = os.path.join(__dir__, os.path.pardir)
        self.scripts_dir = os.path.join(self.repo_dir, 'scripts')
        self.script = os.path.join(self.scripts_dir, 'gdal2mbtiles')

        self.environ = os.environ.copy()

        # Make sure you can get to the local gdal2mbtiles module
        pythonpath = self.environ.get('PYTHONPATH', [])
        if pythonpath:
            pythonpath = pythonpath.split(os.path.pathsep)
        pythonpath = os.path.pathsep.join([self.repo_dir] + pythonpath)
        self.environ['PYTHONPATH'] = pythonpath

    def test_simple(self):
        with NamedTemporaryFile(suffix='.mbtiles') as output:
            inputfile = os.path.join(__dir__, 'bluemarble.tif')
            check_call([sys.executable, self.script, inputfile, output.name],
                       env=self.environ)
            with MBTiles(output.name) as mbtiles:
                # 4×4 at resolution 2
                cursor = mbtiles._conn.execute('SELECT COUNT(*) FROM tiles')
                self.assertEqual(cursor.fetchone(), (16,))
