=============
Release Notes
=============

2.0.0
-----

* Add support for Python 3.5 and 3.6
* Replace vipsCC with pyvips
* Use pytest and tox for testing
* types.py has been renamed to gd_types.py to avoid import conflicts
* Remove multiprocessing as it creates noise in mbtiles output files with
pyvips and doesn't appear to have a significant impact on processing sppeds
