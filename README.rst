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

We rely on GDAL_ to read georeferenced datasets.

Under Debian or Ubuntu, run the following to install it::

    $ sudo add-apt-repository ppa:ubuntugis/ppa && sudo apt-get update
    $ sudo apt-get install gdal-bin libgdal-dev


You will need to install the PyPi GDAL package with the following options::

    $ pip install --global-option=build_ext --global-option=--gdal-config=/usr/bin/gdal-config --global-option=--include-dirs=/usr/include/gdal/ GDAL==$(GDAL_VERSION)


We also rely on VIPS_ (version 8.2+) to do fast image processing.

Under Debian or Ubuntu, run the following to install it::

    $ sudo apt-get install libvips libvips-dev


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
