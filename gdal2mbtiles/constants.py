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


# EPSG constants
EPSG_WEB_MERCATOR = 3857

# ESRI constants with their EPSG code equivalent
ESRI_102113_PROJ = 'WGS_1984_Web_Mercator'                   # EPSG:3785
ESRI_102100_PROJ = 'WGS_1984_Web_Mercator_Auxiliary_Sphere'  # EPSG:3857

# Output constants
TILE_SIDE = 256                 # in pixels

# Command-line programs
GDALINFO = 'gdalinfo'
GDALTRANSLATE = 'gdal_translate'
GDALWARP = 'gdalwarp'
