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

You can get a copy of the source by using::

    $ git clone https://github.com/ecometrica/gdal2mbtiles.git

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
