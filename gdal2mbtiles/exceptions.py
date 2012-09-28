from subprocess import CalledProcessError


class GdalError(RuntimeError):
    # HACK: GDAL uses RuntimeError for everything!!!!!!! :-(
    pass


class GdalWarpError(CalledProcessError, GdalError):
    def __init__(self, returncode, cmd, output=None, error=None):
        super(GdalWarpError, self).__init__(returncode=returncode, cmd=cmd,
                                            output=output)
        self.error = error

    def __str__(self):
        return super(GdalWarpError, self).__str__() + ': %s' % self.error


class UnknownResamplingMethodError(ValueError):
    pass
