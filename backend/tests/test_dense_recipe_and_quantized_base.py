"""The unlocked half of the dense recipe, the quantized-base guard, and the
payload the pod-side fp8 export would actually receive.

Three rules are asserted here that no single-file test can catch on its own:

* an unlocked value must reach BOTH the emitted ai-toolkit job config and the
  Hugging Face storage forecast — a forecast that disagrees with the job config
  is exactly what cost run #146 its last 250 steps;
* the quantized-base refusal must fire on the file HEADER, never on the body;
* the fp8 export never turns "the twin failed" into "the run failed".
"""
import json
import struct

import pytest

from app.services import dense_fp8_delivery as dfd
from app.services import hf_storage
from app.services import lora_training as lt
from app.services import model_integrity as mi


class FakeDataset:
    """Minimal duck-typed dataset — the training service reads attributes, not
    an ORM row, which is what makes the recipe testable without a database."""

    def __init__(self, **settings):
        self.id = 1
        self.train_type = 'krea'
        self.train_variant = 'base'
        self.train_base_model = None
        self.train_vae_path = None
        self.train_te_path = None
        self.training_mode = 'full_transformer'
        self.trigger_word = 'subject1'
        self.kind = 'character'
        self.train_settings = json.dumps(settings) if settings else None
        self.train_slider = None


def _job(ds, steps=3000):
    # An explicit training_folder keeps this a pure recipe test: build_job_config
    # otherwise resolves the local ai-toolkit output dir, which a cloud-only
    # install (and this suite) does not have.
    return lt.build_job_config(ds, '/tmp/data', steps=steps,
                               training_folder='/o')['config']['process'][0]


@pytest.fixture()
def one_dataset(monkeypatch):
    """update_train_settings validates against a real row; the validation rules
    are what this file is about, so the row is a stub."""
    ds = FakeDataset()
    monkeypatch.setattr(lt.fds, 'get_dataset', lambda *_a, **_k: ds)
    return ds


# --- volet 2: the four unlocked values ------------------------------------------

def test_dense_defaults_are_unchanged_when_nothing_is_set():
    process = _job(FakeDataset())
    assert process['train']['lr'] == lt.FULL_TRANSFORMER_LR == 1e-6
    assert process['datasets'][0]['resolution'] == [1024]
    assert process['save']['save_every'] == 250
    assert process['save']['max_step_saves_to_keep'] == 1
    assert process['sample']['guidance_scale'] == 4
    assert process['sample']['sample_steps'] == 25


def test_each_unlocked_value_reaches_the_emitted_job_config():
    ds = FakeDataset(dense_lr=2e-6, dense_resolution=768,
                     dense_save_every=500, dense_max_step_saves=3,
                     sample_prompts=['{trigger} on a red couch'])
    process = _job(ds)
    assert process['train']['lr'] == 2e-6
    assert process['datasets'][0]['resolution'] == [768]
    assert process['save']['save_every'] == 500
    assert process['save']['max_step_saves_to_keep'] == 3
    # Previews follow the checkpoint cadence: a probe sheet that does not line
    # up with a save cannot be used to choose which save to keep.
    assert process['sample']['sample_every'] == 500
    assert process['sample']['prompts'] == ['subject1 on a red couch']


def test_the_locked_geometry_is_not_reachable_through_settings():
    """batch/optimizer/dtype/gradient checkpointing are what make 12B fit in
    80 GB. A patch naming them must not move the dense recipe."""
    ds = FakeDataset(optimizer='adamw8bit', grad_accum=4, save_dtype='fp16',
                     rank=64, network_type='lokr')
    process = _job(ds)
    assert process['train']['optimizer'] == 'adafactor'
    assert process['train']['batch_size'] == 1
    assert process['train']['gradient_accumulation'] == 1
    assert process['train']['dtype'] == 'bf16'
    assert process['train']['gradient_checkpointing'] is True
    assert process['save']['dtype'] == 'bf16'
    assert 'network' not in process


