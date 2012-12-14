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

from contextlib import contextmanager
import errno
from hashlib import md5
import os
from shutil import rmtree
from tempfile import mkdtemp


@contextmanager
def tempenv(name, value):
    original = os.environ.get(name, None)
    os.environ[name] = value
    yield
    if original is None:
        del os.environ[name]
    else:
        os.environ[name] = original


@contextmanager
def NamedTemporaryDir(**kwargs):
    dirname = mkdtemp(**kwargs)
    yield dirname
    rmtree(dirname, ignore_errors=True)


def makedirs(d, ignore_exists=False):
    """Like `os.makedirs`, but doesn't raise OSError if ignore_exists."""
    try:
        os.makedirs(d)
    except OSError as e:
        if ignore_exists and e.errno == errno.EEXIST:
            return
        raise


def rmfile(path, ignore_missing=False):
    """Like `os.remove`, but doesn't raise OSError if ignore_missing."""
    try:
        os.remove(path)
    except OSError as e:
        if ignore_missing and e.errno == errno.ENOENT:
            return
        raise


def recursive_listdir(directory):
    """Generator of all files in `directory`, recursively."""
    for root, dirs, files in os.walk(directory):
        root = os.path.relpath(root, directory)
        if root == '.':
            root = ''
        for d in dirs:
            yield os.path.join(root, d) + os.path.sep
        for f in files:
            yield os.path.join(root, f)


def intmd5(x):
    """Returns the MD5 digest of `x` as an integer."""
    return int(md5(x).hexdigest(), base=16)
