"""Opt-in pytest control: reject real httpx transports, allow Mock/ASGI only."""
import httpx
import pytest

blocked = 0


@pytest.fixture(autouse=True)
def forbid_real_http(monkeypatch):
    def forbidden(*args, **kwargs):
        global blocked
        blocked += 1
        pytest.fail('Offline test attempted a real httpx transport')
    monkeypatch.setattr(httpx.HTTPTransport, 'handle_request', forbidden)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', forbidden)


def pytest_terminal_summary(terminalreporter):
    terminalreporter.write_line(f'Offline unexpected real-HTTP transport attempts: {blocked}')
