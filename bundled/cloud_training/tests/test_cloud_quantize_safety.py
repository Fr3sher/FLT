"""Quantize cleanup needs durable local ownership and the launch credential."""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest


@pytest.fixture
def lane(app, monkeypatch):
    from lds_cloud_training import cloud_quantize as cq
    monkeypatch.setenv('VAST_API_KEY', 'fixture-account-a')
    monkeypatch.setenv('HF_CLOUD_TOKEN', 'fixture-hub-a')
    monkeypatch.setattr('threading.Thread.start', lambda *_a, **_k: pytest.fail('Real worker forbidden'))
    with app.app_context():
        yield cq


def test_label_prefix_is_never_authority_to_destroy_a_foreign_pod(lane, monkeypatch):
    deleted = []
    monkeypatch.setattr(lane.vast_client, 'list_instances', lambda **_kw: [
        {'instance_id': 70, 'label': lane.LABEL_PREFIX + 'foreign-installation'},
        {'instance_id': 71, 'label': lane.LABEL_PREFIX + 'a' * 32},
    ])
    monkeypatch.setattr(lane.vast_client, 'destroy_instance',
                        lambda pod, **_kw: deleted.append(pod) or True)
    assert lane.reconcile_orphans() == []
    assert deleted == []


def test_legacy_status_without_account_provenance_never_lists_or_deletes(lane, monkeypatch):
    lane.queue_manager._set_system_state('cloud_quantize', {
        'status': 'running', 'instance_id': 70, 'label': lane.LABEL_PREFIX + 'old'}, ttl_seconds=None)
    monkeypatch.setattr(lane.vast_client, 'list_instances',
                        lambda **_kw: pytest.fail('No durable account proof permits a listing'))
    assert lane.reconcile_orphans() == []
    assert lane.has_unreleased_rental()
    assert lane.status().get('cleanup_pending') is True


def test_damaged_local_receipt_is_retained_without_provider_calls(lane, monkeypatch):
    damaged = {'schema_version': 1, 'label': lane.LABEL_PREFIX + 'bad', 'instance_id': 70}
    lane.queue_manager._set_system_state('cloud_quantize_rental', deepcopy(damaged), ttl_seconds=None)
    monkeypatch.setattr(lane.vast_client, 'list_instances',
                        lambda **_kw: pytest.fail('Damaged proof must not contact a provider'))
    assert lane.reconcile_orphans() == []
    assert lane.queue_manager._get_system_state('cloud_quantize_rental') == damaged


@pytest.mark.parametrize('raw', ['not-json', 'null', '{}', '{"v": null, "exp": null}',
                                  '{"v": {}, "exp": 0}'])
def test_corrupt_or_expiring_receipt_envelope_blocks_admission_without_erasure(lane, raw):
    from lds_sdk.cloud_host.extensions import db
    from lds_sdk.cloud_host.models import SystemState
    db.session.add(SystemState(key=lane._RENTAL_KEY, value=raw))
    db.session.commit()
    assert lane.has_unreleased_rental() is True
    assert db.session.get(SystemState, lane._RENTAL_KEY).value == raw


@pytest.mark.parametrize('state', ['error', 'done', 'corrupt', 'empty'])
def test_disable_keeps_cleanup_available_until_rental_release_is_proven(lane, monkeypatch, state):
    from lds_cloud_training import _disable_blockers
    from lds_sdk.cloud_host.extensions import db
    from lds_sdk.cloud_host.models import SystemState

    if state in ('error', 'done'):
        lane.queue_manager._set_system_state('cloud_quantize', {
            'status': state, 'instance_id': 70, 'label': lane.LABEL_PREFIX + 'old'}, ttl_seconds=None)
    elif state == 'corrupt':
        db.session.add(SystemState(key=lane._RENTAL_KEY, value='not-json'))
        db.session.commit()
    monkeypatch.setattr(lane.vast_client, 'list_instances',
                        lambda **_kw: pytest.fail('Disable must not contact a provider'))
    reasons = _disable_blockers('cloud_training', ['existing'])
    assert reasons[0] == 'existing'
    if state == 'empty':
        assert reasons == ['existing']
    else:
        assert len(reasons) == 2
        assert 'quantization rental' in reasons[1]


