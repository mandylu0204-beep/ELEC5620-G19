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
        parent = self._pending.get()
        pending = OrderedDict()
        token = self._pending.set(pending)
        try:
            yield
            if parent is not None:
                parent.update(pending)
                while len(parent) > self.capacity:
                    parent.popitem(last=False)
            else:
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
        # Dataset/selector wrappers and all exported mutable values stay detached.
        # Only owned immutable safety archives may return themselves on deepcopy.
        return deepcopy(value) if value is not None else None

    def stage(self, key, dataset):
        pending = self._pending.get()
        if pending is None:
            raise RuntimeError('Parsed snapshots require a registration transaction')
        from ..adapters.snapshot_archive import compact_owned_dataset
        pending[key] = compact_owned_dataset(deepcopy(dataset))
        while len(pending) > self.capacity:
            pending.popitem(last=False)
