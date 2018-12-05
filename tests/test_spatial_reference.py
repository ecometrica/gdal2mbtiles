# -*- coding: utf-8 -*-


import rasterio
import pytest
from math import pi

from numpy import array
from numpy.testing import assert_array_almost_equal

from gdal2mbtiles.constants import EPSG_WEB_MERCATOR

from gdal2mbtiles.gdal import SpatialReference


# SEMI_MAJOR is a constant referring to the WGS84 Semi Major Axis.
SEMI_MAJOR = 6378137.0

# Note: web-Mercator = pseudo-Mercator = EPSG 3857
# The extents of the web-Mercator are constants.
# Since the projection is formed from a sphere the extents of the projection
# form a square.
# For the values of the extents refer to:
# OpenLayer lib: http://docs.openlayers.org/library/spherical_mercator.html
EPSG3857_EXTENT = pi * SEMI_MAJOR

EPSG3857_EXTENTS = array([[-EPSG3857_EXTENT]*2, [EPSG3857_EXTENT]*2])

epsg_3857_raster_path = 'tests/web_mercator_3857.tif'


@pytest.fixture
def epsg_3857_from_proj4():
    """
    Return a gdal spatial reference object with
    3857 crs using the ImportFromProj4 method.
    """
    ds_3857 = rasterio.open(epsg_3857_raster_path)
    spatial_ref = SpatialReference()
    spatial_ref.ImportFromProj4(ds_3857.crs.to_string())
    return spatial_ref


@pytest.fixture
def epsg_3857_from_epsg():
    """
    Return a gdal spatial reference object with
    3857 crs using the FromEPSG method.
    """
    spatial_ref = SpatialReference.FromEPSG(EPSG_WEB_MERCATOR)
    return spatial_ref


def test_epsg_3857_proj4(epsg_3857_from_proj4):
    extents = epsg_3857_from_proj4.GetWorldExtents()
    extents = array(extents)
    assert_array_almost_equal(extents, EPSG3857_EXTENTS, decimal=3)


def test_epsg_3857_from_epsg(epsg_3857_from_epsg):
    extents = epsg_3857_from_epsg.GetWorldExtents()
    extents = array(extents)
    assert_array_almost_equal(extents, EPSG3857_EXTENTS, decimal=3)
