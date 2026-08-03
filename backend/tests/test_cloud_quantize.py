"""Cloud quantization: the payload, the price, and the promise that the pod dies.

Nothing here rents anything or touches Hugging Face. What is asserted is the
exact onstart script the machine would receive, the refusals that happen BEFORE
a rental, and — the one that actually matters — that the instance is destroyed
on every path out, including the ones nobody plans for.
"""
import base64
import json

import pytest

from app.services import cloud_quantize as cq


class _Sibling:
    def __init__(self, rfilename, size):
        self.rfilename = rfilename
        self.size = size
        self.lfs = None


class _Info:
    def __init__(self, siblings):
        self.siblings = siblings


class _Api:
    def __init__(self, siblings):
        self._siblings = siblings
        self.deleted = []

    def repo_info(self, **_kw):
        return _Info(self._siblings)

    def delete_file(self, **kw):
        self.deleted.append(kw.get('path_in_repo'))


FAKE_TOKEN = 'hf_zzUNIQUEsecret999'
MASTER = 'Krea_full_subject1_000002500.safetensors'
BF16_BYTES = 25_600_000_000
OFFER = {'offer_id': 77, 'gpu_name': 'RTX 3060', 'dph_total': 0.09,
         'inet_down': 1000, 'machine_id': 5}


@pytest.fixture(autouse=True)
def _app_context(app):
    """system_state writes go through the DB — every path here stamps one."""
    with app.app_context():
        yield app


@pytest.fixture(autouse=True)
def _tokens(monkeypatch):
    monkeypatch.setattr(cq.cfg, 'secret',
                        lambda name, *a, **k: FAKE_TOKEN if name in
                        ('HF_CLOUD_TOKEN', 'HF_TOKEN', 'VAST_API_KEY') else None)


def _api(extra=()):
    return _Api([_Sibling(MASTER, BF16_BYTES), *extra])


def _plan(**kw):
    return cq.plan('me/krea-run-146', token=FAKE_TOKEN, _api=_api(kw.pop('extra', ())),
                   _offers=[OFFER], **kw)


# --- planning -------------------------------------------------------------------

def test_plan_prices_the_rental_and_names_both_files():
    planned = _plan()
    assert planned['weight_name'] == MASTER
    assert planned['output_name'] == 'Krea_full_subject1_000002500_fp8.safetensors'
    assert planned['source_bytes'] == BF16_BYTES
    # The user downloads ~10 GB instead of 25.6 GB — that is the whole point.
    assert 9e9 < planned['output_bytes_typical'] < 11e9
    assert planned['price_per_hour'] == 0.09
    assert planned['estimated_minutes'] >= 6
    assert 0 < planned['estimated_cost'] < 1.0, 'a minutes-long job must cost cents'
    # A hard ceiling is quoted up front, not discovered later.
    assert planned['max_minutes'] == cq.max_minutes() >= 5


def test_plan_refuses_to_rebuild_an_export_that_already_exists():
    with pytest.raises(cq.CloudQuantizeError, match='already in'):
        _plan(extra=(_Sibling('Krea_full_subject1_000002500_fp8.safetensors', 1),))


def test_plan_refuses_a_repository_with_no_master():
    with pytest.raises(cq.CloudQuantizeError, match='no full-precision'):
        cq.plan('me/empty', token=FAKE_TOKEN, _api=_Api([]), _offers=[OFFER])


def test_plan_refuses_a_malformed_repository_id():
    with pytest.raises(cq.CloudQuantizeError, match='owner/name'):
        cq.plan('not-a-repo', token=FAKE_TOKEN, _api=_api(), _offers=[OFFER])


def test_plan_ignores_an_existing_export_when_choosing_the_master():
    """An `_fp8` sibling is an export, never a quantization source."""
    api = _Api([_Sibling('Krea_a_fp8.safetensors', 10), _Sibling(MASTER, BF16_BYTES)])
    assert cq.plan('me/r', token=FAKE_TOKEN, _api=api, _offers=[OFFER])['weight_name'] == MASTER


def test_the_disk_request_holds_the_master_its_twin_and_the_cache():
    assert cq._disk_gb_for(BF16_BYTES) >= int(25.6 * 2.6) + 20
    assert cq._disk_gb_for(0) == 60          # never below a usable floor


# --- the script the machine actually receives ------------------------------------

def test_the_onstart_embeds_the_real_exporter_and_nothing_else():
    script = cq.build_onstart(_plan())
    payload = [line for line in script.splitlines() if 'base64 -d' in line][0]
    encoded = payload.split("'")[1]
    source = base64.b64decode(encoded).decode('utf-8')
    # THE invariant: one implementation. The pod runs the module the unit tests
    # exercise and that ComfyUI's own converter was fed.
    assert 'def export_scaled_fp8' in source
    assert 'scale_weight' in source
    assert 'LDS_FP8_RESULT' in source


