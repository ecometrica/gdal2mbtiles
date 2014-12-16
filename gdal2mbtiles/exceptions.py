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

from subprocess import CalledProcessError


class GdalError(RuntimeError):
    # HACK: GDAL uses RuntimeError for everything!!!!!!! :-(
    pass


class CalledGdalError(CalledProcessError, GdalError):
    """Error when calling a GDAL command-line utility."""
    def __init__(self, returncode, cmd, output=None, error=None):
        super(CalledGdalError, self).__init__(returncode=returncode, cmd=cmd,
                                              output=output)
        self.error = error

    def __str__(self):
        return super(CalledGdalError, self).__str__() + ': %s' % self.error


class UnalignedInputError(ValueError):
    pass


class UnknownResamplingMethodError(ValueError):
    pass


class VrtError(ValueError):
    pass
