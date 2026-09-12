"""Offline projection checks against the existing public host, not an SDK certification.

The bridge below is test-only. Production must supply the documented named SDK
facades; this test harness neither publishes them nor creates another ORM mapper.
"""
import importlib
import importlib.abc
import importlib.util
from pathlib import Path
import socket
import subprocess
import sys
import tempfile

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class _PublicHostBridge(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'lds_sdk.cloud_history' or fullname == 'lds_sdk.cloud_host' or fullname.startswith('lds_sdk.cloud_host.'):
            return importlib.util.spec_from_loader(fullname, self, is_package=True)
        return None

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        target = ('app.services.cloud_training' if module.__name__ == 'lds_sdk.cloud_history'
                  else 'app' + module.__name__.removeprefix('lds_sdk.cloud_host'))
        public = importlib.import_module(target)
        module.__getattr__ = lambda name: getattr(public, name)


_bridge = _PublicHostBridge()
_session_patch = None
_session_temp = None


def _forbidden(*args, **kwargs):
    raise AssertionError('Cloud projection tests may not contact providers, start processes or connect sockets')


def pytest_sessionstart(session):
    global _session_patch, _session_temp
    import requests
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
    _session_patch.setattr(socket.socket, 'connect', _forbidden)
    _session_patch.setattr(socket.socket, 'connect_ex', _forbidden)
    _session_patch.setattr(socket, 'create_connection', _forbidden)
    _session_patch.setattr(requests.Session, 'request', _forbidden)
    _session_patch.setattr(subprocess, 'run', _forbidden)
    _session_patch.setattr(subprocess, 'Popen', _forbidden)


def pytest_sessionfinish(session, exitstatus):
    if _session_patch:
        _session_patch.undo()
    if _session_temp:
        _session_temp.cleanup()


@pytest.fixture(autouse=True)
def isolated_product(monkeypatch):
    import lds_sdk
    prefixes = ('lds_sdk.cloud_host', 'lds_sdk.cloud_history')
    def is_bridge(name):
        return any(name == prefix or name.startswith(prefix + '.') for prefix in prefixes)
    sdk_saved = {key: value for key, value in sys.modules.items() if is_bridge(key)}
    absent = object()
    parent_saved = {key: getattr(lds_sdk, key, absent) for key in ('cloud_host', 'cloud_history')}
    saved = {k: v for k, v in sys.modules.items() if k == 'lds_cloud_training' or k.startswith('lds_cloud_training.')}
    for name in saved.keys() | sdk_saved.keys():
        sys.modules.pop(name, None)
    for key in parent_saved:
        if hasattr(lds_sdk, key):
            delattr(lds_sdk, key)
    sys.meta_path.insert(0, _bridge)
    for key in ('VAST_API_KEY', 'HF_CLOUD_TOKEN', 'HF_TOKEN'):
        monkeypatch.delenv(key, raising=False)
    try:
        yield
    finally:
        if _bridge in sys.meta_path:
            sys.meta_path.remove(_bridge)
        for name in list(sys.modules):
            if name == 'lds_cloud_training' or name.startswith('lds_cloud_training.') or is_bridge(name):
                sys.modules.pop(name, None)
        sys.modules.update(saved)
        sys.modules.update(sdk_saved)
        for key, value in parent_saved.items():
            if value is absent:
                if hasattr(lds_sdk, key):
                    delattr(lds_sdk, key)
            else:
                setattr(lds_sdk, key, value)


@pytest.fixture()
def app(tmp_path, monkeypatch):
    from flask import Flask
    from app.extensions import db
    import app.config as cfg
    import app.models  # noqa: F401 -- register the one existing public schema
    import app.capabilities as caps

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
