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


def recursive_listdir(directory):
    """Generator of all files in `directory`, recursively."""
    for root, dirs, files in os.walk(directory):
        root = os.path.relpath(root, directory)
        if root == '.':
            root = ''
        for d in dirs:
            yield os.path.join(root, d)
        for f in files:
            yield os.path.join(root, f)