@pytest.mark.parametrize('patch, message', [
    ({'dense_lr': 1e-4}, 'dense_lr'),
    ({'dense_lr': 1e-9}, 'dense_lr'),
    ({'dense_resolution': 512}, 'dense_resolution'),
    ({'dense_save_every': 10}, 'dense_save_every'),
    ({'dense_max_step_saves': 9}, 'dense_max_step_saves'),
    ({'dense_fp8_export': 'yes'}, 'dense_fp8_export'),
])
def test_out_of_bounds_values_are_refused(patch, message, one_dataset):
    settings = {}
    with pytest.raises(ValueError, match=message):
        lt.update_train_settings(1, 1, patch, _settings=settings)
    assert settings == {}


def test_auto_clears_a_stored_value_back_to_the_default(one_dataset):
    settings = {'dense_lr': 3e-6, 'dense_max_step_saves': 3}
    lt.update_train_settings(1, 1, {'dense_lr': 'auto',
                                    'dense_max_step_saves': None},
                             _settings=settings)
    assert settings == {}
    assert lt._dense_lr(FakeDataset()) == lt.FULL_TRANSFORMER_LR


def test_storage_forecast_and_job_config_read_the_same_keep_count():
    ds = FakeDataset(dense_max_step_saves=3)
    assert lt.dense_max_step_saves_for(ds) == 3
    assert _job(ds)['save']['max_step_saves_to_keep'] == 3
    plan = lt.dense_storage_plan(ds)
    assert plan['keeps'] == 3
    # 3 x ~26 GB + the fp8 twin — the number the panel must state BEFORE launch.
    assert plan['peak_bytes'] > 3 * 25 * 1000 ** 3
    assert plan['fp8_bytes'] > 0


def test_forecast_counts_the_fp8_twin_even_when_the_master_is_dropped():
    """The master is pushed by the trainer, the twin is uploaded, and only then
    is the master deleted: the PEAK always contains both."""
    usage = {'ok': True, 'used_bytes': 0, 'repos': [], 'namespace': 'ns'}
    without = hf_storage.dense_storage_forecast('ns', 't', keeps=1, _usage=usage)
    with_fp8 = hf_storage.dense_storage_forecast('ns', 't', keeps=1, _usage=usage,
                                                 fp8_export=True)
    assert with_fp8['needed_bytes'] > without['needed_bytes']
    assert with_fp8['fp8_bytes'] > 0
    assert without['fp8_bytes'] == 0


def test_refusal_message_names_the_fp8_export_when_it_is_part_of_the_need():
    usage = {'ok': True, 'used_bytes': 99 * hf_storage.GB, 'namespace': 'ns',
             'repos': [{'name': 'big', 'private': True,
                        'used_bytes': 99 * hf_storage.GB}]}
    forecast = hf_storage.dense_storage_forecast('ns', 't', keeps=2, _usage=usage,
                                                 fp8_export=True)
    assert forecast['fits'] is False
    message = hf_storage.storage_refusal_message(forecast)
    assert 'fp8 export' in message
    assert '× 2 kept' in message


def test_inference_hint_is_the_recipe_and_not_a_second_copy_of_it():
    hint = lt.dense_inference_hint()
    process = _job(FakeDataset())
    assert hint['guidance_scale'] == process['sample']['guidance_scale']
    assert hint['steps'] == process['sample']['sample_steps']
    assert 'RAW' in hint['note'] and 'blurry' in hint['note']


