============
gdal2mbtiles
============

Convert GDAL-readable datasets into an MBTiles file
===================================================

**gdal2mbtiles** helps you generate web mapping tiles that can be shown
through a browser-based mapping library on your website.

`GDAL-readable files`_ are images that are georeference, that means that
they are positioned and projected on to the world. In order to display a
dynamic map on the web, you don't want to serve the whole image at once,
so it must be sliced into tiles that are hosted by a tile server.

The MBTiles_ file format was developed by MapBox_ to make tile storage
easier. You can upload the final file to their service, or run your own
tile server. MapBox provides one called TileStream_.

Later versions of GDAL (>= 2) allow generation of mbtiles files via the
``gdal_translate`` and ``gdaladdo`` commands.  However, gdal2mbtiles offers some
advantages:

*  allows you to specify an upper resolution/zoom level.  GDAL always uses the
   native resolution of the input raster to determine the highest zoom level of
   the mbtiles output, whereas gdal2mbtiles can also upsample to create zoom levels
   at a higher resolution than your original file.
* the ``gdal_translate`` command only converts the geotiff at the native resolution,
  so the lower resolutions are added to the file via overviews (``gdaladdo``)
* ``gdaladdo`` can only add overviews down to the zoom level corresponding to
  the size of the tile/block size (256x256).  gdal2mbtiles can always create images
  down to zoom level 1.
* performance: gdal2mbtiles uses pyvips for image processing, which is parallel
  and quick.  Compared to the equivalent processing with GDAL, gdal2mbtiles is
  typically 2-4 times quicker.  For example:

  * a resolution 14 file, 13000x11000 pixels, min resolution 0, max resolution
    14: ~5 minutes with gdal2mbtiles and ~8 minutes with GDAL commands.
  * a resoluton 11 file, 200,000x200,000, zoom level 11 only: ~30min with
    gdal2mbtiles and ~133min with GDAL (with ``GDAL_CACHE_MAX`` and
    ``GDAL_NUM_THREADS`` options)


Installation
============

PyPI package page: https://pypi.python.org/pypi/gdal2mbtiles/

.. warning:: gdal2mbtiles requires Python 2.7 or higher and relies on
  installing the items from the `External Dependencies`_ section below *before*
  the python package.

Using pip::

    $ pip install gdal2mbtiles

From source::

    $ git clone https://github.com/ecometrica/gdal2mbtiles.git
    $ cd gdal2mbtiles
    $ python setup.py install

External Dependencies
---------------------

We rely on GDAL_ to read georeferenced datasets.
Under Debian or Ubuntu, you can install the GDAL library & binary via apt.

Default GDAL versions in Ubuntu LTS:

* Xenial: 1.11
* Bionic: 2.2
* Focal: 3.0

.. warning::
  GDAL 2 is the current supported version.
  GDAL 3 support is in progress - `contributions <#contributing>`_ welcome!

We recommend using the `UbuntuGIS`_ PPA to get more recent versions of GDAL, if
needed, as is the case for Xenial.

.. code-block:: sh

    sudo add-apt-repository ppa:ubuntugis/ppa && sudo apt-get update
    sudo apt-get install gdal-bin libgdal-dev

The ubuntugis PPA also usually includes ``python-gdal`` or ``python3-gdal``
that will install the python bindings at the system level. Installing
that may be enough for you if you aren't planning to use a non-default python
or a `virtual environment`_.

Otherwise, you will also need to install the GDAL python bindings package from
`PyPI <GDAL_PyPI>`_. Make sure to install the version that matches the installed
GDAL library. You can double-check that version with ``gdal-config --version``.

.. code-block:: sh

    pip install \
      --global-option=build_ext \
      --global-option=--gdal-config=/usr/bin/gdal-config \
      --global-option=--include-dirs=/usr/include/gdal/ \
      GDAL=="$(gdal-config --version)"

We also rely on VIPS_ (version 8.2+) to do fast image processing.

Under Debian or Ubuntu, run the following to install it without the GUI nip2::

    $ sudo apt-get install --no-install-recommends libvips libvips-dev

You'll also need a few other libraries to deal with large TIFF files and
to optimize the resulting PNG tiles.

Under Debian or Ubuntu, run the following to install them::

    $ sudo apt-get install libtiff5 optipng pngquant


Command Line Interface
======================

