from contextlib import contextmanager
import os


@contextmanager
def tempenv(name, value):
    original = os.environ.get(name, None)
    os.environ[name] = value
    yield
    if original is None:
        del os.environ[name]
    else:
        os.environ[name] = original
