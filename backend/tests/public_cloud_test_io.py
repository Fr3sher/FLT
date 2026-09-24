"""Final transport tripwire for Cloud tests that supply their own provider doubles."""
import socket

import pytest


@pytest.fixture(autouse=True)
def no_cloud_provider_io(monkeypatch):
    from app import capabilities
    from app.routes import settings

    # Cloud route gates also collect local-tool readiness. Its HTTP probe is
    # outside these unit tests; preserve the real cloud capability probe.
    monkeypatch.setattr(capabilities, '_http_ok', lambda *_a, **_kw: False)
    monkeypatch.setattr(settings, '_lan_ip', lambda: '127.0.0.1')
    monkeypatch.setattr(settings, '_tailscale_ip', lambda: None)

    def forbidden(*_args, **_kwargs):
        pytest.fail('Cloud unit tests must provide a transport double before opening a socket.')

    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(socket.socket, 'connect_ex', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    monkeypatch.setattr(socket, 'getaddrinfo', forbidden)