.. code-block:: console

    $ gdal2mbtiles --help
    usage: gdal2mbtiles [-h] [-v] [--name NAME] [--description DESCRIPTION]
                        [--layer-type {baselayer,overlay}] [--version VERSION]
                        [--format {jpg,png}]
                        [--spatial-reference SPATIAL_REFERENCE]
                        [--resampling {near,bilinear,cubic,cubicspline,lanczos}]
                        [--min-resolution MIN_RESOLUTION]
                        [--max-resolution MAX_RESOLUTION] [--fill-borders]
                        [--no-fill-borders] [--zoom-offset N]
                        [--coloring {gradient,palette,exact}]
                        [--color BAND-VALUE:HTML-COLOR]
                        [--colorize-band COLORIZE-BAND]
                        [--png8 PNG8]
                        [INPUT] [OUTPUT]

    Converts a GDAL-readable into an MBTiles file

    optional arguments:
      -h, --help            show this help message and exit
      -v, --verbose         explain what is being done

    Positional arguments:
      INPUT                 GDAL-readable file.
      OUTPUT                Output filename. Defaults to INPUT.mbtiles

    MBTiles metadata arguments:
      --name NAME           Human-readable name of the tileset. Defaults to INPUT
      --description DESCRIPTION
                            Description of the layer. Defaults to ""
      --layer-type {baselayer,overlay}
                            Type of layer. Defaults to "overlay"
      --version VERSION     Version of the tileset. Defaults to "1.0.0"
      --format {jpg,png}    Tile image format. Defaults to "png"

    GDAL warp arguments:
      --spatial-reference SPATIAL_REFERENCE
                            Destination EPSG spatial reference. Defaults to 3857
      --resampling {near,bilinear,cubic,cubicspline,lanczos}
                            Resampling algorithm for warping. Defaults to "near"
                            (nearest-neighbour)

    Rendering arguments:
      --min-resolution MIN_RESOLUTION
                            Minimum resolution/zoom level to render and slice.
                            Defaults to None (do not downsample)
      --max-resolution MAX_RESOLUTION
                            Maximum resolution/zoom level to render and slice.
                            Defaults to None (do not upsample)
      --fill-borders        Fill image to whole world with empty tiles. Default.
      --no-fill-borders     Do not add borders to fill image.
      --zoom-offset N       Offset zoom level by N to fit unprojected images to
                            square maps. Defaults to 0.
      --png8                Quantizes 32-bit RGBA to 8-bit RGBA paletted PNGs.
                            value range from 2 to 256. Default to False.

    Coloring arguments:
      --coloring {gradient,palette,exact}
                            Coloring algorithm.
      --color BAND-VALUE:HTML-COLOR
                            Examples: --color="0:#ff00ff" --color=255:red
      --colorize-band COLORIZE-BAND
                            Raster band to colorize. Defaults to 1


Contributing
============

Reporting bugs and submitting patches
-------------------------------------

Please check our `issue tracker`_ for known bugs and feature requests.

We accept pull requests for fixes and new features.

Development and Testing
-----------------------

We use `Tox`_ and `Pytest`_ to test locally and `CircleCI`_ for remote testing.

1. Clone the repo
2. Install whichever `External Dependencies`_ are suitable for your OS/VM.
3. Create and activate a `virtual environment`_
4. Install tox: ``pip install tox``
5. Set the GDAL_CONFIG env var for tox via the venv activations script.

   If using virtualenv:
   ``echo 'export GDAL_VERSION=$(gdal-config --version)' >> $VIRTUAL_ENV/bin/postactivate``

   If using venv:
   ``echo 'export GDAL_VERSION=$(gdal-config --version)' >> $VIRTUAL_ENV/bin/activate``

6. Run tests to confirm all is working: ``tox``
7. Do some development:

   - Make some changes
   - Run the tests
   - Fix any errors
   - Run the tests again
   - Update CHANGELOG.rst with a line about the change in the UNRELEASED section
   - Add yourself to AUTHORS.rst if not already there
   - Write a nice commit message
   - Repeat

8. Make a PR

You don't need to worry initially about testing in every combination of GDAL
and Ubuntu, leave that to the remote CI build matrix when you make a PR and let
the reviewers figure out if it needs more work from that.

Credits
=======

Maxime Dupuis and Simon Law wrote this program, with the generous
support of Ecometrica_.

See AUTHORS.rst for the full list of contributors.

.. _GDAL-readable files: http://www.gdal.org/formats_list.html
.. _MBTiles: http://mapbox.com/developers/mbtiles/
.. _MapBox: http://mapbox.com/
.. _TileStream: https://github.com/mapbox/tilestream

.. _GDAL: http://www.gdal.org/
.. _UbuntuGIS: https://launchpad.net/~ubuntugis/
.. _VIPS: http://www.vips.ecs.soton.ac.uk/

.. _GDAL_PyPI: https://https://pypi.org/project/GDAL/
.. _Tox: https://tox.readthedocs.io/
.. _Pytest: https://docs.pytest.org/
.. _virtual environment: https://packaging.python.org/guides/installing-using-pip-and-virtual-environments/#creating-a-virtual-environment

.. _issue tracker: https://github.com/ecometrica/gdal2mbtiles/issues
.. _Ecometrica: http://ecometrica.com/

.. _CircleCI: https://circleci.com/
