"""What a dead training run is allowed to claim.

Both units under test are PURE — no GPU, no ai-toolkit, no filesystem — which is
the point: nobody on this project owns a Blackwell card, so the verdict logic is
exercised with simulated probe payloads instead of hardware.

The bug that started this (wannadecryptor, Discord, RTX 5070): the panel printed
the raw tail of training.log in red, and ai-toolkit's tail on an early death is a
harmless huggingface_hub `FutureWarning`. Hours lost on a deprecation notice.
"""
from unittest.mock import patch

from app.services.training_diagnostics import (
    CU128_INDEX_URL, MAX_EXCERPT_LINES, extract_error_excerpt, gated_repo_verdict,
    torch_arch_verdict,
)

# The actual log the user was shown, trimmed. Nothing in it is an error.
FUTUREWARNING_LOG = (
    'C:\\Users\\somebody\\ai-toolkit\\venv\\Lib\\site-packages\\huggingface_hub\\constants.py:298: '
    'FutureWarning: The `HF_HUB_ENABLE_HF_TRANSFER` environment variable is deprecated. '
    'Please use `HF_XET_HIGH_PERFORMANCE` instead.\n'
    '  warnings.warn(\n'
    'Running 1 job\n'
    'Dataset: C:\\Users\\somebody\\datasets\\subject\n'
    ' - Preprocessing image dimensions\n'
    'Bucket sizes for C:\\Users\\somebody\\datasets\\subject:\n'
    '1024x1024: 42 files\n'
    'Caching latents to disk:   0%|          | 0/42 [00:00<?, ?it/s]\n'
)


# --- extract_error_excerpt ------------------------------------------------

def test_a_futurewarning_is_never_reported_as_the_cause():
    out = extract_error_excerpt(FUTUREWARNING_LOG)
    assert out['kind'] == 'none'          # -> the UI renders it neutral, not red
    assert out['headline'] == ''          # -> nothing is quoted as "the reason"
    assert 'FutureWarning' in out['text']  # still shown, as context


def test_the_excerpt_is_path_redacted_for_public_help_threads():
    out = extract_error_excerpt(FUTUREWARNING_LOG)
    assert 'somebody' not in out['text']
    assert '~\\ai-toolkit' in out['text'] or '~\\datasets' in out['text']


def test_a_traceback_wins_and_its_exception_line_is_the_headline():
    log = FUTUREWARNING_LOG + (
        'Traceback (most recent call last):\n'
        '  File "run.py", line 90, in <module>\n'
        '    main()\n'
        '  File "toolkit/train.py", line 12, in cache\n'
        '    latents = vae.encode(px)\n'
        'RuntimeError: CUDA error: no kernel image is available for execution on the device\n'
    )
    out = extract_error_excerpt(log)
    assert out['kind'] == 'traceback'
    assert out['headline'].startswith('RuntimeError: CUDA error: no kernel image')
    assert out['text'].startswith('Traceback (most recent call last):')
    # The warning noise above the traceback is dropped entirely.
    assert 'FutureWarning' not in out['text']


def test_the_last_traceback_wins_over_one_the_run_survived():
    log = ('Traceback (most recent call last):\n'
           'ValueError: first, caught\n'
           'retrying\n'
           'Traceback (most recent call last):\n'
           'OSError: second, fatal\n')
    out = extract_error_excerpt(log)
    assert out['headline'] == 'OSError: second, fatal'
    assert 'ValueError' not in out['text']


def test_an_error_line_without_a_traceback_is_quoted_with_context():
    log = ('loading model\n'
           'preparing buckets\n'
           'torch.cuda.OutOfMemoryError: CUDA out of memory. Tried to allocate 2.00 GiB\n'
           'exiting\n')
    out = extract_error_excerpt(log)
    assert out['kind'] == 'error'
    assert out['headline'].startswith('torch.cuda.OutOfMemoryError')
    assert 'preparing buckets' in out['text']   # context above kept
    assert 'exiting' in out['text']             # context below kept


