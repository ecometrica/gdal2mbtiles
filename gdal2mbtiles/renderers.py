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

import os
from subprocess import check_call
from tempfile import gettempdir, NamedTemporaryFile

from .utils import rmfile


class Renderer(object):
    _suffix = ''

    def __init__(self, suffix=None, tempdir=None):
        if suffix is None:
            suffix = self.__class__._suffix
        self.suffix = suffix

        if tempdir is None:
            tempdir = gettempdir()
        self.tempdir = tempdir

    def __str__(self):
        return 'Renderer(suffix={suffix!r})'.format(**self.__dict__)

    def render(self, image):
        raise NotImplementedError()


class JpegRenderer(Renderer):
    """
    Render a VIPS image as a JPEG to filename.

    Since JPEGs cannot contain transparent areas, the alpha channel is
    discarded.

    compression: JPEG compression level. Default 75.
    interlace: Filename of ICC profile. Default None.
    suffix: Suffix for filename. Default '.jpeg'.
    """
    _suffix = '.jpeg'

    def __init__(self, compression=None, profile=None, **kwargs):
        if compression is None:
            compression = 75
        _compression = int(compression)
        if not 0 <= _compression <= 100:
            raise ValueError(
                'compression must be between 0 and 100: {0!r}'.format(
                    compression
                )
            )
        self.compression = _compression

        if profile is None:
            profile = 'none'
        self.profile = profile

        super(JpegRenderer, self).__init__(**kwargs)

    @property
    def _vips_options(self):
        return {
            'Q': self.compression,
            'profile': self.profile
        }

    def render(self, image):
        """Returns the rendered VIPS `image`."""
        if image.bands > 3:
            # Strip out alpha channel, otherwise transparent pixels turn white.
            image = image.extract_band(0, n=3)
        with NamedTemporaryFile(suffix=self.suffix,
                                dir=self.tempdir) as rendered:
            image.write_to_file(rendered.name, **self._vips_options)
            return rendered.read()


class PngRenderer(Renderer):
    """
    Render a VIPS image as a PNG.

    compression: PNG compression level. Default 6.
    interlace: Use ADAM7 interlacing. Default False.
    png8: Quantizes 32-bit RGBA to 8-bit RGBA paletted PNGs. Default False.
          If an integer, specifies number of colors in palette.
          If True, defaults to 256 colors.
    optimize: Optimizes PNG using optipng. Default False. See `optipng -h`.
    suffix: Suffix for filename. Default '.png'.

    If optimize is not False, then compression is ignored and set to 0, to
    prevent double-compression. In general, VIPS compression is faster than
    optimizing with OptiPNG.
    """
    _suffix = '.png'

    PNGQUANT = 'pngquant'
    OPTIPNG = 'optipng'

    def __init__(self, compression=None, interlace=None, png8=None,
                 optimize=None, **kwargs):
        if compression is None:
            compression = 6
        _compression = int(compression)
        if not 0 <= _compression <= 9:
            raise ValueError(
                'compression must be between 0 and 9: {0!r}'.format(
                    compression
                )
            )
        self.compression = _compression

        self.interlace = bool(interlace)

        _png8 = png8
        if _png8 is None:
            _png8 = False
        elif _png8 is True:
            _png8 = 256
        if _png8 is not False:
            _png8 = int(_png8)
            if not 2 <= _png8 <= 256:
                raise ValueError(
                    'png8 must be between 2 and 256: {0!r}'.format(png8)
                )
        self.png8 = _png8

        _optimize = optimize
        if _optimize is None:
            _optimize = False
        if _optimize is not False:
            _optimize = int(_optimize)
            if not 0 <= _optimize <= 7:
                raise ValueError(
                    'optimize must be between 0 and 7: {0!r}'.format(optimize)
                )
        if _optimize:
            self.compression = 1  # Reduce cost of double-compression
        self.optimize = _optimize

        super(PngRenderer, self).__init__(**kwargs)

    @property
    def _vips_options(self):
        return {
            'compression': self.compression,
            'interlace': self.interlace
        }

    def render(self, image):
        """Returns the rendered VIPS `image`."""
        with NamedTemporaryFile(suffix=self.suffix,
                                dir=self.tempdir) as rendered:
            image.write_to_file(rendered.name, **self._vips_options)
            filename = rendered.name

            if self.png8 is not False:
                check_call([self.PNGQUANT, '--force', str(self.png8),
                            filename])
                filename = os.path.splitext(filename)[0] + '-fs8.png'

            if self.optimize is not False:
                check_call([self.OPTIPNG, '-o{0:d}'.format(self.optimize),
                            '-quiet', filename])

            with open(filename, 'rb') as result:
                if rendered.name != filename:
                    rmfile(filename, ignore_missing=True)
                return result.read()


class TouchRenderer(Renderer):
    """For testing only. Only creates files, doesn't actually render."""
    _suffix = ''

    def render(self, image):
        """Touches `filename` and returns its value."""
        return b''