def test_the_test_studio_prefills_raw_settings_for_a_full_model_checkpoint():
    from app.services import lora_test_studio as studio
    assert studio.krea_build_of('Krea_full_subject1_000002500_fp8.safetensors') == 'raw'
    assert studio.krea_build_of('krea2_raw_bf16.safetensors') == 'raw'
    assert studio.krea_build_of('BigLove_Krea_Turbo.safetensors') == 'turbo'
    # Whole-word matching, like zimage_build_of: an unrecognised name keeps
    # today's distilled defaults rather than flipping everyone to slow+guided.
    assert studio.krea_build_of('BigLoveKreaTurbo.safetensors') == 'unknown'
    assert studio.krea_build_of('someones_finetune.safetensors') == 'unknown'
    raw = studio.krea_model_defaults('Krea_full_x_000002500_fp8.safetensors')
    assert raw == {'cfg': 4.0, 'steps': 25}
    # Turbo and the official base keep today's distilled defaults exactly.
    assert studio.krea_model_defaults('') == {'cfg': studio.DEFAULT_CFG,
                                              'steps': studio.DEFAULT_STEPS}
    # The recommended value has to be selectable in the picker at all.
    assert 25 in studio.STEPS_CHOICES and 4.0 in studio.CFG_CHOICES
    table = studio.studio_model_defaults('krea', [{'value': 'Krea_full_a_fp8.safetensors'}])
    assert table['Krea_full_a_fp8.safetensors']['steps'] == 25


# --- volet 3: the pre-quantized base guard --------------------------------------

def _write_safetensors_header(path, tensors, metadata=None):
    """A header-only fixture: the declared body is never written, which is the
    point — the guard must not need it."""
    index = {}
    offset = 0
    for name, (dtype, shape, nbytes) in tensors.items():
        index[name] = {'dtype': dtype, 'shape': list(shape),
                       'data_offsets': [offset, offset + nbytes]}
        offset += nbytes
    if metadata:
        index['__metadata__'] = metadata
    blob = json.dumps(index).encode('utf-8')
    with open(path, 'wb') as fh:
        fh.write(struct.pack('<Q', len(blob)))
        fh.write(blob)
        fh.write(b'\0' * 16)          # a token body, orders of magnitude short
    return str(path)


def _bf16_model(path):
    return _write_safetensors_header(path, {
        f'blocks.{i}.attn.wq.weight': ('BF16', [3072, 3072], 128) for i in range(20)
    })


def test_a_plain_bf16_base_is_accepted(tmp_path):
    path = _bf16_model(tmp_path / 'raw.safetensors')
    mi.clear_cache()
    report = mi.quantization_report(path)
    assert report['checked'] is True and report['quantized'] is False
    assert lt.assert_trainable_base_file(path)['quantized'] is False


def test_a_comfyui_scaled_fp8_export_is_refused(tmp_path):
    """The legacy marker alone is decisive — dtype counts never even matter."""
    path = _write_safetensors_header(tmp_path / 'q.safetensors', {
        'blocks.0.attn.wq.weight': ('F8_E4M3', [3072, 3072], 128),
        'blocks.0.attn.wq.scale_weight': ('F32', [], 4),
        'scaled_fp8': ('F8_E4M3', [2], 2),
    })
    assert mi.quantization_report(path)['quantized'] is True
    with pytest.raises(ValueError, match='inference-only quantized export'):
        lt.assert_trainable_base_file(path)


def test_a_modern_comfy_quant_export_is_refused_by_its_metadata(tmp_path):
    """The reference community file: mostly F32 scales and BF16 norms, so a
    dtype-majority rule alone would MISS it. The markers are what catch it."""
    tensors = {'blocks.0.attn.wq.weight': ('F8_E4M3', [3072, 3072], 128),
               'blocks.0.attn.wq.weight_scale': ('F32', [], 4),
               'blocks.0.attn.wq.comfy_quant': ('U8', [63], 63)}
    tensors.update({f'blocks.{i}.norm.scale': ('BF16', [3072], 8) for i in range(10)})
    path = _write_safetensors_header(
        tmp_path / 'mixed.safetensors', tensors,
        metadata={'_quantization_metadata': '{"format_version": "1.0"}'})
    report = mi.quantization_report(path)
    assert report['quantized'] is True
    assert '_quantization_metadata' in report['signals']
    with pytest.raises(ValueError, match='bf16/fp16 version'):
        lt.assert_trainable_base_file(path)


