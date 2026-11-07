"""Header-only local plan/status contract; no torch worker or model generation."""
from pathlib import Path
import json
import struct
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT / 'bundled/model_tools')]
from lds_model_tools import fp8_quantize, runtime


def test_missing_torch_points_to_the_owning_plugin_settings(monkeypatch):
    monkeypatch.setattr(runtime, 'candidates', lambda: ['existing-python'])
    monkeypatch.setattr(runtime, 'explicit_python', lambda: 'existing-python')
    monkeypatch.setattr(runtime, 'probe', lambda _python: {'torch': False})
    result = fp8_quantize.interpreter()
    assert result['ready'] is False
    assert 'Plugins > Model tools > Settings > Advanced Python override' in result['reason']
    assert 'Keep the LDS application environment unchanged' in result['reason']
    assert 'Bank' not in result['reason'] and 'config.json' not in result['reason']


def test_local_plan_and_persisted_status_keep_the_real_output_folder(tmp_path, monkeypatch):
    source = tmp_path / 'SYNTHETIC-PARSER-only.safetensors'
    header = json.dumps({'__metadata__': {'fixture': 'synthetic parser test, not trained'},
                         'blocks.0.attn.wq.weight': {'dtype': 'F16', 'shape': [1024, 1024],
                                                    'data_offsets': [0, 2097152]}}).encode()
    source.write_bytes(struct.pack('<Q', len(header)) + header + bytes(2097152))
    before = source.read_bytes()
    monkeypatch.setattr(fp8_quantize, 'interpreter', lambda: {'ready': True, 'python': 'test-only-no-worker'})
    monkeypatch.setattr(fp8_quantize, '_free_gb', lambda _: 10)
    plan = fp8_quantize.plan(str(source))
    assert plan['destination_dir'] == str(tmp_path)
    assert plan['required_bytes'] == plan['estimated_bytes'] + fp8_quantize.WRITE_HEADROOM_BYTES
    assert plan['free_bytes'] == 10_000_000_000
    saved = []
    monkeypatch.setattr(fp8_quantize.queue_manager, 'set', lambda _key, value, **_kw: saved.append(value))
    fp8_quantize._set('running', plan, done=0, total=1)
    assert saved[0]['destination_dir'] == str(tmp_path)
    assert saved[0]['destination_name'] == plan['destination_name']
    assert source.read_bytes() == before
    assert list(tmp_path.iterdir()) == [source], 'a header plan must not create a converted model'
