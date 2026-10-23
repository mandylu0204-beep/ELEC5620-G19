"""Local test-run control, never part of the production repository."""
import httpx
import pytest

blocked = 0


@pytest.fixture(autouse=True)
def forbid_real_model_http(monkeypatch):
    def forbidden(*args, **kwargs):
        global blocked
        blocked += 1
        pytest.fail('Offline suite attempted a real httpx network transport')
    monkeypatch.setattr(httpx.HTTPTransport, 'handle_request', forbidden)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', forbidden)


def pytest_terminal_summary(terminalreporter):
    terminalreporter.write_line(f'Offline real-HTTP transport blocks: {blocked}')