def test_a_warning_line_is_skipped_even_when_it_says_error():
    log = ('some_module.py:12: UserWarning: ErrorHandler is deprecated, failed lookups ignored\n'
           'still going\n')
    out = extract_error_excerpt(log)
    assert out['kind'] == 'none' and out['headline'] == ''


def test_an_empty_log_claims_nothing():
    for empty in (None, '', '   \n\n  '):
        out = extract_error_excerpt(empty)
        assert out == {'kind': 'none', 'text': '', 'headline': ''}


def test_a_carriage_return_progress_bar_does_not_become_one_huge_line():
    log = 'Caching latents:   0%|\rCaching latents:  50%|\rCaching latents: 100%|\n'
    out = extract_error_excerpt(log)
    assert out['text'].count('\n') == 2       # three states, three lines
    assert max(len(line) for line in out['text'].split('\n')) < 60


def test_a_long_traceback_is_capped_and_says_so_instead_of_truncating_silently():
    frames = ''.join(f'  File "f{i}.py", line {i}, in fn\n' for i in range(60))
    log = 'Traceback (most recent call last):\n' + frames + 'RuntimeError: boom\n'
    out = extract_error_excerpt(log)
    lines = out['text'].split('\n')
    assert len(lines) <= MAX_EXCERPT_LINES
    assert 'more lines' in out['text'] and 'training.log' in out['text']
    assert lines[-1] == 'RuntimeError: boom'   # the exception line always survives


def test_the_cap_is_a_real_cap_even_at_absurdly_small_budgets():
    log = 'Traceback (most recent call last):\n' + ''.join(f'line {i}\n' for i in range(40))
    for budget in (1, 2, 3, 5):
        out = extract_error_excerpt(log, max_lines=budget)
        assert len(out['text'].split('\n')) <= max(budget, 3), budget


# --- torch_arch_verdict ---------------------------------------------------
# Simulated probe payloads: the verdict must never need a real card.

BLACKWELL = {'torch': '2.7.1+cu126', 'cuda': '12.6', 'capability': [12, 0],
             'device_name': 'NVIDIA GeForce RTX 5070',
             'arch_list': ['sm_50', 'sm_80', 'sm_86', 'sm_90', 'compute_90']}
ADA = {'torch': '2.7.1+cu126', 'cuda': '12.6', 'capability': [8, 9],
       'device_name': 'NVIDIA GeForce RTX 4090',
       'arch_list': ['sm_50', 'sm_80', 'sm_86', 'sm_90']}


def test_blackwell_on_a_stable_wheel_is_diagnosed_with_the_cu128_remedy():
    v = torch_arch_verdict(BLACKWELL, venv_python='C:\\Users\\somebody\\ai-toolkit\\venv\\Scripts\\python.exe')
    assert v['supported'] is False and v['blackwell'] is True
    assert v['sm'] == 'sm_120' and v['built_up_to'] == 'sm_90'
    assert 'no kernel image' in v['message'] and 'RTX 5070' in v['message']
    assert CU128_INDEX_URL in v['command'] and '--force-reinstall' in v['command']
    assert 'somebody' not in v['command']       # paste-safe like everything else


def test_a_supported_card_is_cleared_across_minor_versions():
    # No stable wheel ships sm_89; the RTX 4090 runs the sm_86 kernels. Flagging
    # it would be a false alarm on the most common training GPU there is.
    v = torch_arch_verdict(ADA)
    assert v['supported'] is True and v['blackwell'] is False
    assert v['command'] == '' and 'ships kernels for it' in v['message']


def test_an_sm90a_style_arch_entry_is_still_understood():
    v = torch_arch_verdict({**ADA, 'arch_list': ['sm_80', 'sm_90a']})
    assert v is not None and v['built_up_to'] == 'sm_90'


