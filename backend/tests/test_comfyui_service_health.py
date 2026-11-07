from types import SimpleNamespace

import requests

from app.services import comfyui_service as service_module


class ConnectedSocket:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def settimeout(self, timeout):
        pass

    def connect_ex(self, address):
        return 0


def test_generation_health_never_downloads_history(monkeypatch):
    monkeypatch.setattr(service_module.socket, 'socket', lambda *args: ConnectedSocket())
    monkeypatch.setattr(service_module.cfg, 'get', lambda key: 'http://localhost:8188')
    seen = []

    def get(url, **kwargs):
        seen.append(url)
        return SimpleNamespace(status_code=200)

    monkeypatch.setattr(service_module.requests, 'get', get)
    service = service_module.ComfyUIService()
    assert service.ensure_comfyui_running() == (True, 'Running')
    assert seen == ['http://localhost:8188/system_stats']


def test_slow_generation_check_is_not_reported_as_stopped(monkeypatch):
    monkeypatch.setattr(service_module.socket, 'socket', lambda *args: ConnectedSocket())
    monkeypatch.setattr(service_module.cfg, 'get', lambda key: 'http://localhost:8188')

    def slow(*args, **kwargs):
        raise requests.exceptions.ReadTimeout()

    monkeypatch.setattr(service_module.requests, 'get', slow)
    service = service_module.ComfyUIService()
    ok, message = service.ensure_comfyui_running()
    assert not ok
    assert 'too slowly' in message
    assert 'not running' not in message

    def offline(*args, **kwargs):
        raise requests.exceptions.ConnectionError()

    monkeypatch.setattr(service_module.requests, 'get', offline)
    ok, message = service.ensure_comfyui_running()
    assert not ok
    assert 'not reachable' in message
    assert 'too slowly' not in message
