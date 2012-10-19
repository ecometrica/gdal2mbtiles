from contextlib import contextmanager
import errno
from hashlib import md5
import os
import platform
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


def get_hasher():
    """Returns a sensible, fast hashing algorithm"""
    try:
        import smhasher

        machine = platform.machine()
        if machine == 'x86_64':
            return smhasher.murmur3_x64_128
        elif machine == 'i386':
            return smhasher.murmur3_x86_128
    except ImportError:
        pass
    # No hasher was found
    return intmd5