def test_a_bare_fp8_cast_is_refused_on_dtype_majority_alone(tmp_path):
    tensors = {f'blocks.{i}.attn.wq.weight': ('F8_E4M3', [3072, 3072], 128)
               for i in range(20)}
    tensors.update({f'blocks.{i}.norm.scale': ('F32', [3072], 12) for i in range(5)})
    path = _write_safetensors_header(tmp_path / 'cast.safetensors', tensors)
    report = mi.quantization_report(path)
    assert report['signals'] == ['majority_quantized_dtypes']
    with pytest.raises(ValueError):
        lt.assert_trainable_base_file(path)


def test_an_unreadable_header_is_let_through_rather_than_guessed_at(tmp_path):
    """Refusing a base nobody could inspect would be worse than the failure it
    prevents — the integrity validator owns 'this file is broken'."""
    path = tmp_path / 'gate.safetensors'
    path.write_bytes(b'<!doctype html><html>licence gate</html>')
    report = mi.quantization_report(str(path))
    assert report == {**report, 'checked': False, 'quantized': False}
    assert lt.assert_trainable_base_file(str(path))['checked'] is False


def test_the_guard_reads_the_header_only(tmp_path, monkeypatch):
    path = _bf16_model(tmp_path / 'raw.safetensors')
    reads = []
    real_open = mi._open

    class Counting:
        def __init__(self, fh):
            self._fh = fh

        def read(self, n=-1):
            reads.append(n)
            return self._fh.read(n)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self._fh.close()
            return False

    monkeypatch.setattr(mi, '_open', lambda *a, **k: Counting(real_open(*a, **k)))
    mi.clear_cache()
    mi.quantization_report(path)
    assert reads and all(n > 0 for n in reads), 'never read to EOF'


def test_selecting_a_quantized_custom_base_is_refused_at_selection(tmp_path):
    path = _write_safetensors_header(tmp_path / 'q.safetensors', {
        'blocks.0.attn.wq.weight': ('F8_E4M3', [3072, 3072], 128),
        'scaled_fp8': ('F8_E4M3', [2], 2),
    })
    ds = FakeDataset()
    ds.training_mode = 'lora'
    ds.train_type = 'krea'
    with pytest.raises(ValueError, match='inference-only quantized export'):
        lt._training_selection_candidate(ds, {'base_model': path}, None)


# --- volet 1: what the pod would actually be told -------------------------------

def test_the_pod_command_is_exactly_what_we_think_it_is():
    paths = dfd.pod_paths('/workspace/ai-toolkit/datasets')
    assert paths['script'] == '/workspace/ai-toolkit/datasets/_lds_fp8/fp8_export.py'
    command = dfd.build_command(paths, '/workspace/ai-toolkit/output',
                                'me/krea-run-12', budget_seconds=1800,
                                drop_bf16=False)
    assert command == (
        "python '/workspace/ai-toolkit/datasets/_lds_fp8/fp8_export.py' "
        "--src-dir '/workspace/ai-toolkit/output' "
        "--repo-id 'me/krea-run-12' "
        "--budget-seconds 1800 "
        "--token-file '/workspace/ai-toolkit/datasets/_lds_fp8/hf_token.txt'")
    # The token NEVER travels on the command line: it is visible in `ps` to every
    # process on the pod and stored verbatim next to the command's output.
    assert 'hf_secret' not in command and 'HF_TOKEN' not in command


def test_dropping_the_master_is_an_explicit_flag_and_never_the_default():
    paths = dfd.pod_paths('/d')
    assert '--drop-bf16' not in dfd.build_command(paths, '/o', 'r/x')
    assert '--drop-bf16' in dfd.build_command(paths, '/o', 'r/x', drop_bf16=True)


