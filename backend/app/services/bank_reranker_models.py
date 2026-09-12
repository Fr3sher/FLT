"""Pinned local assets for optional Qwen image-search refinement."""
from pathlib import Path
import sys

from .. import config as cfg

MODEL_ID = 'Qwen/Qwen3-VL-Reranker-2B'
REVISION = '4bd860ac4f15ad1897a214615cccc700f8f71818'
MODEL_KEY = 'qwen3-vl-reranker-2b@4bd860ac'
DOWNLOAD_MB = 4260
WEIGHT_BYTES = 4255140312
FILES = ('config.json', 'model.safetensors', 'preprocessor_config.json',
         'tokenizer.json', 'tokenizer_config.json', 'chat_template.jinja',
         'vocab.json', 'merges.txt', 'video_preprocessor_config.json',
         'added_tokens.json', 'special_tokens_map.json', 'generation_config.json')
TOP_N = 20
MAX_PIXELS = 524288
MAX_LENGTH = 4096


def inference_python():
    return str(cfg.get('bank_reranker.python') or '').strip() or sys.executable


def models_root():
    configured = str(cfg.get('bank_reranker.models_root') or '').strip()
    return Path(configured) if configured else cfg.data_dir() / 'models' / 'bank_reranker'


def snapshot_dir(root=None):
    return (Path(root) if root else models_root()) / (
        'models--' + MODEL_ID.replace('/', '--')) / 'snapshots' / REVISION


def weights_present(root=None):
    snap = snapshot_dir(root)
    try:
        return (all((snap / name).is_file() and (snap / name).stat().st_size > 0
                    for name in FILES)
                and (snap / 'model.safetensors').stat().st_size == WEIGHT_BYTES)
    except OSError:
        return False


def device():
    value = str(cfg.get('bank_reranker.device') or 'cpu').strip().lower()
    if value not in ('cpu', 'cuda'):
        raise ValueError('Qwen refinement device must be cpu or cuda')
    return value
