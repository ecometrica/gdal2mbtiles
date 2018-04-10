=============
Release Notes
=============

2.1.1
-----
Revert commit f7fde54, which reintroduced tiling issues fixed by 9231133.

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
