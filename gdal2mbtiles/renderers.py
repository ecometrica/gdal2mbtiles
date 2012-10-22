# -*- coding: utf-8 -*-

from __future__ import absolute_import

from tempfile import NamedTemporaryFile


class Renderer(object):
    _suffix = ''

    def __init__(self, suffix=None):
        if suffix is None:
            suffix = self.__class__._suffix
        self.suffix = suffix

    def __str__(self):
        return 'Renderer(suffix={suffix!r})'.format(**self.__dict__)

    def render(self, image, filename):
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
                'compression must be between 0 and 100: {0}'.format(compression)
            )
        self.compression = _compression

        if profile is None:
            profile = 'none'
        self.profile = profile

        super(JpegRenderer, self).__init__(**kwargs)

    @property
    def _options(self):
        return ':{compression:d},{profile}'.format(
            compression=self.compression,
            profile=self.profile,
        )

    def render(self, image):
        """Returns the rendered VIPS `image`."""
        if image.Bands() > 3:
            # Strip out alpha channel, otherwise transparent pixels turn white.
            image = image.extract_bands(band=0, nbands=3)
        with NamedTemporaryFile(suffix=self.suffix) as tempfile:
            image.vips2jpeg(tempfile.name + self._options)
            return tempfile.read()


class PngRenderer(Renderer):
    """
    Render a VIPS image as a PNG.

    compression: PNG compression level. Default 6.
    interlace: Use ADAM7 interlacing. Default False.
    suffix: Suffix for filename. Default '.png'.
    """
    _suffix = '.png'

    def __init__(self, compression=None, interlace=None, **kwargs):
        if compression is None:
            compression = 6
        _compression = int(compression)
        if not 0 <= _compression <= 9:
            raise ValueError(
                'compression must be between 0 and 9: {0}'.format(compression)
            )
        self.compression = _compression

        self.interlace = bool(interlace)

        super(PngRenderer, self).__init__(**kwargs)

    @property
    def _options(self):
        return ':{compression:d},{interlace:d}'.format(
            compression=self.compression,
            interlace=self.interlace,
        )

    def render(self, image):
        """Returns the rendered VIPS `image`."""
        with NamedTemporaryFile(suffix=self.suffix) as tempfile:
            image.vips2png(tempfile.name + self._options)
            return tempfile.read()


class TouchRenderer(Renderer):
    """For testing only. Only creates files, doesn't actually render."""
    _suffix = ''

    def render(self, image):
        """Touches `filename` and returns its value."""
        return ''
