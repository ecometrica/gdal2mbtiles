from contextlib import contextmanager
import errno
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


def makedirs(d, ignore_exists=False):
    """Like `os.makedirs`, but doesn't raise OSError if ignore_exists."""
    try:
        os.makedirs(d)
    except OSError as e:
        if ignore_exists and e.errno == errno.EEXIST:
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
