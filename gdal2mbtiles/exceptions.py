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