def test_an_unsupported_but_non_blackwell_card_invents_no_command():
    v = torch_arch_verdict({**BLACKWELL, 'capability': [11, 0]})
    assert v['supported'] is False and v['blackwell'] is False
    assert v['command'] == ''      # we have no remedy we can honestly name


def test_the_verdict_is_none_whenever_we_simply_do_not_know():
    unknowns = [
        None,                                             # no probe at all
        {},                                               # empty payload
        {'error': 'torch not importable'},                # probe said so
        {**BLACKWELL, 'capability': None},                # CUDA saw no device
        {**BLACKWELL, 'capability': [12]},                # malformed
        {**BLACKWELL, 'capability': ['a', 'b']},          # malformed
        {**BLACKWELL, 'arch_list': []},                   # nothing to compare to
        {**BLACKWELL, 'arch_list': ['compute_90']},       # PTX only, no cubin list
        'not a dict',
    ]
    for payload in unknowns:
        assert torch_arch_verdict(payload) is None, payload


def test_without_a_known_interpreter_the_command_stays_a_placeholder():
    v = torch_arch_verdict(BLACKWELL)
    assert '<ai-toolkit venv python>' in v['command']


# --- the probe gate: cost discipline --------------------------------------

def test_an_old_gpu_never_pays_for_a_torch_import(app):
    """A card below the risky generation cannot hit the trap, so `import torch`
    in a cold venv (seconds) must not run at all."""
    from app import capabilities
    with app.app_context():
        with patch.object(capabilities, 'gpu_compute_capability', return_value=(8, 9)), \
             patch.object(capabilities, '_torch_probe') as probe:
            assert capabilities.aitoolkit_torch_info() is None
        probe.assert_not_called()


def test_an_unknown_gpu_is_not_probed_and_asserts_nothing(app):
    from app import capabilities
    with app.app_context():
        with patch.object(capabilities, 'gpu_compute_capability', return_value=None), \
             patch.object(capabilities, '_torch_probe') as probe:
            assert capabilities.aitoolkit_torch_info() is None
        probe.assert_not_called()


def test_a_failed_probe_is_not_cached_as_a_fact(app, tmp_path):
    """A cold-import timeout must be retried next time, never remembered as
    'this venv has no torch'."""
    from app import capabilities
    fake_python = tmp_path / 'python.exe'
    fake_python.write_text('')
    capabilities._torch_probe_cache.clear()
    with app.app_context():
        with patch.object(capabilities, 'gpu_compute_capability', return_value=(12, 0)), \
             patch.object(capabilities.cfg, 'aitoolkit_path', return_value=fake_python), \
             patch.object(capabilities, '_torch_probe', return_value=None):
            assert capabilities.aitoolkit_torch_info() is None
        assert capabilities._torch_probe_cache == {}


def test_a_successful_probe_is_cached_so_a_relaunch_costs_nothing(app, tmp_path):
    from app import capabilities
    fake_python = tmp_path / 'python.exe'
    fake_python.write_text('')
    capabilities._torch_probe_cache.clear()
    with app.app_context():
        with patch.object(capabilities, 'gpu_compute_capability', return_value=(12, 0)), \
             patch.object(capabilities.cfg, 'aitoolkit_path', return_value=fake_python), \
             patch.object(capabilities, '_torch_probe', return_value=BLACKWELL) as probe:
            assert capabilities.aitoolkit_torch_info() == BLACKWELL
            assert capabilities.aitoolkit_torch_info() == BLACKWELL
            assert probe.call_count == 1
    capabilities._torch_probe_cache.clear()


# --- the preflight surface ------------------------------------------------
# Catching the trap BEFORE the launch is the point: the alternative is 20 minutes
# of setup for an opaque "ai-toolkit exited 1".