OFFER = {'offer_id': 77, 'machine_id': 5, 'gpu_name': 'fixture', 'dph_total': 0.09,
         'inet_down': 1000, 'disk_space_gb': 512.0}
PLAN = {'repo_id': 'fixture/model', 'weight_path': 'master.safetensors',
        'weight_name': 'master.safetensors', 'output_name': 'master_fp8.safetensors',
        'source_bytes': 1_000_000_000, 'output_bytes_typical': 400_000_000,
        'offer': OFFER, 'disk_gb': 60, 'price_per_hour': 0.09,
        'estimated_cost': 0.009, 'keep_bf16': True}


class Fleet:
    """Transport-only fake; credential/context/error types and retry loop stay real."""
    def __init__(self, lane):
        self.lane = lane
        self.instances = []
        self.calls = []
        self.create_error = None
        self.visible_create = True
        self.delete_answer = True
        self.after_create = lambda: None
        self.created_env = None

    def _called(self, op, credential=None, target=None):
        credential = credential or self.lane.vast_client.capture_credentials()
        self.calls.append((op, credential.api_key, target))

    def search_offers(self, **kwargs):
        self._called('search', kwargs.get('credential'))
        return [dict(OFFER), {**OFFER, 'offer_id': 78, 'machine_id': 6}]

    def create_instance(self, offer_id, *, credential, label, env, **kwargs):
        self._called('create', credential, offer_id)
        proof = self.lane._receipt()
        assert proof['pending'] and proof['instance_id'] is None
        assert proof['label'] == label and proof['fingerprint'] == credential.fingerprint
        self.created_env = dict(env)
        if self.visible_create:
            self.instances.append({'instance_id': '9001', 'label': label})
        self.after_create()
        if self.create_error:
            raise self.create_error
        return '9001'

    def list_instances(self, *, credential):
        self._called('list', credential)
        return deepcopy(self.instances)

    def get_instance(self, target, *, credential):
        self._called('get', credential, str(target))
        return next((deepcopy(p) for p in self.instances if str(p['instance_id']) == str(target)), None)

    def destroy_instance(self, target, *, credential):
        self._called('delete', credential, str(target))
        assert self.lane._receipt()['delete_pending'] is True
        if self.delete_answer is True:
            self.instances = [p for p in self.instances if str(p['instance_id']) != str(target)]
        return self.delete_answer


@pytest.fixture
def fleet(lane, monkeypatch):
    fake = Fleet(lane)
    for name in ('search_offers', 'create_instance', 'list_instances', 'get_instance', 'destroy_instance'):
        monkeypatch.setattr(lane.vast_client, name, getattr(fake, name))
    return fake


@pytest.fixture
def hub():
    removed = []
    return SimpleNamespace(delete_file=lambda **kw: removed.append(kw), removed=removed)


def drive(lane, monkeypatch, hub, result=None, *, timeout=False):
    result = {'ok': True, 'uploaded': True} if result is None else result
    reads = []

    def read(*args, **kwargs):
        reads.append(kwargs)
        return None if timeout else result

    monkeypatch.setattr(lane, '_read_result', read)
    clock = iter([0, 1, 10**9])
    lane._drive(deepcopy(PLAN), 'fixture-hub-a', _api=hub,
                _sleep=lambda _: None, _now=lambda: next(clock))
    return reads


def reserve(lane, *, pending=False, instance_id=None, delete_pending=False):
    credential = lane.vast_client.capture_credentials()
    proof = lane._reserve(credential)
    return lane._save_receipt(proof, pending=pending, instance_id=instance_id, delete_pending=delete_pending)


