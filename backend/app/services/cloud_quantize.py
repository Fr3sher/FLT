"""Quantize a checkpoint that is ALREADY on Hugging Face, without downloading it.

THE PROBLEM
-----------
A dense run delivers a ~26 GB bf16 master into a private Hugging Face repo. To
get the ~10 GB fp8 file from it locally you first have to pull 26 GB down and
push 10 GB back — an hour of home bandwidth for a conversion that takes under a
minute of CPU. Runs delivered before the automatic pod export shipped are all in
that position, including the ones already trained.

So: rent a cheap machine for a few minutes, let IT do the round trip on a
datacentre link, and download only the 10 GB result. The user's own connection
never sees the master.

WHY THE CHEAPEST GPU, AND WHY THAT IS NOT A CONTRADICTION
---------------------------------------------------------
Quantization is an elementwise cast plus one reduction per tensor: measured at
~1.2 GB/s on an ordinary CPU, i.e. well under a minute of arithmetic for 26 GB.
The job is entirely bound by the network — 26 GB down, ~10 GB up. The GPU is
never touched. vast.ai has no CPU-only instances, so the selection asks for the
smallest card that clears the price filter and instead filters on DOWNLINK
bandwidth and disk, which are the things that actually decide the bill.

HOW THE POD IS DRIVEN, AND HOW IT IS GUARANTEED TO DIE
-------------------------------------------------------
No inbound connection to the pod is needed:

* everything it does is in its ``onstart`` script — the exporter's own source is
  embedded (base64) so THIS runs the same code the unit tests exercise;
* it reports back by uploading a tiny JSON result file to the SAME Hugging Face
  repo, which we already have a token for. We poll the Hub, not the pod.

Destruction is enforced from three sides, because a forgotten pod on a
minutes-long job is the worst possible outcome:

1. the monitor destroys the instance in a ``finally`` — success, failure or
   exception;
2. a HARD deadline (``cloud.quantize.max_minutes``, default 60) destroys it even
   if nothing was ever reported;
3. ``reconcile_orphans`` destroys any instance carrying this lane's label prefix
   that no live job claims — it runs on every status poll and at every start, so
   an app restart mid-job still reaps the machine.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import threading
import time
import uuid

from .. import config as cfg
from ..job_queue import queue_manager
from . import fp8_export, vast_client

logger = logging.getLogger(__name__)

_STATE_KEY = 'cloud_quantize'
_STATE_TTL = 6 * 3600
_lock = threading.Lock()

# Every instance this lane rents carries it. reconcile_orphans will destroy
# anything with this prefix that no live job claims — so the label is a safety
# device, not a cosmetic name.
LABEL_PREFIX = 'lds-quantize-'

# The pod reports here, in the repo it is already authenticated against.
RESULT_FILE = '_lds_fp8_result.json'

# Hard ceiling on the whole rental. A 26 GB pull + 10 GB push on a filtered host
# is minutes; an hour means something is wrong and the machine must go.
DEFAULT_MAX_MINUTES = 60
DEFAULT_POLL_SECONDS = 20
# The cast itself is CPU-bound and fast; this bounds it inside the pod so a
# pathological file cannot hold the rental open to the hard deadline.
DEFAULT_EXPORT_BUDGET_SECONDS = 1800
# Smallest card that still clears the filters — the GPU is never used (see note).
MIN_VRAM_GB = 8


class CloudQuantizeError(ValueError):
    """Refusal with a sentence for the user."""


def _cfg() -> dict:
    return ((cfg.get('cloud') or {}).get('quantize') or {})


def _int_cfg(key, default) -> int:
    try:
        return int(_cfg().get(key) or default)
    except (TypeError, ValueError):
        return default


def max_minutes() -> int:
    return max(5, _int_cfg('max_minutes', DEFAULT_MAX_MINUTES))


def status() -> dict:
    return queue_manager._get_system_state(_STATE_KEY, {}) or {}


# --- planning -------------------------------------------------------------------

def _hf_api(token):
    from .hf_publish import _make_api
    return _make_api(token)


def _weight_sibling(info, filename=None):
    """(path, size) of the dense weight file to quantize, from Hub metadata."""
    best = None
    for sibling in (getattr(info, 'siblings', None) or []):
        path = str(getattr(sibling, 'rfilename', '') or '')
        if not path.lower().endswith('.safetensors'):
            continue
        if path.endswith('_fp8.safetensors'):
            continue                    # an export, not a master
        if filename and os.path.basename(path) != os.path.basename(filename):
            continue
        size = getattr(sibling, 'size', None)
        lfs = getattr(sibling, 'lfs', None)
        if size is None and lfs is not None:
            size = getattr(lfs, 'size', None) if not isinstance(lfs, dict) else lfs.get('size')
        size = int(size) if isinstance(size, int) and not isinstance(size, bool) else 0
        if best is None or size > best[1]:
            best = (path, size)
    return best


def plan(repo_id, *, filename=None, keep_bf16=True, token=None, _api=None,
         _offers=None) -> dict:
    """What renting a machine to quantize ``repo_id`` would cost and produce.

    Every refusal is raised here, BEFORE anything is rented — including the
    Hugging Face storage one: the fp8 file adds ~10 GB to a repo that may
    already be at the account's ceiling.
    """
    repo = str(repo_id or '').strip()
    if '/' not in repo:
        raise CloudQuantizeError('give the full Hugging Face repository id (owner/name)')
    token = token or cfg.secret('HF_CLOUD_TOKEN') or cfg.secret('HF_TOKEN')
    if not token:
        raise CloudQuantizeError(
            'no Hugging Face token configured — add HF_CLOUD_TOKEN in '
            'Settings ▸ Local tools so the pod can read and write this repository')
    if not cfg.secret('VAST_API_KEY'):
        raise CloudQuantizeError('no vast.ai API key configured — add it in Settings ▸ Training')

    api = _api or _hf_api(token)
    try:
        info = api.repo_info(repo_id=repo, repo_type='model', files_metadata=True)
    except Exception as e:
        raise CloudQuantizeError(f'could not read {repo} on Hugging Face: {e}') from e
    found = _weight_sibling(info, filename)
    if not found:
        raise CloudQuantizeError(
            f'{repo} holds no full-precision .safetensors checkpoint to quantize'
            + (f' named {os.path.basename(str(filename))}' if filename else ''))
    weight_path, source_bytes = found
    if any(str(getattr(s, 'rfilename', '')) ==
           fp8_export.fp8_name_for(weight_path) for s in (info.siblings or [])):
        raise CloudQuantizeError(
            f'{fp8_export.fp8_name_for(os.path.basename(weight_path))} is already in '
            f'{repo} — delete it there first if you want to rebuild it.')

    offers = _offers if _offers is not None else _search_offers()
    offer = offers[0] if offers else None
    minutes = _estimated_minutes(source_bytes, offer)
    price = float((offer or {}).get('dph_total') or 0)
    fp8_typical = fp8_export.typical_fp8_bytes(source_bytes)

    from . import hf_storage
    forecast = hf_storage.dense_storage_forecast(
        repo.split('/')[0], token, keeps=0 if not keep_bf16 else 0,
        fp8_export=False)
    # The repo already holds the master; the only NEW bytes are the fp8 file.
    forecast['needed_bytes'] = fp8_export.estimate_fp8_bytes(source_bytes)
    if forecast.get('free_bytes') is not None:
        forecast['fits'] = forecast['needed_bytes'] <= forecast['free_bytes']
        forecast['shortfall_bytes'] = (None if forecast['fits'] else
                                       forecast['needed_bytes'] - forecast['free_bytes'])

    return {
        'repo_id': repo,
        'weight_path': weight_path,
        'weight_name': os.path.basename(weight_path),
        'source_bytes': source_bytes,
        'output_name': fp8_export.fp8_name_for(os.path.basename(weight_path)),
        'output_bytes_typical': fp8_typical,
        'keep_bf16': bool(keep_bf16),
        'offer': offer,
        'price_per_hour': price,
        'estimated_minutes': minutes,
        'estimated_cost': round(price * minutes / 60.0, 3),
        'max_minutes': max_minutes(),
        'storage': forecast,
    }


def _search_offers() -> list:
    c = cfg.get('cloud') or {}
    return vast_client.search_offers(
        min_vram_gb=MIN_VRAM_GB,
        max_dph=float(_cfg().get('max_price_per_hour')
                      or c.get('max_price_per_hour') or 0.80),
        # Downlink is the real cost driver: the whole job is 26 GB in, 10 GB out.
        min_inet_down_mbps=_int_cfg('min_inet_down_mbps',
                                    int(c.get('min_inet_down_mbps') or 200)),
        min_reliability=float(c.get('min_reliability') or 0.98),
        verified_only=bool(c.get('verified_only', True)))


def _estimated_minutes(source_bytes, offer) -> int:
    """Transfer time, plus a floor for boot and the cast.

    Honest about what is guessed: the downlink is advertised by the host and the
    UPLINK is not published at all, so the return leg is assumed to be half the
    downlink — pessimistic on purpose, since this number becomes a price.
    """
    mbps = float((offer or {}).get('inet_down') or 0) or 200.0
    down_s = (source_bytes * 8) / (mbps * 1e6) if source_bytes else 0
    up_s = (fp8_export.typical_fp8_bytes(source_bytes) * 8) / (mbps / 2 * 1e6) \
        if source_bytes else 0
    return max(6, int((down_s + up_s) / 60) + 6)   # +6 min: boot, cast, push setup


def _disk_gb_for(source_bytes) -> int:
    """The pod holds the master plus its fp8 twin plus the HF cache copy."""
    need = int((source_bytes or 0) / 1e9 * 2.6) + 20
    return max(60, need)


# --- the pod's whole life, in one script ----------------------------------------

def build_onstart(planned: dict, *, export_budget_seconds=None) -> str:
    """The onstart script. Nothing else ever talks to this machine.

    The exporter's SOURCE is embedded base64 rather than fetched: the pod has no
    access to this app, and a second copy of the algorithm pasted into a shell
    string is exactly the drift this whole feature is built to avoid.
    """
    from . import dense_fp8_delivery
    payload = base64.b64encode(
        dense_fp8_delivery.script_source().encode('utf-8')).decode('ascii')
    budget = int(export_budget_seconds
                 or _int_cfg('export_budget_seconds', DEFAULT_EXPORT_BUDGET_SECONDS))
    drop = '' if planned['keep_bf16'] else ' --drop-bf16'
    # Single-quoted everywhere; the only interpolated values are a repo id, a
    # file name resolved from the Hub, and integers.
    return '\n'.join([
        '#!/bin/bash',
        'set -o pipefail',
        'mkdir -p /workspace/lds && cd /workspace/lds',
        f"echo '{payload}' | base64 -d > fp8_export.py",
        'python -m pip install -q --upgrade "huggingface_hub>=0.30" safetensors || true',
        'python - <<\'PY\'',
        'import os',
        'from huggingface_hub import hf_hub_download',
        f'p = hf_hub_download(repo_id={planned["repo_id"]!r}, '
        f'filename={planned["weight_path"]!r}, local_dir="/workspace/lds/src", '
        'token=os.environ.get("HF_TOKEN"))',
        'open("/workspace/lds/src_path", "w").write(p)',
        'PY',
        'SRC=$(cat /workspace/lds/src_path)',
        f'python fp8_export.py --src "$SRC" --repo-id {planned["repo_id"]!r} '
        f'--budget-seconds {budget}{drop} > /workspace/lds/result.txt 2>&1',
        'python - <<\'PY\'',
        'import json, os, re',
        'from huggingface_hub import HfApi',
        'raw = open("/workspace/lds/result.txt", encoding="utf-8", errors="replace").read()',
        'm = re.search(r"LDS_FP8_RESULT\\s+(\\{.*\\})", raw)',
        'out = json.loads(m.group(1)) if m else {"ok": False, "error": raw[-800:]}',
        'open("/workspace/lds/result.json", "w").write(json.dumps(out))',
        'HfApi(token=os.environ.get("HF_TOKEN")).upload_file('
        'path_or_fileobj="/workspace/lds/result.json", '
        f'path_in_repo={RESULT_FILE!r}, repo_id={planned["repo_id"]!r}, repo_type="model")',
        'PY',
    ])


# --- running it -----------------------------------------------------------------

def start(app, repo_id, *, filename=None, keep_bf16=True, token=None,
          _api=None, _offers=None) -> dict:
    """Rent, convert, upload, destroy. Refuses before renting; never leaks."""
    token = token or cfg.secret('HF_CLOUD_TOKEN') or cfg.secret('HF_TOKEN')
    planned = plan(repo_id, filename=filename, keep_bf16=keep_bf16, token=token,
                   _api=_api, _offers=_offers)
    if not planned['offer']:
        raise CloudQuantizeError(
            'no vast.ai offer matches right now — raise the price cap in '
            'Settings ▸ Training and retry')
    reconcile_orphans()
    with _lock:
        if status().get('status') in ('provisioning', 'running'):
            raise CloudQuantizeError('a cloud quantization is already running')
        _set('provisioning', planned)

    def _run():
        with app.app_context():
            _drive(planned, token, _api=_api)

    threading.Thread(target=_run, daemon=True).start()
    return planned


def _drive(planned, token, *, _api=None, _sleep=time.sleep, _now=time.monotonic):
    label = LABEL_PREFIX + uuid.uuid4().hex[:10]
    instance_id = None
    deadline = _now() + max_minutes() * 60
    try:
        env = {'HF_TOKEN': token or ''}
        instance_id = vast_client.create_instance(
            planned['offer']['offer_id'],
            disk_gb=_disk_gb_for(planned['source_bytes']),
            label=label,
            image=(_cfg().get('image') or (cfg.get('cloud') or {}).get('image')),
            env=env,
            onstart=build_onstart(planned))
        _set('running', planned, instance_id=instance_id, label=label,
             started_at=time.time())
        api = _api or _hf_api(token)
        result = None
        while _now() < deadline:
            _sleep(_int_cfg('poll_seconds', DEFAULT_POLL_SECONDS))
            result = _read_result(api, planned['repo_id'])
            if result is not None:
                break
        if result is None:
            raise CloudQuantizeError(
                f'the machine reported nothing within {max_minutes()} minutes — '
                'it has been destroyed; nothing in your repository was changed')
        if not result.get('ok') or not result.get('uploaded'):
            raise CloudQuantizeError(str(result.get('error')
                                         or 'the quantization failed on the pod'))
        _set('done', planned, instance_id=instance_id, result=result)
    except Exception as e:
        logger.warning('cloud quantization failed (%s): %s', planned['repo_id'], e)
        _set('error', planned, instance_id=instance_id, error=str(e)[:400])
    finally:
        # THE line that matters: whatever happened above, the machine goes.
        if instance_id:
            try:
                if not vast_client.destroy_instance(instance_id):
                    logger.warning('cloud quantization: destroy of %s FAILED — '
                                   'reconcile_orphans will retry', instance_id)
            except Exception:
                logger.exception('cloud quantization: destroy of %s raised', instance_id)
        try:
            _cleanup_result(_api or _hf_api(token), planned['repo_id'])
        except Exception:
            logger.debug('could not remove the pod result marker', exc_info=True)


def _read_result(api, repo_id):
    """The pod's JSON verdict, or None while it has not been uploaded yet."""
    try:
        from huggingface_hub import hf_hub_download
        path = hf_hub_download(repo_id=repo_id, filename=RESULT_FILE,
                               repo_type='model')
    except Exception:
        return None
    try:
        with open(path, encoding='utf-8') as fh:
            parsed = json.load(fh)
    except (OSError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _cleanup_result(api, repo_id):
    api.delete_file(path_in_repo=RESULT_FILE, repo_id=repo_id, repo_type='model')


def reconcile_orphans() -> list:
    """Destroy every instance of this lane that no LIVE job claims.

    Called at every start and on every status poll, so an app restart in the
    middle of a job cannot leave a machine billing. The claimed instance of a
    job still marked running is deliberately spared.
    """
    live = status()
    claimed = str(live.get('instance_id') or '') if live.get('status') == 'running' else ''
    killed = []
    try:
        instances = vast_client.list_instances()
    except Exception:
        return killed
    for inst in instances:
        label = str(inst.get('label') or '')
        if not label.startswith(LABEL_PREFIX):
            continue
        if claimed and str(inst.get('instance_id')) == claimed:
            continue
        try:
            if vast_client.destroy_instance(inst['instance_id']):
                killed.append(inst['instance_id'])
                logger.warning('reaped orphan quantization pod %s', inst['instance_id'])
        except Exception:
            logger.exception('could not reap %s', inst.get('instance_id'))
    return killed


def _set(state, planned, **extra):
    queue_manager._set_system_state(_STATE_KEY, {
        'status': state,
        'repo_id': planned['repo_id'],
        'weight_name': planned['weight_name'],
        'output_name': planned['output_name'],
        'source_bytes': planned['source_bytes'],
        'output_bytes_typical': planned['output_bytes_typical'],
        'price_per_hour': planned['price_per_hour'],
        'estimated_cost': planned['estimated_cost'],
        'keep_bf16': planned['keep_bf16'],
        **extra,
    }, ttl_seconds=_STATE_TTL)
