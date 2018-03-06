#!/usr/bin/env python



from setuptools import setup

import gdal2mbtiles


# Hack to prevent stupid TypeError: 'NoneType' object is not callable error on
# exit of python setup.py test in multiprocessing/util.py _exit_function when
# running python setup.py test (see
# http://www.eby-sarna.com/pipermail/peak/2010-May/003357.html)
import multiprocessing
multiprocessing

setup(
    name='gdal2mbtiles',
    version=gdal2mbtiles.__version__,
    description='Converts a GDAL-readable dataset into an MBTiles file. This is used to generate web maps.',
    long_description=open('README.rst').read(),
    license='Apache Software License, version 2.0',

    author='Ecometrica',
    author_email='admin@ecometrica.com',
    url='https://github.com/ecometrica/gdal2mbtiles',

    packages=['gdal2mbtiles'],
    include_package_data=True,
    install_requires=['future', 'numexpr', 'numpy', 'pyvips', 'webcolors'],
    # You also need certain dependencies that aren't in PyPi:
    # gdal-bin, libgdal-dev, libvips, libvips-dev, libtiff5, optipng, pngquant

    entry_points={
        'console_scripts': [
            'gdal2mbtiles = gdal2mbtiles.main:main',
        ]
    },
    tests_require=['pytest'],
    test_suite='tests',

    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Environment :: Console',
        'Intended Audience :: Other Audience',
        'License :: OSI Approved :: Apache Software License',
        'Operating System :: POSIX',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Topic :: Multimedia :: Graphics :: Graphics Conversion',
        'Topic :: Scientific/Engineering :: GIS',
    ],

    zip_safe=True,
)