def test_success_uses_durable_receipt_and_unique_marker_without_persisting_credentials(lane, fleet, hub, monkeypatch):
    from lds_sdk.cloud_host.extensions import db
    from lds_sdk.cloud_host.models import SystemState
    reads = drive(lane, monkeypatch, hub)
    receipt = lane._receipt()
    assert receipt['released'] and not lane.has_unreleased_rental()
    assert lane.status()['status'] == 'done'
    assert [c[0] for c in fleet.calls] == ['search', 'create', 'list', 'delete']
    assert {c[1] for c in fleet.calls} == {'fixture-account-a'}
    marker = f'_lds_fp8_result_{receipt["job_id"]}.json'
    assert reads == [{'token': 'fixture-hub-a', 'result_file': marker}]
    assert [x['path_in_repo'] for x in hub.removed] == [marker]
    assert fleet.created_env == {'HF_TOKEN': 'fixture-hub-a'}
    assert json.loads(db.session.get(SystemState, lane._RENTAL_KEY).value)['exp'] is None
    stored = '\n'.join(r.value for r in SystemState.query.all())
    assert 'fixture-account-a' not in stored and 'fixture-hub-a' not in stored


def test_rotation_during_create_does_not_change_the_cleanup_account(lane, fleet, hub, monkeypatch):
    fleet.after_create = lambda: monkeypatch.setenv('VAST_API_KEY', 'fixture-account-b')
    drive(lane, monkeypatch, hub)
    assert {c[1] for c in fleet.calls} == {'fixture-account-a'}
    assert lane.vast_client.capture_credentials().api_key == 'fixture-account-b'


def test_uncertain_create_is_never_retried_and_blocks_another_rental(lane, fleet, hub, monkeypatch, app):
    fleet.visible_create = False
    fleet.create_error = lane.vast_client.VastCreateUncertain('timeout')
    drive(lane, monkeypatch, hub)
    before = lane._receipt()
    assert before['pending'] and not before['released']
    assert lane.has_unreleased_rental() and lane.status()['cleanup_pending']
    monkeypatch.setattr(lane, 'plan', lambda *a, **kw: deepcopy(PLAN))
    with pytest.raises(lane.CloudQuantizeError, match='previous quantization'):
        lane.start(app, 'fixture/model', _api=hub)
    assert lane._receipt() == before
    assert [c[0] for c in fleet.calls].count('create') == 1
    assert not any(c[0] == 'delete' for c in fleet.calls)


def test_uncertain_create_with_one_exact_durable_label_can_be_adopted_and_closed(lane, fleet, hub, monkeypatch):
    fleet.create_error = lane.vast_client.VastCreateUncertain('timeout')
    drive(lane, monkeypatch, hub)
    assert lane._receipt()['released']
    assert lane._receipt()['instance_id'] == '9001'
    assert [c[0] for c in fleet.calls].count('create') == 1
    assert [c for c in fleet.calls if c[0] == 'delete'] == [('delete', 'fixture-account-a', '9001')]


@pytest.mark.parametrize('inventory', ['duplicate-label', 'duplicate-id', 'foreign-label', 'foreign-id', 'absent'])
def test_ambiguous_or_foreign_inventory_never_authorizes_delete(lane, fleet, inventory):
    proof = reserve(lane, pending=inventory != 'foreign-label',
                    instance_id='9001' if inventory == 'foreign-label' else None)
    good = {'instance_id': '9001', 'label': proof['label']}
    fleet.instances = {
        'duplicate-label': [good, {**good, 'instance_id': '9002'}],
        'duplicate-id': [good, {**good, 'label': 'foreign'}],
        'foreign-label': [{**good, 'label': 'foreign'}],
        'foreign-id': [{'instance_id': '9002', 'label': 'foreign'}],
        'absent': [],
    }[inventory]
    assert lane.reconcile_orphans() == []
    assert lane._receipt() == proof
    assert not any(c[0] == 'delete' for c in fleet.calls)


