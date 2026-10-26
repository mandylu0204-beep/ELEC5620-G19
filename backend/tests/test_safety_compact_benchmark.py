"""Portable loop bootstrap without granting benchmark code real networking."""
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys

import httpx
import pytest

ROOT=Path(__file__).resolve().parents[2]


@pytest.fixture(scope='module')
def benchmark():
    spec=importlib.util.spec_from_file_location('compact_benchmark_under_test',
        ROOT/'scripts/safety_compact_benchmark.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def methods():
    return (socket.socket.connect,socket.socket.connect_ex,socket.create_connection,
        httpx.HTTPTransport.handle_request,httpx.AsyncHTTPTransport.handle_async_request)


def test_full_benchmark_retains_recorded_byte_results(benchmark):
    expected=json.loads((ROOT/'evidence/b-safety-compact-offline.json').read_text())['portable_fixture_metrics']
    actual=benchmark.compare()
    # Lengths and complete facts/results must remain the original comparison;
    # request digests are checked between two executions in this same runtime.
    for version in ('v3','v4'):
        for field in ('serialized_http_request_bytes','mock_action_utf8_bytes','facts_utf8_bytes'):
            assert actual[version][field]==expected[version][field]
    assert actual['reduction']==expected['reduction']
    assert actual['same_complete_assessment'] and actual['same_complete_expanded_advice']
    assert actual['lossless_fact_projection'] and actual['actual_campus_calls']==0
    assert benchmark.compare()==actual


def test_windows_style_bootstrap_precedes_guards(benchmark,monkeypatch):
    original_loop=asyncio.events.new_event_loop
    original_connect=socket.socket.connect
    sentinel=object()
    startup=[]
    def connect(sock,address):
        if sock is sentinel:
            startup.append(address)
            return None  # Simulate only the private stdlib bootstrap; no wire IO.
        return original_connect(sock,address)  # Native Windows self-pipe if present.
    def new_loop():
        socket.socket.connect(sentinel,('127.0.0.1',49371))
        return original_loop()
    async def compare(case):
        with pytest.raises(AssertionError,match='No real network'):
            socket.socket.connect(sentinel,('127.0.0.1',49371))
        return {'actual_campus_calls':0}
    monkeypatch.setattr(socket.socket,'connect',connect)
    monkeypatch.setattr(asyncio.events,'new_event_loop',new_loop)
    monkeypatch.setattr(benchmark,'fixture',lambda:object())
    monkeypatch.setattr(benchmark,'_compare_async',compare)
    assert benchmark.compare()=={'actual_campus_calls':0}
    assert startup==[('127.0.0.1',49371)]
    assert socket.socket.connect is connect


@pytest.mark.parametrize('method',['connect','connect_ex','create_connection'])
@pytest.mark.parametrize('address',[('10.167.60.148',8000),('198.51.100.1',443),
    ('127.0.0.1',8000),('::1',8000)])
def test_real_and_arbitrary_loopback_connections_still_forbidden(benchmark,monkeypatch,method,address):
    # An unguarded helper must fail safely without DNS/socket IO even if this
    # regression breaks the protection being tested.
    original_create_connection=socket.create_connection
    def unexpected(target,*args,**kwargs):
        if target==address:
            raise AssertionError('UNGUARDED_HELPER_MUST_NOT_RUN')
        # Do not replace a possible native stdlib bootstrap with a fake socket;
        # test traffic is the exact address above and must never get this far.
        return original_create_connection(target,*args,**kwargs)
    monkeypatch.setattr(socket,'create_connection',unexpected)
    async def compare(case):
        with pytest.raises(AssertionError,match='No real network'):
            if method=='create_connection':
                socket.create_connection(address)
            else:
                # A non-socket sentinel cannot open a real connection if a
                # missing guard accidentally delegates to the native descriptor.
                getattr(socket.socket,method)(object(),address)
        return {}
    monkeypatch.setattr(benchmark,'_compare_async',compare)
    benchmark.compare(object())


@pytest.mark.parametrize('kind',['sync','async'])
def test_real_http_transports_blocked_before_dispatch(benchmark,monkeypatch,kind):
    async def compare(case):
        request=httpx.Request('POST','http://10.167.60.148:8000/v1/chat/completions')
        with pytest.raises(AssertionError,match='No real network'):
            if kind=='sync':
                httpx.HTTPTransport.handle_request(None,request)
            else:
                await httpx.AsyncHTTPTransport.handle_async_request(None,request)
        return {}
    monkeypatch.setattr(benchmark,'_compare_async',compare)
    benchmark.compare(object())


def test_fixture_loading_is_guarded_too(benchmark,monkeypatch):
    def fixture():
        with pytest.raises(AssertionError,match='No real network'):
            socket.socket.connect(object(),('127.0.0.1',8000))
        return 'loaded-under-guard'
    async def compare(case):
        assert case=='loaded-under-guard'
        return {}
    monkeypatch.setattr(benchmark,'fixture',fixture)
    monkeypatch.setattr(benchmark,'_compare_async',compare)
    benchmark.compare()


@pytest.mark.parametrize('failure',['none','fixture','model','cancelled'])
def test_guards_restore_after_success_failure_or_cancellation(benchmark,monkeypatch,failure):
    before=methods()
    created=[]
    original_loop=asyncio.events.new_event_loop
    def new_loop():
        loop=original_loop();created.append(loop)
        return loop
    monkeypatch.setattr(asyncio.events,'new_event_loop',new_loop)
    def fixture():
        if failure=='fixture':raise ValueError('synthetic fixture failure')
        return object()
    async def compare(case):
        if failure=='model':raise RuntimeError('synthetic model failure')
        if failure=='cancelled':raise asyncio.CancelledError()
        return {'ok':True}
    monkeypatch.setattr(benchmark,'fixture',fixture)
    monkeypatch.setattr(benchmark,'_compare_async',compare)
    if failure=='none':assert benchmark.compare()=={'ok':True}
    else:
        cls={'fixture':ValueError,'model':RuntimeError,'cancelled':asyncio.CancelledError}[failure]
        with pytest.raises(cls):benchmark.compare()
    assert methods()==before
    assert len(created)==1 and created[0].is_closed()


def test_pending_task_cleanup_remains_under_network_guards(benchmark,monkeypatch):
    events=[]
    original_create_connection=socket.create_connection
    def fallback(target,*args,**kwargs):
        if target==('127.0.0.1',8000):
            events.append('unguarded')
            raise AssertionError('UNGUARDED_HELPER_MUST_NOT_RUN')
        return original_create_connection(target,*args,**kwargs)
    monkeypatch.setattr(socket,'create_connection',fallback)
    async def compare(case):
        async def pending():
            try:await asyncio.Event().wait()
            finally:
                try:socket.create_connection(('127.0.0.1',8000))
                except AssertionError as exc:
                    events.append('guarded' if 'No real network' in str(exc) else 'wrong-error')
        asyncio.create_task(pending())
        await asyncio.sleep(0)
        return {}
    monkeypatch.setattr(benchmark,'_compare_async',compare)
    benchmark.compare(object())
    assert events==['guarded']
    assert socket.create_connection is fallback


def test_async_generator_cleanup_still_blocks_network(benchmark,monkeypatch):
    events=[];retained=[]
    async def compare(case):
        async def generator():
            try:yield 'open'
            finally:
                try:socket.socket.connect(object(),('127.0.0.1',8000))
                except AssertionError:events.append('guarded')
        value=generator();retained.append(value)
        assert await value.__anext__()=='open'
        return {}
    monkeypatch.setattr(benchmark,'_compare_async',compare)
    benchmark.compare(object())
    assert events==['guarded'] and retained[0].ag_frame is None


def test_cli_uses_native_event_loop_and_emits_only_finite_metrics(tmp_path):
    env=dict(os.environ)
    env.update(PYTHONDONTWRITEBYTECODE='1',CAMPMATE_EXECUTION_MODE='stub',
        CAMPMATE_LOGISTICS_EXECUTION='rules',CAMPMATE_SAFETY_EXECUTION='rules',
        CAMPMATE_DATABASE_PATH=str(tmp_path/'unused.sqlite3'))
    result=subprocess.run([sys.executable,'-B','scripts/safety_compact_benchmark.py'],
        cwd=ROOT,env=env,capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr
    value=json.loads(result.stdout)
    assert value['actual_campus_calls']==0
    assert value['same_complete_assessment'] and value['same_complete_expanded_advice']
    assert value['v4']['serialized_http_request_bytes'][1]<value['v3']['serialized_http_request_bytes'][1]
    assert 'messages' not in value and 'api_key' not in value
