# -*- coding: utf-8 -*-

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)


def __discover_tests():
    import os
    import sys
    import unittest

    loader = unittest.defaultTestLoader
    discovered = loader.discover(start_dir=os.path.dirname(__file__))

    def extract_tests(suite):
        for obj in suite._tests:
            if isinstance(obj, unittest.TestCase):
                yield obj
            else:
                for t in extract_tests(suite=obj):
                    yield t

    cases = set(type(t) for t in extract_tests(suite=discovered))

    mod = sys.modules[__name__]
    for case in cases:
        setattr(mod, case.__name__, case)
__discover_tests()