def _dataset(app, n_keep=20):
    from app.config import LOCAL_USER
    from app.services import face_dataset_service as svc
    from app.models import FaceDatasetImage
    ds = svc.create_dataset(LOCAL_USER, 'Arch', 'arch_trig', train_type='zimage')
    for i in range(n_keep):
        svc.db.session.add(FaceDatasetImage(
            dataset_id=ds.id, filename=f'k{i}.webp', status='keep', framing='half',
            caption=f'a nice varied caption with many words #{i}'))
    svc.db.session.commit()
    return ds


def test_the_preflight_warns_before_the_launch_is_wasted(app):
    from app.config import LOCAL_USER
    from app import capabilities
    from app.services import lora_training as lt
    with app.app_context():
        ds = _dataset(app)
        with patch.object(capabilities, 'aitoolkit_torch_info', return_value=BLACKWELL):
            r = lt.training_preflight(LOCAL_USER, ds.id)
    row = next((c for c in r['checks'] if c['id'] == 'torch_arch'), None)
    assert row is not None and row['status'] == 'warn'
    assert 'sm_120' in row['detail']
    assert len(row['detail']) < 110, 'the row sits in a list on a phone — keep it short'
    assert any('no kernel image' in w and CU128_INDEX_URL in w for w in r['warnings'])
    # A warning, never a blocker: we read a venv, we do not own the truth.
    assert not r['blockers'] and r['verdict'] != 'blocked'


def test_the_preflight_stays_silent_when_the_gpu_is_fine(app):
    from app.config import LOCAL_USER
    from app import capabilities
    from app.services import lora_training as lt
    with app.app_context():
        ds = _dataset(app)
        with patch.object(capabilities, 'aitoolkit_torch_info', return_value=ADA):
            r = lt.training_preflight(LOCAL_USER, ds.id)
    assert not any(c['id'] == 'torch_arch' for c in r['checks'])


def test_an_unknown_probe_adds_no_row_and_no_warning(app):
    from app.config import LOCAL_USER
    from app import capabilities
    from app.services import lora_training as lt
    with app.app_context():
        ds = _dataset(app)
        with patch.object(capabilities, 'aitoolkit_torch_info', return_value=None):
            r = lt.training_preflight(LOCAL_USER, ds.id)
    assert not any(c['id'] == 'torch_arch' for c in r['checks'])


def test_a_raising_probe_never_breaks_the_preflight(app):
    from app.config import LOCAL_USER
    from app import capabilities
    from app.services import lora_training as lt
    with app.app_context():
        ds = _dataset(app)
        with patch.object(capabilities, 'aitoolkit_torch_info', side_effect=OSError('boom')):
            r = lt.training_preflight(LOCAL_USER, ds.id)
    assert r['verdict'] in ('ready', 'warnings')     # the preflight still answered


# --- the one-line summary on the Runs page --------------------------------

def test_the_runs_page_summary_quotes_the_cause_not_the_last_line():
    from app.services.lora_training import local_error_message
    err = {'rc': 1, 'log_tail': FUTUREWARNING_LOG,
           'excerpt': extract_error_excerpt(FUTUREWARNING_LOG)}
    msg = local_error_message(err)
    assert msg == 'Training crashed (exit code 1). No error line in the log.'
    assert 'FutureWarning' not in msg


def test_a_legacy_payload_without_an_excerpt_is_re_analysed():
    """States live an hour: a crash recorded before this shipped must not fall
    back to the old 'last line = the cause' lie."""
    from app.services.lora_training import local_error_message
    msg = local_error_message({'rc': 1, 'log_tail': FUTUREWARNING_LOG})
    assert msg.endswith('No error line in the log.')
    msg2 = local_error_message({'rc': 1, 'log_tail': 'boom\nRuntimeError: it died\n'})
    assert msg2 == 'Training crashed (exit code 1). RuntimeError: it died'


# --- gated Hugging Face repo: 401 is NOT 403 ------------------------------
# SurpassHR (GitHub) hit this on Krea 2. huggingface_hub prints the SAME
# sentence for both statuses — "You must have access to it and be authenticated
# to access it" — and reading the sentence instead of the code produced a public
# answer telling him to request access he already had. The two are separated
# here, on the status code, with opposite remedies.

