# -*- coding: utf-8 -*-

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import os


def load_tests(loader, tests, pattern):
    discovered = loader.discover(start_dir=os.path.dirname(__file__))
    tests.addTests(tests=discovered)
    return tests
