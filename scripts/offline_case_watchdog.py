"""Opt-in passive pytest process cap; never wraps application methods."""
import json
import os
from pathlib import Path
import threading
import time

_lock = threading.Lock()
_stop = threading.Event()
_thread = None
_path = None
_active = None
_events = []
_started = time.perf_counter()


def record(kind, **values):
    with _lock:
        if len(_events) >= 6000:
            raise RuntimeError('Passive diagnostic event limit reached')
        _events.append(dict(seq=len(_events),elapsed=time.perf_counter()-_started,
            wall=time.time(),cpu=time.process_time(),kind=kind,**values))


def save(status):
    with _lock:
        value=dict(status=status,per_case_process_cap_seconds=180,
            application_methods_wrapped=False,events=list(_events))
    temporary=_path.with_suffix('.pending')
    temporary.write_text(json.dumps(value,separators=(',',':')),encoding='utf-8')
    temporary.replace(_path)


def monitor():
    while not _stop.wait(.5):
        record('sample')
        with _lock:
            active=_active
        if active and time.perf_counter()-active[1]>180:
            record('process_cap',node=active[0])
            save('DIAGNOSTIC_PROCESS_CAP')
            os._exit(124)
        save('RUNNING')


def pytest_configure(config):
    global _path,_thread
    root=Path(__file__).resolve().parents[1]
    _path=Path(os.environ['CAMPMATE_CASE_WATCHDOG_OUTPUT']).resolve()
    if not _path.is_relative_to((root/'var').resolve()):
        raise RuntimeError('Keep passive evidence in the generated var directory')
    _path.parent.mkdir(parents=True,exist_ok=True)
    record('session_start')
    _thread=threading.Thread(target=monitor,daemon=True)
    _thread.start()


def pytest_runtest_logstart(nodeid,location):
    global _active
    with _lock:
        _active=(nodeid,time.perf_counter())
    record('case_start',node=nodeid)


def pytest_runtest_logreport(report):
    record('case_report',node=report.nodeid,phase=report.when,outcome=report.outcome)


def pytest_runtest_logfinish(nodeid,location):
    global _active
    record('case_finish',node=nodeid)
    with _lock:
        _active=None


def pytest_sessionfinish(session,exitstatus):
    _stop.set()
    _thread.join()
    record('session_finish',exit_code=int(exitstatus))
    save('FINISHED')