GATED_401_LOG = (
    'Running 1 job\n'
    'Traceback (most recent call last):\n'
    '  File "~/ai-toolkit/run.py", line 90, in <module>\n'
    '    main()\n'
    'huggingface_hub.errors.GatedRepoError: 401 Client Error. (Request ID: Root=1-abc)\n'
    '\n'
    'Cannot access gated repo for url '
    'https://huggingface.co/krea/Krea-2-Turbo/resolve/main/turbo.safetensors.\n'
    'Access to model krea/Krea-2-Turbo is restricted. You must have access to it and be '
    'authenticated to access it. Please log in.\n'
)

GATED_403_LOG = (
    'huggingface_hub.errors.GatedRepoError: 403 Client Error. (Request ID: Root=1-def)\n'
    'Cannot access gated repo for url '
    'https://huggingface.co/black-forest-labs/FLUX.1-dev/resolve/main/flux1-dev.safetensors.\n'
    'Access to model black-forest-labs/FLUX.1-dev is restricted and you are not in the '
    'authorized list. Visit https://huggingface.co/black-forest-labs/FLUX.1-dev to ask '
    'for access.\n'
)


def test_a_401_is_reported_as_not_authenticated_not_as_a_licence_problem():
    v = gated_repo_verdict(GATED_401_LOG)
    assert v['status'] == 401
    assert v['repo'] == 'krea/Krea-2-Turbo'
    low = v['message'].lower()
    assert 'not authenticated' in low
    assert 'settings' in low and 'api keys' in low
    # It must NOT send the user off to request access again — that was the wrong
    # answer this whole verdict exists to stop.
    assert 'accept the model licence' not in low
    assert 'ask for access' not in low


def test_a_403_is_reported_as_a_licence_not_yet_accepted():
    v = gated_repo_verdict(GATED_403_LOG)
    assert v['status'] == 403
    assert v['repo'] == 'black-forest-labs/FLUX.1-dev'
    assert v['url'] == 'https://huggingface.co/black-forest-labs/FLUX.1-dev'
    low = v['message'].lower()
    assert 'accept the model licence' in low
    assert 'another token will not help' in low


def test_a_401_with_a_token_already_saved_says_the_token_was_rejected():
    v = gated_repo_verdict(GATED_401_LOG, token_configured=True)
    assert 'rejected' in v['message'].lower()
    assert 'expired' in v['message'].lower()


def test_a_401_with_no_token_saved_says_to_paste_one():
    v = gated_repo_verdict(GATED_401_LOG, token_configured=False)
    assert 'no hugging face token is saved' in v['message'].lower()


def test_a_log_with_no_gated_refusal_gets_no_verdict():
    for log in (FUTUREWARNING_LOG, '', None, 'RuntimeError: CUDA out of memory\n',
                'huggingface_hub.errors.RepositoryNotFoundError: 404 Client Error\n'):
        assert gated_repo_verdict(log) is None, log


def test_the_verdict_never_echoes_a_token():
    """Training logs get pasted into public help threads verbatim."""
    leaky = GATED_401_LOG + 'headers: {"Authorization": "Bearer hf_abcdefghijklmnop"}\n'
    v = gated_repo_verdict(leaky)
    assert 'hf_abcdefghijklmnop' not in str(v)
    assert 'hf_abcdefghijklmnop' not in extract_error_excerpt(leaky)['text']


def test_the_crash_payload_carries_the_gated_verdict(tmp_path):
    """End of the chain: what the watcher stores is what the panel renders."""
    from app.services.lora_training import _crash_payload
    log = tmp_path / 'training.log'
    log.write_text(GATED_401_LOG, encoding='utf-8')
    payload = _crash_payload(str(log), dataset_id=1, rc=1)
    assert payload['hf_gated']['status'] == 401
    assert payload['hf_gated']['repo'] == 'krea/Krea-2-Turbo'