def test_the_onstart_downloads_quantizes_uploads_and_reports_back():
    script = cq.build_onstart(_plan())
    assert 'hf_hub_download' in script
    assert "'me/krea-run-146'" in script
    assert f"filename='{MASTER}'" in script
    assert 'python fp8_export.py --src "$SRC"' in script
    assert '--budget-seconds' in script
    # It reports through the repo it is already authenticated for — no inbound
    # connection to the pod is ever needed.
    assert cq.RESULT_FILE in script
    assert 'upload_file' in script


def test_the_master_is_only_dropped_when_explicitly_asked():
    assert '--drop-bf16' not in cq.build_onstart(_plan())
    assert '--drop-bf16' in cq.build_onstart(_plan(keep_bf16=False))


def test_the_token_travels_as_an_environment_variable_never_in_the_script():
    script = cq.build_onstart(_plan())
    # The secret reaches the pod through the container ENVIRONMENT (create_instance
    # env), never through a script the host stores and echoes back.
    assert FAKE_TOKEN not in script
    assert 'os.environ.get("HF_TOKEN")' in script


# --- the rental, and its guaranteed end -----------------------------------------

class _Vast:
    def __init__(self, *, create_raises=None):
        self.created = []
        self.destroyed = []
        self.instances = []
        self.create_raises = create_raises

    def create_instance(self, offer_id, **kw):
        if self.create_raises:
            raise self.create_raises
        self.created.append((offer_id, kw))
        return '9001'

    def destroy_instance(self, instance_id):
        self.destroyed.append(str(instance_id))
        return True

    def list_instances(self):
        return self.instances


@pytest.fixture()
def vast(monkeypatch):
    fake = _Vast()
    monkeypatch.setattr(cq, 'vast_client', fake)
    return fake


def _drive(monkeypatch, vast, result, *, timeout=False):
    planned = _plan()
    api = _api()
    monkeypatch.setattr(cq, '_read_result', lambda *_a: None if timeout else result)
    clock = iter([0.0] + [i * 10.0 for i in range(1, 200)] + [10 ** 9] * 50)
    cq._drive(planned, FAKE_TOKEN, _api=api, _sleep=lambda _s: None,
              _now=lambda: next(clock))
    return api


def test_a_successful_job_reports_the_file_and_destroys_the_machine(monkeypatch, vast):
    api = _drive(monkeypatch, vast,
                 {'ok': True, 'uploaded': True, 'bytes_after': 10_100_000_000})
    state = cq.status()
    assert state['status'] == 'done'
    assert state['result']['uploaded'] is True
    assert vast.destroyed == ['9001']
    # The pod's report file does not stay behind in the user's repository.
    assert api.deleted == [cq.RESULT_FILE]
    # The rental carries this lane's label, which is what makes reaping possible.
    assert vast.created[0][1]['label'].startswith(cq.LABEL_PREFIX)
    assert vast.created[0][1]['env']['HF_TOKEN'] == FAKE_TOKEN


def test_a_failed_conversion_still_destroys_the_machine(monkeypatch, vast):
    _drive(monkeypatch, vast, {'ok': False, 'error': 'out of disk'})
    assert cq.status()['status'] == 'error'
    assert 'out of disk' in cq.status()['error']
    assert vast.destroyed == ['9001']


def test_a_pod_that_never_reports_is_destroyed_at_the_hard_deadline(monkeypatch, vast):
    _drive(monkeypatch, vast, None, timeout=True)
    state = cq.status()
    assert state['status'] == 'error'
    assert 'reported nothing' in state['error']
    assert 'nothing in your repository was changed' in state['error']
    assert vast.destroyed == ['9001']


def test_an_upload_that_never_happened_is_not_a_success(monkeypatch, vast):
    _drive(monkeypatch, vast, {'ok': True, 'uploaded': False})
    assert cq.status()['status'] == 'error'
    assert vast.destroyed == ['9001']


def test_a_rental_that_never_started_destroys_nothing_and_says_so(monkeypatch, vast):
    vast.create_raises = RuntimeError('offer taken')
    planned = _plan()
    cq._drive(planned, FAKE_TOKEN, _api=_api(), _sleep=lambda _s: None)
    assert cq.status()['status'] == 'error'
    assert vast.destroyed == []


def test_reconcile_destroys_an_orphan_but_spares_a_live_job(vast):
    vast.instances = [
        {'instance_id': '111', 'label': cq.LABEL_PREFIX + 'abc'},
        {'instance_id': '222', 'label': 'someone-elses-run'},
    ]
    assert cq.reconcile_orphans() == ['111']
    assert vast.destroyed == ['111']

    vast.destroyed.clear()
    cq.queue_manager._set_system_state(cq._STATE_KEY, {
        'status': 'running', 'instance_id': '111', 'repo_id': 'r',
        'weight_name': 'w', 'output_name': 'o', 'source_bytes': 1,
        'output_bytes_typical': 1, 'price_per_hour': 0, 'estimated_cost': 0,
        'keep_bf16': True}, ttl_seconds=60)
    assert cq.reconcile_orphans() == []
    assert vast.destroyed == []
