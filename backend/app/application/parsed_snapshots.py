"""Small per-application parsed-data cache; never stores agents or run products."""
from collections import OrderedDict
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from threading import RLock


class ParsedSnapshots:
    def __init__(self, capacity=4):
        if type(capacity) is not int or capacity < 1:
            raise ValueError('Snapshot capacity must be positive')
        self.capacity = capacity
        self._entries = OrderedDict()
        self._pending = ContextVar('parsed_snapshot_pending', default=None)
        self._lock = RLock()

    @contextmanager
    def transaction(self):
        # Publish only after the entire runtime registration succeeded.
        if self._pending.get() is not None:
            raise RuntimeError('Nested parsed snapshot transaction')
        pending = OrderedDict()
        token = self._pending.set(pending)
        try:
            yield
            with self._lock:
                self._entries.update(pending)
                for key in pending:
                    self._entries.move_to_end(key)
                while len(self._entries) > self.capacity:
                    self._entries.popitem(last=False)
        finally:
            self._pending.reset(token)

    def get(self, key):
        with self._lock:
            value = self._entries.get(key)
        # Every caller receives its own object graph, including public dicts.
        return deepcopy(value) if value is not None else None

    def stage(self, key, dataset):
        pending = self._pending.get()
        if pending is None:
            raise RuntimeError('Parsed snapshots require a registration transaction')
        pending[key] = deepcopy(dataset)
