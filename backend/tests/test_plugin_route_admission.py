"""An OFF plugin cannot enter its HTTP handlers or blueprint hooks."""
from flask import Flask
from flask_wtf import CSRFProtect
import pytest

from app import config as cfg
from app.plugins.loader import load_plugins
from test_plugin_registration import host, write_plugin  # noqa: F401


ROUTES = '''
from flask import Blueprint, current_app
first, second = Blueprint('admission_first', __name__), Blueprint('admission_second', __name__)
@first.before_request
def before():
    current_app.extensions['entered'] = current_app.extensions.get('entered', 0) + 1
@first.route('/work', methods=['GET', 'POST'])
def work():
    return {'owner': 'sample.feature'}
@second.get('/read')
def read():
    return {'owner': 'sample.feature'}
def register(ctx):
    ctx.register_blueprint(first)
    ctx.register_blueprint(second, url_prefix='/api/second')
'''


@pytest.mark.parametrize(('method', 'url'), [
    ('GET', '/api/plugins/sample.feature/work'),
    ('POST', '/api/plugins/sample.feature/work'),
    ('GET', '/api/second/read'),
])
def test_disabled_product_is_refused_before_its_blueprint_hooks(host, method, url):
    app, csrf, root = host
    write_plugin(root / 'plugins', 'sample.feature', package='lds_registration_admission', code=ROUTES)
    app.add_url_rule('/api/core', 'core', lambda: {'core': True})
    loaded = load_plugins(app, csrf)
    assert loaded.records['sample.feature'].state == 'loaded'
    client = app.test_client()
    assert client.open(url, method=method).status_code == 200
    entered = app.extensions.get('entered', 0)
    cfg.save_config({'plugins': {'enabled': {'sample.feature': False}}})
    response = client.open(url, method=method)
    assert response.status_code == 409
    assert response.get_json()['code'] == 'plugin_unavailable'
    assert app.extensions.get('entered', 0) == entered
    assert client.get('/api/core').get_json() == {'core': True}


def test_shared_blueprints_can_register_on_another_app_without_retaining_its_state(host):
    app, csrf, root = host
    write_plugin(root / 'plugins', 'sample.feature', package='lds_registration_admission', code=ROUTES)
    first = load_plugins(app, csrf)
    second_app = Flask(__name__)
    second_app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    second = load_plugins(second_app, CSRFProtect(second_app))
    assert second.records['sample.feature'].state == 'loaded'
    first.records['sample.feature'].state = 'error'
    url = '/api/plugins/sample.feature/work'
    assert app.test_client().get(url).status_code == 409
    assert second_app.test_client().get(url).status_code == 200


@pytest.mark.parametrize(('decorator', 'url', 'expected'), [
    ('before_app_request', '/api/plugins/sample.feature/work', 409),
    ('before_app_request', '/api/core', 200),
    ('url_value_preprocessor', '/api/plugins/sample.feature/work', 409),
    ('app_url_value_preprocessor', '/api/plugins/sample.feature/work', 409),
    ('app_url_value_preprocessor', '/api/core', 200),
])
def test_off_plugin_cannot_run_early_or_global_blueprint_callbacks(host, decorator, url, expected):
    app, csrf, root = host
    code = ROUTES + f'''
@first.{decorator}
def early(*args):
    current_app.extensions['early'] = current_app.extensions.get('early', 0) + 1
    return {{'intercepted': True}}, 202
'''
    write_plugin(root / 'plugins', 'sample.feature', package='lds_registration_admission', code=code)
    app.add_url_rule('/api/core', 'core', lambda: {'core': True})
    load_plugins(app, csrf)
    client = app.test_client()
    client.get(url)
    assert app.extensions['early'] == 1
    cfg.save_config({'plugins': {'enabled': {'sample.feature': False}}})
    response = client.get(url)
    assert response.status_code == expected
    assert app.extensions['early'] == 1
    if expected == 200:
        assert response.get_json() == {'core': True}
