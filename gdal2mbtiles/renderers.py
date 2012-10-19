# -*- coding: utf-8 -*-

from __future__ import absolute_import


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
    """
    _suffix = '.jpeg'

    def render(self, image, filename):
        """
        Renders the VIPS `image` to `filename`.

        Returns the filename actually rendered to.
        """
        if image.Bands() > 3:
            # Strip out alpha channel, otherwise transparent pixels turn white.
            image = image.extract_bands(band=0, nbands=3)
        image.vips2jpeg(filename)
        return filename


class PngRenderer(Renderer):
    """Render a VIPS image as a PNG to filename."""
    _suffix = '.png'

    def render(self, image, filename):
        """
        Renders the VIPS `image` to `filename`.

        Returns the filename actually rendered to.
        """
        image.vips2png(filename)
        return filename


class TouchRenderer(Renderer):
    """For testing only. Only creates files, doesn't actually render."""
    _suffix = ''

    def render(self, image, filename):
        """Touches `filename` and returns its value."""
        open(filename, mode='w').close()
        return filename
