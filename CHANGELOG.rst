=============
Release Notes
=============

The format is based on `Keep a Changelog <https://keepachangelog.com/en/1.0.0/>`_
and this project attempts to adhere to `Semantic Versioning <https://semver.org/spec/v2.0.0.html>`_.

Unreleased
------------
* Fixing GDAL 3 backwards incompatible change which switches axis in coordinate transformation - see: https://github.com/OSGeo/gdal/issues/1546

2.1.3
----------

* Fix float overflow bug
* Unpin pyvips and fix related issue - install pyvips==2.1.8 if any issues
* Fix renderer tests
* Fix deprecation warnings
* Fix python3.7+ pytest errors
* Update author email
* Update CI
* Update README

2.1.2
-----

* Update docs
* Pin pyvips

2.1.1
-----

* Revert commit f7fde54, which reintroduced tiling issues fixed by 9231133.


2.1.0
-----

* Add --png8 argument to quantize 32-bit RGBA to 8-bit RGBA paletted PNGs.
* Specify `NUM_THREADS` option for gdal_translate to use all CPUs
* Update MANIFEST.in to include required files


2.0.0
-----

* Add support for Python 3.5 and 3.6
* Replace vipsCC with pyvips
* Use pytest and tox for testing
* types.py has been renamed to gd_types.py to avoid import conflicts
* Remove multiprocessing as it creates noise in mbtiles output files with
pyvips and doesn't appear to have a significant impact on processing speeds
