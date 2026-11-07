"""Offline product checks using the real named SDK and the existing main schema."""
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


_session_patch = None
_session_temp = None


def _forbidden(*args, **kwargs):
    raise AssertionError('Cloud projection tests may not contact providers, start processes or connect sockets')


def pytest_sessionstart(session):
    global _session_patch, _session_temp
    _session_patch = pytest.MonkeyPatch()
    _session_temp = tempfile.TemporaryDirectory(prefix='lds-public-cloud-offline-')
    for key, value in {
        'LDS_ENV': str(Path(_session_temp.name) / '.env'),
        'LDS_CONFIG': str(Path(_session_temp.name) / 'config.json'),
        'LDS_DATA_DIR': str(Path(_session_temp.name) / 'data'),
    }.items():
        _session_patch.setenv(key, value)
    for key in ('VAST_API_KEY', 'HF_CLOUD_TOKEN', 'HF_TOKEN'):
        _session_patch.delenv(key, raising=False)


def pytest_sessionfinish(session, exitstatus):
    if _session_patch:
        _session_patch.undo()
    if _session_temp:
        _session_temp.cleanup()


@pytest.fixture(autouse=True)
def isolated_product(monkeypatch):
    import requests
    monkeypatch.setattr(socket.socket, 'connect', _forbidden)
    monkeypatch.setattr(socket.socket, 'connect_ex', _forbidden)
    monkeypatch.setattr(socket, 'create_connection', _forbidden)
    monkeypatch.setattr(requests.Session, 'request', _forbidden)
    monkeypatch.setattr(threading.Thread, 'start', _forbidden)
    monkeypatch.setattr(subprocess, 'run', _forbidden)
    monkeypatch.setattr(subprocess, 'Popen', _forbidden)
    saved = {k: v for k, v in sys.modules.items() if k == 'lds_cloud_training' or k.startswith('lds_cloud_training.')}
    for name in saved:
        sys.modules.pop(name, None)
    for key in ('VAST_API_KEY', 'HF_CLOUD_TOKEN', 'HF_TOKEN'):
        monkeypatch.delenv(key, raising=False)
    try:
        yield
    finally:
        for name in list(sys.modules):
            if name == 'lds_cloud_training' or name.startswith('lds_cloud_training.'):
                sys.modules.pop(name, None)
        sys.modules.update(saved)


@pytest.fixture()
def app(tmp_path, monkeypatch, isolated_product):
    from flask import Flask
    from app.extensions import db
    import app.config as cfg
    import app.models  # noqa: F401 -- register the one existing public schema
    import app.capabilities as caps
    from lds_cloud_training import cloud_training, cloud_video_training

    class DeferredThread:
        def __init__(self, **kwargs):
            self.name = kwargs.get('name')

        def start(self):
            pass  # A launch test records a worker request; it never executes it.

        def is_alive(self):
            return False

        def join(self, timeout=None):
            pass

    fake_threads = SimpleNamespace(**(vars(threading) | {'Thread': DeferredThread}))
    monkeypatch.setattr(cloud_training, 'threading', fake_threads)
    # Business unit tests exercise an admitted product. Real loader admission
    # and OFF recovery are exercised in backend/test_public_cloud_safety.py.
    monkeypatch.setattr(cloud_training, 'is_available', lambda _pid: True)
    monkeypatch.setattr(cloud_video_training, 'threading', fake_threads, raising=False)

    for key, path in (('LDS_DATA_DIR', tmp_path / 'data'), ('LDS_CONFIG', tmp_path / 'config.json'), ('LDS_ENV', tmp_path / '.env')):
        monkeypatch.setenv(key, str(path))
    monkeypatch.setattr(cfg, 'ENV_PATH', tmp_path / '.env')
    monkeypatch.setattr(cfg, '_cache', None)
    monkeypatch.setattr(caps, 'probe', lambda: {'cloud_training': bool(cfg.secret('VAST_API_KEY'))})
    application = Flask('cloud-projection-tests')
    application.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI='sqlite:///:memory:', SQLALCHEMY_TRACK_MODIFICATIONS=False)
    db.init_app(application)
    with application.app_context():
        db.create_all()
    yield application
    with application.app_context():
        db.session.remove()
        db.drop_all()
        db.engine.dispose()


@pytest.fixture()
def client(app):
    from lds_cloud_training.routes import bp
    app.register_blueprint(bp, url_prefix='/api')
    return app.test_client()
