"""Quantizing a model you already have: the refusals, and the verified output.

The interesting half is what it REFUSES — the same header guard as the training
base check, used in reverse — and the fact that it never touches the source.
"""
import json
import struct

import pytest

from app.services import fp8_quantize as fq

torch = pytest.importorskip('torch', reason='fp8 quantization needs torch')
safetensors_torch = pytest.importorskip('safetensors.torch')


def _model(tmp_path, name='BigModel.safetensors'):
    torch.manual_seed(3)
    path = tmp_path / name
    safetensors_torch.save_file({
        'blocks.0.attn.wq.weight': torch.randn(1024, 1024).bfloat16(),
        'blocks.0.mlp.up.weight': torch.randn(1024, 2048).bfloat16(),
        'blocks.0.prenorm.scale': torch.ones(1024),
    }, str(path))
    return path


def test_plan_describes_the_output_without_writing_anything(tmp_path):
    src = _model(tmp_path)
    plan = fq.plan(str(src))
    assert plan['destination_name'] == 'BigModel_fp8.safetensors'
    assert plan['destination_exists'] is False
    assert plan['quantized_tensors'] == 2 and plan['kept_tensors'] == 1
    assert 0 < plan['estimated_bytes'] < plan['source_bytes']
    assert list(tmp_path.iterdir()) == [src]


def test_quantizing_writes_a_verified_twin_and_never_touches_the_source(tmp_path):
    src = _model(tmp_path)
    before = src.read_bytes()
    result = fq.quantize(str(src))
    assert result['verified'] is True, result.get('verify_error')
    assert result['verify_error'] is None
    assert result['scaled_tensors'] == 2
    out = tmp_path / 'BigModel_fp8.safetensors'
    assert out.is_file() and out.stat().st_size == result['bytes_after']
    assert out.stat().st_size < src.stat().st_size
    assert src.read_bytes() == before, 'the source must never be rewritten'
    loaded = safetensors_torch.load_file(str(out))
    assert loaded['scaled_fp8'].dtype is torch.float8_e4m3fn
    assert loaded['blocks.0.attn.wq.weight'].dtype is torch.float8_e4m3fn
    assert loaded['blocks.0.attn.wq.scale_weight'].dtype is torch.float32
    # The provenance stamp says where it came from, which is the one thing a
    # bare `*_fp8.safetensors` name cannot survive being renamed.
    from app.services import fp8_export
    assert fp8_export.read_header(out)['__metadata__']['lds_quantized_from'] \
        == 'BigModel.safetensors'


def test_an_already_quantized_file_is_refused_rather_than_quantized_twice(tmp_path):
    src = _model(tmp_path)
    fq.quantize(str(src))
    out = tmp_path / 'BigModel_fp8.safetensors'
    with pytest.raises(fq.QuantizeError, match='already a quantized export'):
        fq.plan(str(out))
    described = fq.describe(str(out))
    assert described['ok'] is False and 'already' in described['error']


def test_a_lora_or_adapter_is_refused_with_a_reason(tmp_path):
    path = tmp_path / 'my_lora.safetensors'
    safetensors_torch.save_file(
        {'lora_unet_blocks_0.lora_down.weight': torch.randn(32, 1024).bfloat16()},
        str(path))
    with pytest.raises(fq.QuantizeError, match='not a full model'):
        fq.plan(str(path))


@pytest.mark.parametrize('value, message', [
    ('', 'choose a'),
    ('relative/path.safetensors', 'full path'),
])
def test_obvious_bad_input_is_refused_before_anything_is_opened(value, message):
    with pytest.raises(fq.QuantizeError, match=message):
        fq.plan(value)


def test_a_missing_file_and_a_wrong_extension_are_named_precisely(tmp_path):
    with pytest.raises(fq.QuantizeError, match='no file at'):
        fq.plan(str(tmp_path / 'nope.safetensors'))
    gguf = tmp_path / 'model.gguf'
    gguf.write_bytes(b'GGUF' + b'\0' * 64)
    with pytest.raises(fq.QuantizeError, match='already quantized'):
        fq.plan(str(gguf))


def test_an_html_gate_page_is_refused_as_a_broken_model(tmp_path):
    path = tmp_path / 'gated.safetensors'
    path.write_bytes(b'<!doctype html><html>accept the licence</html>')
    with pytest.raises(fq.QuantizeError):
        fq.plan(str(path))


def test_an_existing_output_is_never_silently_overwritten(tmp_path):
    src = _model(tmp_path)
    fq.quantize(str(src))
    with pytest.raises(fq.QuantizeError, match='already exists'):
        fq.quantize(str(src))
    # ...unless the caller says so explicitly.
    assert fq.quantize(str(src), overwrite=True)['verified'] is True


def test_progress_is_reported_per_tensor(tmp_path):
    src = _model(tmp_path)
    seen = []
    fq.quantize(str(src), progress=lambda done, total: seen.append((done, total)))
    assert seen[0] == (1, 3) and seen[-1] == (3, 3)


def test_verify_rejects_a_file_that_is_not_a_scaled_fp8_export(tmp_path):
    src = _model(tmp_path)
    report = fq.verify(str(src))
    assert report['verified'] is False
    assert 'marker' in report['verify_error']


def test_a_free_space_refusal_happens_before_any_read(tmp_path, monkeypatch):
    src = _model(tmp_path)
    monkeypatch.setattr(fq, '_free_gb', lambda _p: 1.0)
    with pytest.raises(fq.QuantizeError, match='not enough disk space'):
        fq.quantize(str(src))
    assert not (tmp_path / 'BigModel_fp8.safetensors').exists()
    assert not (tmp_path / 'BigModel_fp8.safetensors.part').exists()
