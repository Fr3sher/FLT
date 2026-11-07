"""Product queue admission and durable ownership, without contacting a GPU."""
import json
from types import SimpleNamespace

import pytest
from flask import Flask

from lds_sdk import comfy


def admission_app(monkeypatch, *, enabled=True, owner='sample'):
    from app import config
    app = Flask(__name__)
    app.extensions['lds_plugins'] = SimpleNamespace(
        records={'sample': SimpleNamespace(enabled=True, state='loaded')},
        job_handlers={'is_sample': (owner, lambda *args: None)})
    monkeypatch.setattr(config, 'get', lambda key: {'sample': enabled})
    return app


@pytest.mark.parametrize('enabled,owner,metadata', [
    (False, 'sample', {}), (True, 'other', {}),
    (True, 'sample', {'is_live': True}),
    (True, 'sample', {'plugin_id': 'other'}),
])
def test_refused_job_never_reaches_queue(monkeypatch, enabled, owner, metadata):
    from app.job_queue import queue_manager
    monkeypatch.setattr(queue_manager, 'add_job', lambda **kw: pytest.fail('Unowned job admitted'))
    app = admission_app(monkeypatch, enabled=enabled, owner=owner)
    with app.app_context(), pytest.raises(ValueError):
        comfy.add_plugin_job('sample', 'is_sample', user_id='local', workflow_data={'1': {}},
                             prompt='a frame', job_id='fixed', metadata=metadata)


def test_admitted_job_keeps_host_queue_and_fixed_identity(monkeypatch):
    from app.job_queue import queue_manager
    calls = []
    monkeypatch.setattr(queue_manager, 'add_job', lambda **kw: calls.append(kw) or kw['job_id'])
    app = admission_app(monkeypatch)
    with app.app_context():
        assert comfy.add_plugin_job('sample', 'is_sample', user_id='local',
                                    workflow_data={'1': {}}, prompt='a frame', job_id='fixed',
                                    metadata={'scene': 3}) == 'fixed'
    assert calls[0]['metadata'] == {'scene': 3, 'is_sample': True, 'plugin_id': 'sample',
                                   'plugin_job_kind': 'is_sample', 'lds_plugin_job': True}


def test_reader_and_cancellation_check_user_and_product(app, monkeypatch):
    from app.extensions import db
    from app.models import ImageGenerationQueue
    from app.job_queue import queue_manager
    with app.app_context():
        row = ImageGenerationQueue(job_id='owned-job', user_id='local', status='pending',
                                   workflow_data='{}', job_metadata=json.dumps({
                                       'lds_plugin_job': True, 'plugin_id': 'sample',
                                       'plugin_job_kind': 'is_sample', 'is_sample': True}))
        db.session.add(row)
        db.session.commit()
        assert comfy.plugin_job('sample', 'owned-job', 'local')['status'] == 'pending'
        for product, user in [('other', 'local'), ('sample', 'other')]:
            assert comfy.plugin_job(product, 'owned-job', user) is None
            with pytest.raises(LookupError):
                comfy.cancel_plugin_job(product, 'owned-job', user)
        monkeypatch.setattr(queue_manager, 'cancel_job_outcome', lambda *a: 'restart_required')
        assert comfy.cancel_plugin_job('sample', 'owned-job', 'local') == 'restart_required'
        row.job_metadata = '{}'
        db.session.commit()
        assert comfy.plugin_job('sample', 'owned-job', 'local') is None


def test_manga_requires_the_queue_presentation_api():
    import json
    from pathlib import Path
    from app.plugins.package_contract import compatibility_issues, validate_contract
    manifest_path = Path(__file__).resolve().parents[2] / 'bundled/manga/plugin.json'
    if not manifest_path.is_file():
        import pytest
        pytest.skip('Manga product source is absent from this core-only tree')
    contract = validate_contract(json.loads(manifest_path.read_text(encoding='utf-8')))
    host = dict(lds_version='2026.9.9', python_version='3.14.2', system='Windows',
                machine='AMD64', dependencies={})
    issues = compatibility_issues(contract, api_version='1.15', **host)
    assert [issue['field'] for issue in issues] == ['compatibility.api']
    assert compatibility_issues(contract, api_version='1.16', **host) == []
