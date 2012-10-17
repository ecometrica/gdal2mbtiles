# -*- coding: utf-8 -*-

from __future__ import absolute_import


class Renderer(object):
    ext = ''

    @classmethod
    def render(self, image, filename):
        raise NotImplementedError()


class PngRenderer(Renderer):
    """Render a VIPS image to filename."""
    ext = '.png'

    @classmethod
    def render(self, image, filename):
        """
        Renders the VIPS `image` to `filename`.

        Returns the filename actually rendered to.
        """
        image.vips2png(filename)
        return filename