def test_recovery_ignores_unrelated_unlabelled_instances(lane, fleet):
    proof = reserve(lane, instance_id='9001')
    fleet.instances = [{'instance_id': '9001', 'label': proof['label']},
                       {'instance_id': '9002', 'label': None}]
    assert lane.reconcile_orphans() == ['9001']
    assert fleet.instances == [{'instance_id': '9002', 'label': None}]


def test_restart_with_another_key_preserves_proof_and_never_contacts_provider(lane, fleet, monkeypatch):
    proof = reserve(lane, instance_id='9001')
    fleet.instances = [{'instance_id': '9001', 'label': proof['label']}]
    lane._credentials.clear()
    monkeypatch.setenv('VAST_API_KEY', 'fixture-account-b')
    assert lane.reconcile_orphans() == []
    assert fleet.calls == [] and lane._receipt() == proof
    monkeypatch.setenv('VAST_API_KEY', 'fixture-account-a')
    assert lane.reconcile_orphans() == ['9001']
    assert lane._receipt()['released']


def test_delete_failure_retains_intent_and_absence_only_allows_idempotent_delete_retry(lane, fleet):
    proof = reserve(lane, instance_id='9001')
    fleet.instances = [{'instance_id': '9001', 'label': proof['label']}]
    fleet.delete_answer = False
    assert lane.reconcile_orphans() == []
    assert lane._receipt()['delete_pending'] and not lane._receipt()['released']
    fleet.instances = []  # DELETE may have succeeded while its response was lost.
    fleet.delete_answer = True
    assert lane.reconcile_orphans() == ['9001']
    assert lane._receipt()['released']
    assert [c[0] for c in fleet.calls] == ['list', 'delete', 'list', 'get', 'delete']


def test_absent_known_instance_without_delete_intent_does_not_acquit(lane, fleet):
    proof = reserve(lane, instance_id='9001')
    assert lane.reconcile_orphans() == []
    assert lane._receipt() == proof
    assert [c[0] for c in fleet.calls] == ['list', 'get']


@pytest.mark.parametrize('boundary', ['before-create', 'after-create', 'before-delete'])
def test_failed_receipt_write_prevents_unproven_mutations_and_can_recover(lane, fleet, hub, monkeypatch, boundary):
    save = lane._save_receipt
    failed = []

    def write(proof, **updates):
        matches = {'before-create': updates.get('pending') is True,
                   'after-create': updates.get('instance_id') == '9001',
                   'before-delete': updates.get('delete_pending') is True}[boundary]
        if matches and not failed:
            failed.append(True)
            raise OSError('fixture persistence failure')
        return save(proof, **updates)

    monkeypatch.setattr(lane, '_save_receipt', write)
    drive(lane, monkeypatch, hub)
    assert failed
    operations = [c[0] for c in fleet.calls]
    if boundary == 'before-create':
        assert operations == ['search'] and lane._receipt()['released']
    elif boundary == 'after-create':
        assert operations.count('create') == 1
        assert operations[-1] == 'delete' and lane._receipt()['released']
    else:
        assert 'delete' not in operations and not lane._receipt()['released']
        assert lane.reconcile_orphans() == ['9001']


def test_failed_commit_discards_unsaved_receipt_from_session(lane, monkeypatch):
    from lds_sdk.cloud_host.extensions import db
    from lds_sdk.cloud_host.models import SystemState
    proof = reserve(lane)
    commit = db.session.commit
    monkeypatch.setattr(db.session, 'commit', lambda: (_ for _ in ()).throw(OSError('fixture commit failure')))
    with pytest.raises(OSError):
        lane._save_receipt(proof, pending=True)
    monkeypatch.setattr(db.session, 'commit', commit)
    db.session.expire_all()
    assert lane._receipt() == proof
    assert not json.loads(db.session.get(SystemState, lane._RENTAL_KEY).value)['v']['pending']


