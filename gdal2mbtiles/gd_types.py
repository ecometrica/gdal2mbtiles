# -*- coding: utf-8 -*-

# Licensed to Ecometrica under one or more contributor license
# agreements.  See the NOTICE file distributed with this work
# for additional information regarding copyright ownership.
# Ecometrica licenses this file to you under the Apache
# License, Version 2.0 (the "License"); you may not use this
# file except in compliance with the License.  You may obtain a
# copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

from collections import namedtuple

import webcolors


GdalFormat = namedtuple(typename='GdalFormat',
                        field_names=['name', 'attributes', 'description',
                                     'can_read', 'can_write', 'can_update',
                                     'has_virtual_io'])


def enum(**enums):
    E = namedtuple(typename='enum',
                   field_names=list(enums.keys()))
    return E(**enums)


_rgba = namedtuple(typename='_rgba',
                   field_names=['r', 'g', 'b', 'a'])


class rgba(_rgba):
    """Represents an RGBA color."""
    def __new__(cls, r, g, b, a=255):
        return super(rgba, cls).__new__(cls, r, g, b, a)

    @classmethod
    def webcolor(cls, color):
        """Returns an RGBA color from its HTML/CSS representation."""
        if color.startswith('#'):
            return cls(*webcolors.hex_to_rgb(color))
        return cls(*webcolors.name_to_rgb(color))


_Extents = namedtuple('Extents', ['lower_left', 'upper_right'])


class Extents(_Extents):
    def __contains__(self, other):
        if isinstance(other, type(self)):
            # TODO: Support testing against own type
            raise NotImplementedError()
        elif isinstance(other, (tuple, list, XY)):
            return (self.lower_left.x <= other[0] < self.upper_right.x and
                    self.lower_left.y <= other[1] < self.upper_right.y)
        raise TypeError("Can't handle {0!r}".format(other))

    def almost_equal(self, other, places=None, delta=None):
        return (self.lower_left.almost_equal(other.lower_left,
                                             places=places, delta=delta) and
                self.upper_right.almost_equal(other.upper_right,
                                              places=places, delta=delta))

    @property
    def dimensions(self):
        return self.upper_right - self.lower_left


_XY = namedtuple('XY', ['x', 'y'])


class XY(_XY):
    def __add__(self, other):
        return type(self)(x=self.x + other.x,
                          y=self.y + other.y)

    def __sub__(self, other):
        return type(self)(x=self.x - other.x,
                          y=self.y - other.y)

    def __mul__(self, other):
        return type(self)(x=self.x * other,
                          y=self.y * other)

    def __truediv__(self, other):
        return type(self)(x=self.x / other,
                          y=self.y / other)

    def floor(self):
        return type(self)(int(self.x), int(self.y))

    def almost_equal(self, other, places=None, delta=None):
        if self.x == other[0] and self.y == other[1]:
            return True         # Shortcut

        if delta is not None and places is not None:
            raise TypeError("specify delta or places not both")

        if delta is not None:
            return (abs(self.x - other[0]) <= delta and
                    abs(self.y - other[1]) <= delta)

        if places is None:
            places = 7

        return (round(abs(other[0] - self.x), places) == 0 and
                round(abs(other[1] - self.y), places) == 0)
