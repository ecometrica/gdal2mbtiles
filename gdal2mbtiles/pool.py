from collections import deque
from functools import wraps
from multiprocessing import cpu_count, Process, Queue, TimeoutError
from Queue import Empty as QueueEmpty
from select import select
import sys
import traceback


class ChildException(RuntimeError):
    def __init__(self, exc_type, exc_repr, exc_str, format_traceback):
        self.exc_type = exc_type
        self.exc_repr = exc_repr
        self.exc_str = exc_str
        self.format_traceback = format_traceback

    def __repr__(self):
        return self.exc_repr

    def __str__(self):
        return self.exc_str

    def is_subclass(self, superclass):
        return issubclass(self.exc_type, superclass)

    def format_tb(self):
        return self.format_traceback

    def format_exception(self):
        return '\n'.join(('Traceback (most recent call last):',
                          self.format_traceback,
                          self.exc_repr))


class ApplyResult(object):
    """
    Instances returned by `apply_async()`, like multiprocessing.ApplyResult.
    """
    def __init__(self, func, args, kwds, callback, pool):
        self.func = func
        self.args = args
        self.kwds = kwds
        self.callback = callback

        self._pool = pool
        self._process = None
        self._queue = Queue()
        self._success = None
        self._result = None

    @classmethod
    def select(cls, rlist=[], wlist=[], timeout=None):
        """
        Like select(), returns (rready, wready) tuple of ApplyResults.

        rlist is an iterable of ApplyResult objects that should be ready for
        reading. wlist is the same, but for writing.

        If timeout is None, blocks until one of the ApplyResult objects is
        ready. Otherwise, it is time in seconds.

        rready is a list of ApplyResult objects that are ready for
        reading. wready is the same for writing.
        """
        rready, wready, xready = select(
            [e._queue._reader for e in rlist],
            [e._queue._writer for e in wlist],
            [],
            timeout
        )
        if rready:
            rdict = dict((e._queue._reader, e) for e in rlist)
            rready = [rdict[f] for f in rready]
        if wready:
            wdict = dict((e._queue._writer, e) for e in rlist)
            wready = [wdict[f] for f in wready]
        return (rready, wready)

    def ready(self):
        """Returns True if worker has finished."""
        return self._success is not None

    def successful(self):
        """Returns True if worker finished successfully."""
        assert self.ready()
        return self._success

    def _wait(self, timeout, maintain_pool):
        assert self._process is not None
        if self.ready():
            return

        block = False if timeout == 0 else True
        try:
            response = self._queue.get(block=block, timeout=timeout)
        except QueueEmpty:
            return
        self._success, self._result = response
        self._process.join()
        self._ready = True

        if self.callback and self._success:
            self.callback(self._result)

        if maintain_pool:
            self._pool._maintain(timeout=0)

    def wait(self, timeout=None):
        """Waits for worker to finish."""
        self._wait(timeout=timeout, maintain_pool=True)

    def get(self, block=True, timeout=None):
        """Returns the result from the worker or raises an exception."""
        self._wait(timeout=timeout, maintain_pool=True)
        if not self.ready():
            raise TimeoutError
        if not self._success:
            raise ChildException(*self._result)
        return self._result

    def _run(self):
        """Starts a worker for this result."""
        target = self._target(target=self.func, queue=self._queue)
        self._process = Process(target=target,
                                args=self.args, kwargs=self.kwds)
        self._process.start()
        return self._process

    @staticmethod
    def _target(target, queue):
        """
        Decorator to wrap `target`` to return results or Exceptions in `queue`.
        """
        @wraps(target)
        def wrapped(*args, **kwargs):
            try:
                queue.put((True, target(*args, **kwargs)))
            except Exception:
                # Exception may be unpickleable, so we have to wrap it in
                # things that are. It will get unpacked in self.get() as a
                # ChildException
                exc_type, exc_value, exc_traceback = sys.exc_info()
                queue.put((False, (exc_type, repr(exc_value), str(exc_value),
                                   traceback.format_tb(exc_traceback))))
        return wrapped


class Pool(object):
    """
    Class representing a process pool, like multiprocessing.Pool.

    Unlike multiprocessing.Pool, creates a new Process for each function call.
    This incurs more overhead in forking and cleanup, but eliminates the
    overhead from pickling.
    """
    def __init__(self, processes=None):
        if processes is None:
            processes = cpu_count()
        self._processes = processes

        self._pool = set()
        self._pending = deque()

    def apply(self, func, args=(), kwds={}):
        """Equivalent of `apply()` builtin"""
        return self.apply_async(func=func, args=args, kwds=kwds).get()

    def apply_async(self, func, args=(), kwds={}, callback=None):
        """Asynchronous equivalent of `apply()` builtin"""
        result = ApplyResult(func=func, args=args, kwds=kwds,
                             callback=callback, pool=self)
        self._pending.append(result)
        self._maintain(timeout=0)
        return result

    def join(self):
        """Waits for all workers to finish."""
        while self._pending or self._pool:
            self._maintain(timeout=None)

    def _maintain(self, timeout):
        """Cleanup any exited workers and start replacements for them."""
        # Collect dead processes
        ready = ApplyResult.select(rlist=self._pool, timeout=timeout)[0]
        for apply_result in ready:
            apply_result._wait(timeout=0, maintain_pool=False)
            self._pool.remove(apply_result)

        # Create more processes
        while self._pending and len(self._pool) < self._processes:
            apply_result = self._pending.popleft()
            self._pool.add(apply_result)
            apply_result._run()
