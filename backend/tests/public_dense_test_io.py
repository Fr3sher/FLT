"""Provider tripwire that permits the Pod unit tests' own loopback servers."""
import socket

import pytest


def restrict_to_owned_loopback(monkeypatch):
    from app import capabilities
    from app.routes import settings

    monkeypatch.setattr(capabilities, '_http_ok', lambda *_a, **_kw: False)
    monkeypatch.setattr(settings, '_lan_ip', lambda: None)
    monkeypatch.setattr(settings, '_tailscale_ip', lambda: None)
    owned_ports = set()
    local_hosts = {'127.0.0.1', '::1', 'localhost'}
    real_bind = socket.socket.bind
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex
    real_getaddrinfo = socket.getaddrinfo

    def bind(sock, address):
        result = real_bind(sock, address)
        if isinstance(address, tuple) and address[0] in local_hosts | {'0.0.0.0', '::'}:
            owned_ports.add(sock.getsockname()[1])
        return result

    def check(address):
        if (not isinstance(address, tuple) or address[0] not in local_hosts
                or address[1] not in owned_ports):
            pytest.fail('Dense unit tests must double providers; only their own loopback server is allowed.')

    def connect(sock, address):
        check(address)
        return real_connect(sock, address)

    def connect_ex(sock, address):
        check(address)
        return real_connect_ex(sock, address)

    def getaddrinfo(host, *args, **kwargs):
        if host not in local_hosts:
            pytest.fail('Dense unit tests must not resolve provider hostnames.')
        return real_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket.socket, 'bind', bind)
    monkeypatch.setattr(socket.socket, 'connect', connect)
    monkeypatch.setattr(socket.socket, 'connect_ex', connect_ex)
    monkeypatch.setattr(socket, 'getaddrinfo', getaddrinfo)


@pytest.fixture(autouse=True)
def no_dense_provider_io(monkeypatch):
    restrict_to_owned_loopback(monkeypatch)
