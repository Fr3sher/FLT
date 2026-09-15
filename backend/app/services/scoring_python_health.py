"""Explicit, bounded calculation check; never called by detection or Setup.

No models are downloaded and no environment is changed. The child uses the
same isolation as Bank workers, so DLL/import failures are not hidden by a
different launch environment. A successful synthetic check is not a full
CLIP/SigLIP model validation.
"""
from contextlib import nullcontext
import json
import subprocess

from ..gpu_window import GpuBusyError, gpu_exclusive_vision_window
from ..utils.redact import redact_tokens, redact_user_paths
from . import infer_env, scoring_python

CHECK_TIMEOUT = 90

# Device is passed explicitly: a CPU check cannot discover and use a GPU after
# admission. CUDA checks hold the same exclusive window as the real Bank pass.
_CHECK_CODE = r'''
import json, sys
result = {'status': 'failed', 'device': sys.argv[1], 'torch_version': None,
          'cudnn_version': None, 'checks': [], 'skipped': []}
try:
    import torch
    import torch.nn.functional as F
    torch.set_num_threads(1)
    result['torch_version'] = str(torch.__version__)
    result['cudnn_version'] = torch.backends.cudnn.version()
    device = sys.argv[1]
    dtype = torch.float16 if device == 'cuda' else torch.float32
    with torch.inference_mode():
        x = torch.ones((1, 3, 32, 32), device=device, dtype=dtype)
        weight = torch.ones((8, 3, 3, 3), device=device, dtype=dtype)
        y = F.conv2d(x, weight)
        if not bool(torch.isfinite(y).all()):
            raise RuntimeError('Convolution returned non-finite values')
        if device == 'cuda':
            torch.cuda.synchronize()
        result['checks'].append('convolution')
        q = torch.ones((1, 4, 64, 64), device=device, dtype=dtype)
        y = F.scaled_dot_product_attention(q, q, q)
        if not bool(torch.isfinite(y).all()):
            raise RuntimeError('Attention returned non-finite values')
        if device == 'cuda':
            torch.cuda.synchronize()
        result['checks'].append('attention')
        if device == 'cuda':
            try:
                from torch.nn.attention import SDPBackend, sdpa_kernel
                with sdpa_kernel([SDPBackend.CUDNN_ATTENTION]):
                    y = F.scaled_dot_product_attention(q, q, q)
                    torch.cuda.synchronize()
                    if not bool(torch.isfinite(y).all()):
                        raise RuntimeError('cuDNN attention returned non-finite values')
                result['checks'].append('cudnn_attention')
            except (ImportError, AttributeError):
                result['skipped'].append('cuDNN attention is unavailable in this Torch build')
            except RuntimeError as exc:
                # An unsupported kernel is inconclusive, not a broken install.
                # DLL/version mismatches never take this branch.
                if ('No viable backend' in str(exc) or 'No available kernel' in str(exc)):
                    result['skipped'].append('cuDNN attention is unsupported for this check')
                else:
                    raise
    result['status'] = 'passed'
    result['detail'] = 'Small convolution and attention calculations passed. Model inference was not tested.'
    if result['skipped']:
        result['detail'] += ' ' + '; '.join(result['skipped']) + '.'
except Exception as exc:
    result['detail'] = str(exc)
print(json.dumps(result))
'''


def _safe_detail(value):
    return redact_user_paths(redact_tokens(str(value or 'Calculation check failed.')))[:700]


def check(path='', profile=None):
    """Read-only explicit POST action, with fail-closed GPU admission."""
    prof = scoring_python.get_profile(profile)
    target = (path or '').strip()
    if not target:
        target = (scoring_python.cfg.get(prof.config_key) or '').strip()
        target = target or scoring_python.default_python(prof)
    result = {'status': 'unavailable', 'detail': '', 'device': None,
              'torch_version': None, 'cudnn_version': None, 'checks': [],
              'profile': prof.key, 'path': target}
    facts = scoring_python.probe(target, force=True)
    verdict = scoring_python.describe(target, facts, prof)
    if not verdict['usable']:
        result['detail'] = _safe_detail(verdict['detail'])
        return result
    device = 'cuda' if verdict['cuda'] else 'cpu'
    result.update(device=device, torch_version=verdict['torch_version'])
    try:
        window = gpu_exclusive_vision_window(flag_ttl=CHECK_TIMEOUT + 30) if device == 'cuda' else nullcontext()
        with window:
            proc = subprocess.run(
                infer_env.worker_argv(target, '-c', _CHECK_CODE, device),
                env=infer_env.worker_env(target), capture_output=True,
                text=True, encoding='utf-8', errors='replace', timeout=CHECK_TIMEOUT,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except GpuBusyError:
        result.update(status='busy', detail='The GPU is in use or could not be reserved safely. Retry after the current work finishes.')
        return result
    except subprocess.TimeoutExpired:
        result.update(status='failed', detail='The calculation check timed out. The check process was stopped; no setting was changed.')
        return result
    except OSError:
        result.update(status='unavailable', detail='The selected Python could not start the calculation check.')
        return result
    try:
        payload = json.loads(proc.stdout.strip().splitlines()[-1])
        if not isinstance(payload, dict) or payload.get('status') not in ('passed', 'failed'):
            raise ValueError('invalid result')
    except (ValueError, IndexError):
        result.update(status='failed', detail='The calculation process exited without a usable result. Check this Python installation.')
        return result
    result['status'] = payload['status'] if proc.returncode == 0 else 'failed'
    result['detail'] = _safe_detail(payload.get('detail'))
    result['checks'] = [name for name in ('convolution', 'attention', 'cudnn_attention')
                        if name in (payload.get('checks') or [])]
    version = payload.get('cudnn_version')
    result['cudnn_version'] = version if isinstance(version, int) else None
    if result['status'] == 'passed' and not {'convolution', 'attention'}.issubset(result['checks']):
        result.update(status='failed', detail='The calculation check did not complete both operations.')
    return result
