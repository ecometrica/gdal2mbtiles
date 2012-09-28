from collections import namedtuple

import webcolors


GdalFormat = namedtuple(typename='GdalFormat',
                        field_names=['name', 'attributes', 'description',
                                     'can_read', 'can_write', 'can_update',
                                     'has_virtual_io'])


_rgba = namedtuple(typename='_rgba',
                   field_names=['r', 'g', 'b', 'a'])
class rgba(_rgba):
    """Represents an RGBA colour."""
    def __new__(cls, r, g, b, a=255):
        return super(rgba, cls).__new__(cls, r, g, b, a)


def hcolour(s):
    """Returns an RGBA colour from its HTML/CSS representation."""
    if s.startswith('#'):
        return rgba(*webcolors.hex_to_rgb(s))
    return rgba(*webcolors.name_to_rgb(s))