def test_a_repo_id_can_never_break_out_of_its_quoting():
    command = dfd.build_command(dfd.pod_paths('/d'), '/o', "x'; rm -rf /; '")
    assert "rm -rf" in command                      # still present, as DATA
    assert command.count("--repo-id 'x'\\''; rm -rf /; '\\'''") == 1


def test_the_shipped_script_is_the_module_the_tests_exercise():
    source = dfd.script_source()
    assert 'def export_scaled_fp8' in source
    assert 'LDS_FP8_RESULT' in source
    assert 'scale_weight' in source


def test_result_parsing_ignores_the_surrounding_pod_chatter():
    output = ('Downloading torch...\nsome warning\n'
              'LDS_FP8_RESULT {"ok": true, "uploaded": true, "path": "/o/a_fp8.safetensors", '
              '"bytes_after": 10500000000}\nbye\n')
    parsed = dfd.parse_result(output)
    assert parsed['ok'] is True and parsed['uploaded'] is True
    assert dfd.parse_result('nothing here') is None
    assert dfd.parse_result('LDS_FP8_RESULT not-json') is None


class _Remote:
    def __init__(self):
        self.uploaded = []

    def get_settings(self):
        return {'DATASETS_FOLDER': '/d', 'TRAINING_FOLDER': '/o'}

    def seed_checkpoint(self, root, dest, name, local):
        with open(local, encoding='utf-8') as fh:
            self.uploaded.append((dest, name, fh.read()))


class _Vast:
    def __init__(self, output):
        self.output = output
        self.commands = []

    def execute_command(self, instance_id, command):
        self.commands.append((instance_id, command))
        return 'https://example.invalid/result'

    def fetch_command_result(self, url):
        return self.output


def _run(tmp_path, output, keep_bf16=True):
    return dfd.run_pod_fp8_export(
        FakeDataset(), _Remote(), instance_id='42', repo_id='me/repo',
        hf_token='hf_secret', keep_bf16=keep_bf16, budget_seconds=1,
        tmp_dir=str(tmp_path), vast=_Vast(output), _sleep=lambda _s: None)


def test_a_successful_export_reports_the_file_and_ships_both_payloads(tmp_path):
    remote = _Remote()
    vast = _Vast('LDS_FP8_RESULT {"ok": true, "uploaded": true, '
                 '"path": "/o/Krea_full_a_fp8.safetensors", "bytes_after": 10000000000}')
    outcome = dfd.run_pod_fp8_export(
        FakeDataset(), remote, instance_id='42', repo_id='me/repo',
        hf_token='hf_secret', budget_seconds=1, tmp_dir=str(tmp_path),
        vast=vast, _sleep=lambda _s: None)
    assert outcome['state'] == 'done'
    assert 'Krea_full_a_fp8.safetensors' in outcome['detail']
    assert 'bf16 master was kept' in outcome['detail']
    names = {name for _dest, name, _body in remote.uploaded}
    assert names == {'fp8_export.py', 'hf_token.txt'}
    # Nothing of the token is left behind in the staging directory.
    assert not list(tmp_path.iterdir())


def test_a_failed_export_is_never_a_failed_run(tmp_path):
    for output in ('LDS_FP8_RESULT {"ok": false, "error": "out of disk"}',
                   'LDS_FP8_RESULT {"ok": true, "uploaded": false}',
                   'the command produced nothing useful'):
        outcome = _run(tmp_path, output)
        assert outcome['state'] == 'failed'
        assert 'bf16 model was delivered' in outcome['detail']


def test_no_pod_or_no_repository_is_skipped_not_failed(tmp_path):
    skipped = dfd.run_pod_fp8_export(
        FakeDataset(), _Remote(), instance_id=None, repo_id='me/repo',
        hf_token='t', tmp_dir=str(tmp_path), vast=_Vast(''))
    assert skipped['state'] == 'skipped'
