class GdalError(RuntimeError):
    # HACK: GDAL uses RuntimeError for everything!!!!!!! :-(
    pass


class UnknownResamplingMethodError(ValueError):
    pass
