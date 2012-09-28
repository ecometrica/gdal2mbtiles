from collections import namedtuple

import webcolors


GdalFormat = namedtuple(typename='GdalFormat',
                        field_names=['name', 'attributes', 'description',
                                     'can_read', 'can_write', 'can_update',
                                     'has_virtual_io'])
