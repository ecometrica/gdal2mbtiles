======================================================
 Convert GDAL-readable datasets into an MBTiles file.
======================================================

**gdal2mbtiles** helps you generate web mapping tiles that can be shown
through a browser-based mapping library on your website.

`GDAL-readable files`_ are images that are georeference, that means that
they are positioned and projected on to the world. In order to display a
dynamic map on the web, you don't want to serve the whole image at once,
so it must be sliced into tiles that are hosted by a tile server.

The MBTiles_ file format was developed by MapBox_ to make tile storage
easier. You can upload the final file to their service, or run your own
tile server. MapBox provides one called TileStream_.


Installation
============

Using pip::

    $ pip install gdal2mbtiles

PyPi package page https://pypi.python.org/pypi/gdal2mbtiles/

From source::

    $ git clone https://github.com/ecometrica/gdal2mbtiles.git
    $ cd gdal2mbtiles
    $ python setup.py install

Note that this program requires Python 2.7 or higher.


External Dependencies
---------------------

We rely on GDAL_ to read georeferenced datasets. However, it is not
available on PyPi.

Under Debian or Ubuntu, run the following to install it::

    $ sudo apt-get install python-gdal


We also rely on VIPS_ to do fast image processing. It's also not
available on PyPi.

Under Debian or Ubuntu, run the following to install it::

    $ sudo apt-get install python-vipscc

If you are using a virtualenv, you will need to symlink Python library
in the right place. Under Debian or Ubuntu, assuming Python 2.7, run the
following::

    $ ln -s /usr/lib/python2.7/dist-packages/vipsCC $VIRTUAL_ENV/lib/python2.7/site-packages/


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
                            Minimum resolution to render and slice. Defaults to
                            None (do not downsample)
      --max-resolution MAX_RESOLUTION
                            Maximum resolution to render and slice. Defaults to
                            None (do not upsample)
      --fill-borders        Fill image to whole world with empty tiles. Default.
      --no-fill-borders     Do not add borders to fill image.
      --zoom-offset N       Offset zoom level by N to fit unprojected images to
                            square maps. Defaults to 0.

    Coloring arguments:
      --coloring {gradient,palette,exact}
                            Coloring algorithm.
      --color BAND-VALUE:HTML-COLOR
                            Examples: --color="0:#ff00ff" --color=255:red
      --colorize-band COLORIZE-BAND
                            Raster band to colorize. Defaults to 1


Reporting bugs and submitting patches
=====================================

Please check our `issue tracker`_ for known bugs and feature requests.

We accept pull requests for fixes and new features.


Credits
=======

Maxime Dupuis and Simon Law wrote this program, with the generous
support of Ecometrica_.

.. _GDAL-readable files: http://www.gdal.org/formats_list.html
.. _MBTiles: http://mapbox.com/developers/mbtiles/
.. _MapBox: http://mapbox.com/
.. _TileStream: https://github.com/mapbox/tilestream

.. _GDAL: http://www.gdal.org/
.. _VIPS: http://www.vips.ecs.soton.ac.uk/

.. _issue tracker: https://github.com/ecometrica/gdal2mbtiles/issues
.. _Ecometrica: http://ecometrica.com/
