"""Provider tests with an isolated SDK adapter and no external runtime access.

The core configuration/error primitives are real; SDK wiring is simulated.
These tests do not qualify a host's engine dispatch or plugin activation.
"""
from copy import deepcopy
import importlib
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
from types import ModuleType

from flask import Flask
import pytest


ROOT = Path(__file__).resolve().parents[3]
PLUGIN = Path(__file__).resolve().parents[1]


def _forbidden(*_args, **_kwargs):
    raise AssertionError('External runtime access is forbidden in provider unit tests.')


@pytest.fixture(autouse=True)
def sdk_adapter(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(ROOT / 'backend'))
    monkeypatch.syspath_prepend(str(PLUGIN))
    monkeypatch.setenv('LDS_ENV', str(tmp_path / 'missing.env'))
    monkeypatch.setenv('LDS_CONFIG', str(tmp_path / 'config.json'))
    monkeypatch.setenv('LDS_DATA_DIR', str(tmp_path / 'data'))
    from app import config
    from app.services import engine_errors
    monkeypatch.setattr(config, 'ENV_PATH', tmp_path / 'missing.env')
    monkeypatch.setattr(config, 'DEFAULTS', deepcopy(config.DEFAULTS))
    monkeypatch.setattr(config, '_cache', None)
    for key in config.SECRET_KEYS:
        monkeypatch.delenv(key, raising=False)

    sdk = ModuleType('lds_sdk')
    sdk.__path__ = []
    config_adapter = ModuleType('lds_sdk.config')
    for name in ('get', 'secret', 'save_config'):
        setattr(config_adapter, name, getattr(config, name))
    config_adapter.data_dir = config._data_dir
    errors_adapter = ModuleType('lds_sdk.engine_errors')
    for name in ('EngineError', 'EngineFatal', 'EngineRefused', 'provider_error_message'):
        setattr(errors_adapter, name, getattr(engine_errors, name))
    # The host owns these two shared exception identities after extraction.
    errors_adapter.SubscriptionQuotaExceeded = type('SubscriptionQuotaExceeded', (RuntimeError,), {})
    errors_adapter.SubscriptionUnavailable = type('SubscriptionUnavailable', (RuntimeError,), {})
    sdk.config, sdk.engine_errors = config_adapter, errors_adapter
    for name, module in (('lds_sdk', sdk), ('lds_sdk.config', config_adapter),
                         ('lds_sdk.engine_errors', errors_adapter)):
        monkeypatch.setitem(sys.modules, name, module)
    # A prior host test may have imported another plugin copy. Restore it after
    # this test rather than reusing its globals or leaving our SDK adapter in it.
    previous = {name: module for name, module in sys.modules.items()
                if name == 'lds_api_engines' or name.startswith('lds_api_engines.')}
    for name in previous:
        sys.modules.pop(name)
    monkeypatch.setattr('requests.sessions.Session.request', _forbidden)
    monkeypatch.setattr(socket.socket, 'connect', _forbidden)
    monkeypatch.setattr(socket.socket, 'connect_ex', _forbidden)
    monkeypatch.setattr(socket, 'create_connection', _forbidden)
    monkeypatch.setattr(subprocess, 'run', _forbidden)
    monkeypatch.setattr(subprocess, 'Popen', _forbidden)
    monkeypatch.setattr(threading.Thread, 'start', _forbidden)
    try:
        oauth = importlib.import_module('lds_api_engines.chatgpt_oauth')
        monkeypatch.delenv('CODEX_HOME', raising=False)
        monkeypatch.setattr(oauth, 'codex_auth_path', lambda: Path(
            os.environ.get('CODEX_HOME', str(tmp_path / 'no-codex'))) / 'auth.json')
        yield sdk
    finally:
        for name in tuple(sys.modules):
            if name == 'lds_api_engines' or name.startswith('lds_api_engines.'):
                sys.modules.pop(name)
        sys.modules.update(previous)


@pytest.fixture
def app():
    application = Flask('api-engines-unit-tests')
    application.config.update(TESTING=True, SECRET_KEY='test-only')
    return application
