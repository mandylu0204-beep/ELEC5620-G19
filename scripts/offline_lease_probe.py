"""Opt-in pytest timing probe: finite labels/stacks only, never application data.

Run only with a generated evidence path in CAMPMATE_LEASE_PROBE_OUTPUT. The
180-second diagnostic process cap is independent of all production deadlines.
"""
import asyncio
from contextlib import contextmanager
from functools import wraps
import inspect
import json
import os
from pathlib import Path
import sys
import threading
import time

_lock = threading.Lock()
_events = []
_active = {}
_stop = threading.Event()
_restore = []
_start = time.perf_counter()
_dropped = 0
_output = None


def record(label, phase, **fields):
    global _dropped
    with _lock:
        if len(_events) >= 12000:
            _dropped += 1
            return
        row = dict(seq=len(_events), elapsed=time.perf_counter()-_start,
            wall=time.time(), cpu=time.process_time(), thread=threading.get_ident(),
            label=label, phase=phase, **fields)
        _events.append(row)


def save(status):
    with _lock:
        value = dict(status=status, events=list(_events), dropped=_dropped,
            production_limits_modified=False, process_cap_seconds=180)
    _output.write_text(json.dumps(value, separators=(',', ':')), encoding='utf-8')


def enter(label):
    ident = threading.get_ident()
    with _lock:
        _active.setdefault(ident, []).append(label)
    record(label, 'start')


def leave(label):
    record(label, 'end')
    ident = threading.get_ident()
    with _lock:
        _active[ident].pop()


def wrap(owner, name, label):
    original = getattr(owner, name)
    if inspect.iscoroutinefunction(original):
        @wraps(original)
        async def wrapped(*args, **kwargs):
            enter(label)
            try:
                return await original(*args, **kwargs)
            finally:
                leave(label)
    else:
        @wraps(original)
        def wrapped(*args, **kwargs):
            enter(label)
            try:
                return original(*args, **kwargs)
            finally:
                leave(label)
    setattr(owner, name, wrapped)
    _restore.append((owner, name, original))


def monitor():
    count = 0
    while not _stop.wait(.5):
        record('monitor', 'sample')
        count += 1
        if count % 10 == 0:
            # Code locations only. Never inspect local variables or arguments.
            frames = sys._current_frames()
            with _lock:
                threads = {key:list(value) for key,value in _active.items() if value}
            for ident, labels in threads.items():
                frame = frames.get(ident)
                stack = []
                while frame is not None and len(stack) < 12:
                    stack.append([Path(frame.f_code.co_filename).name,
                                  frame.f_code.co_name,frame.f_lineno])
                    frame = frame.f_back
                record('monitor', 'stack', observed_thread=ident, labels=labels, stack=stack)
            del frames
        save('RUNNING')
        if time.perf_counter()-_start > 180:
            record('diagnostic', 'process_cap')
            save('DIAGNOSTIC_PROCESS_CAP')
            os._exit(124)


def pytest_configure(config):
    global _output
    root = Path(__file__).resolve().parents[1]
    _output = Path(os.environ['CAMPMATE_LEASE_PROBE_OUTPUT']).resolve()
    assert _output.is_relative_to((root/'var').resolve())
    _output.parent.mkdir(parents=True, exist_ok=True)
    from app.application.agent_runtime import AgentRuntime
    from app.adapters.synthetic_dataset_v2 import SyntheticDatasetV2Adapter
    from app.storage.database import Database
    from app.storage.workflows import RecoveryPort, WorkflowService
    from app.storage.port import SqlitePersistencePort
    from app.agents.hybrid_planning_agent import HybridPlanningAgent
    from starlette.testclient import TestClient
    for owner,names in ((AgentRuntime, ['resolve','_resolve','for_scope']),
            (SyntheticDatasetV2Adapter,['load']),
            (RecoveryPort,['active','load_checkpoint','save_model_safety_assessment']),
            (SqlitePersistencePort,['save_model_version']),
            (WorkflowService,['renew','expire']),
            (HybridPlanningAgent,['generate_or_revise_itinerary','assess_safety_with_trace']),
            (TestClient,['request'])):
        for name in names:
            if hasattr(owner,name):
                wrap(owner,name,owner.__name__+'.'+name)
    original = Database.transaction
    @contextmanager
    @wraps(original)
    def transaction(*args, **kwargs):
        label = 'Database.transaction.write' if kwargs.get('write',True) else 'Database.transaction.read'
        enter(label)
        try:
            with original(*args, **kwargs) as connection:
                record(label,'acquired')
                yield connection
                record(label,'leaving')
        finally:
            leave(label)
    Database.transaction = transaction
    _restore.append((Database,'transaction',original))
    record('diagnostic','start')
    threading.Thread(target=monitor, daemon=True).start()


def pytest_sessionfinish(session, exitstatus):
    _stop.set()
    record('diagnostic','finished',exit_code=int(exitstatus))
    save('FINISHED')
    for owner,name,original in reversed(_restore):
        setattr(owner,name,original)