def test_deferred_worker_holds_lease_and_uses_keys_captured_before_rotation(lane, fleet, hub, monkeypatch, app):
    workers = []
    monkeypatch.setattr(lane, 'plan', lambda *a, **kw: deepcopy(PLAN))
    monkeypatch.setattr(lane, '_read_result', lambda *a, **kw: {'ok': True, 'uploaded': True})
    real_drive = lane._drive
    monkeypatch.setattr(lane, '_drive', lambda *a, **kw: real_drive(*a, **kw, _sleep=lambda _: None))
    monkeypatch.setattr(lane, 'threading', SimpleNamespace(Thread=lambda **kw: SimpleNamespace(
        start=lambda: workers.append(kw['target']))))
    planned = lane.start(app, 'fixture/model', _api=hub)
    assert len(workers) == 1
    try:
        assert lane.reconcile_orphans() == [] and fleet.calls == []
        with pytest.raises(lane.CloudQuantizeError, match='already holds'):
            lane.start(app, 'fixture/model', _api=hub)
        monkeypatch.setenv('VAST_API_KEY', 'fixture-account-b')
        monkeypatch.setenv('HF_CLOUD_TOKEN', 'fixture-hub-b')
    finally:
        workers[0]()  # execute synchronously; never start a real thread
    assert {c[1] for c in fleet.calls} == {'fixture-account-a'}
    assert fleet.created_env == {'HF_TOKEN': 'fixture-hub-a'}
    assert hub.removed[0]['path_in_repo'] == planned['result_file']


def test_failed_thread_start_releases_own_reservation_and_does_not_rent(lane, fleet, hub, monkeypatch, app):
    monkeypatch.setattr(lane, 'plan', lambda *a, **kw: deepcopy(PLAN))
    monkeypatch.setattr(lane, 'threading', SimpleNamespace(Thread=lambda **kw: SimpleNamespace(
        start=lambda: (_ for _ in ()).throw(RuntimeError('fixture thread unavailable')))))
    with pytest.raises(RuntimeError, match='fixture thread unavailable'):
        lane.start(app, 'fixture/model', _api=hub)
    assert lane._receipt()['released'] and not lane.has_unreleased_rental()
    assert lane.status()['status'] == 'error' and fleet.calls == []
    lease = lane._lease()
    lease.release()


@pytest.mark.parametrize('timeout', [True, False])
def test_failure_and_timeout_keep_cleanup_problem_visible(lane, fleet, hub, monkeypatch, timeout, caplog):
    fleet.delete_answer = False
    drive(lane, monkeypatch, hub, {'ok': False, 'error': 'fixture-account-a fixture-hub-a'}, timeout=timeout)
    assert lane.has_unreleased_rental() and lane.status()['cleanup_pending']
    assert 'may still be billing' in lane.status()['error']
    assert 'fixture-account-a' not in caplog.text and 'fixture-hub-a' not in caplog.text
    assert [c[0] for c in fleet.calls][-1] == 'delete'


def test_hub_marker_download_uses_explicit_job_file_and_captured_token(lane, monkeypatch, tmp_path):
    path = tmp_path / 'result.json'
    path.write_text('{"ok": true, "uploaded": true}', encoding='utf-8')
    calls = []
    monkeypatch.setattr('huggingface_hub.hf_hub_download', lambda **kw: calls.append(kw) or str(path))
    assert lane._read_result(None, 'fixture/model', token='fixture-hub-a', result_file='job.json')['ok']
    assert calls == [{'repo_id': 'fixture/model', 'filename': 'job.json', 'repo_type': 'model', 'token': 'fixture-hub-a'}]


def test_plan_transport_error_never_returns_credentials_to_the_client(lane):
    def failed(**kw):
        raise RuntimeError('request failed fixture-hub-a fixture-account-a')
    with pytest.raises(lane.CloudQuantizeError) as error:
        lane.plan('fixture/model', token='fixture-hub-a', _api=SimpleNamespace(repo_info=failed), _offers=[OFFER])
    assert 'fixture-hub-a' not in str(error.value)
    assert 'fixture-account-a' not in str(error.value)
