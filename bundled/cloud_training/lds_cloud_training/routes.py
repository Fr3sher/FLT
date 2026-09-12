"""Training API: launch/continue/queue/stop a LoRA training run via ai-toolkit,
plus checkpoint listing/import/delete and Z-Image base-conversion prep.

No login - single local user (`cfg.LOCAL_USER`). Every route except
`/dataset/train/status` is gated on `capabilities.probe()['aitoolkit']['valid']`
(409 with a UI hint): `/train/status` must stay pollable even when
ai-toolkit isn't configured, so it degrades to `{'available': False}` instead.
"""







from flask import Blueprint, current_app, request, jsonify

from lds_sdk.cloud_host import capabilities

from lds_sdk.cloud_host import config as cfg

from lds_sdk.cloud_host.config import LOCAL_USER

from lds_cloud_training import cloud_training as ct

from lds_sdk.cloud_host.services import face_dataset_service as svc




from lds_sdk.cloud_host.services import lora_training as lt



from lds_sdk.cloud_host.routes._common import _map_error

bp = Blueprint('cloud_training', __name__)

def _require_cloud():
    """None if cloud training is configured, else the (body, status) 409 to return."""
    if not capabilities.probe().get('cloud_training'):
        return jsonify({'error': 'Cloud training is not configured',
                        'hint': 'Add your vast.ai API key in Settings'}), 409
    return None

@bp.post('/dataset/train/cloud/purge')
def dataset_train_cloud_purge():
    """Trash the working files of finished cloud runs — the exported dataset
    copy, the sample images and the logs. Checkpoints are moved into the durable
    store instead and never trashed. Also reports orphan run folders found on
    disk, which the caller can then purge explicitly."""
    return jsonify({'ok': True, **ct.purge_finished_runs()})

@bp.get('/dataset/train/cloud/orphans')
def dataset_train_cloud_orphans():
    """Run folders on disk that no run row claims — the tens of GB the cleanup
    used to answer 'already clean' about. Walks the disk, so it is its own
    endpoint and never rides the hub's poll."""
    orphans = ct.orphan_staging_dirs()
    return jsonify({'ok': True, 'orphans': orphans,
                    'total_bytes': sum(o['size_bytes'] for o in orphans)})

@bp.post('/dataset/train/cloud/purge-orphans')
def dataset_train_cloud_purge_orphans():
    """Trash the named orphan run folders (all of them when `names` is absent).
    Loose checkpoints inside them are rescued into the store first."""
    body = request.get_json(silent=True) or {}
    names = body.get('names')
    if names is not None and not isinstance(names, list):
        return jsonify({'error': 'names must be a list'}), 400
    try:
        res = ct.purge_orphan_staging_dirs(names)
    except Exception as e:
        return _map_error(e)
    return jsonify({'ok': True, **res})

@bp.get('/dataset/train/cloud/staging-sizes')
def dataset_train_cloud_staging_sizes():
    """How much disk each cloud run's staging dir still holds, so the Runs hub can
    show "8.2 GB on disk" on a card and name that weight in the per-run 🧹
    confirmation. DELIBERATELY its own endpoint (and not a field of the runs
    payload): sizing means walking thousands of files, which must not ride the
    hub's 5 s poll. Optional ?run_ids=1,2,3 narrows the walk to the shown cards."""
    raw = (request.args.get('run_ids') or '').strip()
    ids = None
    if raw:
        try:
            ids = [int(x) for x in raw.split(',') if x.strip()]
        except ValueError:
            return jsonify({'error': 'run_ids must be a comma-separated list of run ids'}), 400
    sizes = ct.staging_sizes(ids)
    return jsonify({'ok': True,
                    'sizes': {str(k): v for k, v in sizes.items()},
                    'total_bytes': sum(sizes.values())})

@bp.post('/dataset/train/cloud/purge-run')
def dataset_train_cloud_purge_run():
    """Trash the staging dir of ONE finished cloud run — targeted cleanup, so a
    45-run history no longer forces an all-or-nothing purge. Spares exactly what
    the global purge spares (active runs, kept pods) via the shared rule."""
    body = request.get_json(silent=True) or {}
    if body.get('run_id') in (None, ''):
        return jsonify({'error': 'run_id is required'}), 400
    try:
        res = ct.purge_run_staging(body['run_id'])
    except Exception as e:
        return _map_error(e)
    return jsonify({'ok': True, **res})

@bp.post('/dataset/<int:dataset_id>/train/cloud')
def dataset_train_cloud(dataset_id):
    gate = _require_cloud()
    if gate:
        return gate
    d = request.get_json(silent=True) or {}
    ds = svc.get_dataset(LOCAL_USER, dataset_id)
    if not ds:
        return jsonify({'error': 'not found'}), 404
    try:
        mode = lt.training_mode(
            ds, d.get('training_mode') if 'training_mode' in d else None)
        res = ct.launch_cloud_training(
            LOCAL_USER, dataset_id,
            # No hardcoded 'turbo' default: an absent variant now resolves to
            # the family-aware default in the service (Krea → Raw, like local).
            steps=d.get('steps'),
            base_model=d.get('base_model', ''),
            variant=d.get('variant'),
            train_type=d.get('train_type'),
            training_mode=mode,
            masked=d.get('masked'),
            allow_caption_mismatch=bool(d.get('allow_caption_mismatch')),
            allow_uncaptioned=bool(d.get('allow_uncaptioned')),
            allow_caption_quality=bool(d.get('allow_caption_quality')),
            allow_unverified_weights=bool(d.get('allow_unverified_weights')),
            allow_not_ready=bool(d.get('allow_not_ready')),
            # « Train anyway » on the HF private-storage pre-check: the ceiling
            # it compares against is an estimate, so the user always keeps the
            # last word (see hf_storage).
            allow_hf_storage=bool(d.get('allow_hf_storage')),
            # ... and the same last word about THIS machine's disk, for a full
            # model that is delivered here.
            allow_local_disk=bool(d.get('allow_local_disk')),
            allow_parallel_run=bool(d.get('allow_parallel_run')),
            gpu_name=d.get('gpu_name'))
    except Exception as e:
        return _map_error(e)
    return jsonify({'ok': True, **res})

@bp.get('/dataset/<int:dataset_id>/train/cloud/custom-base')
def dataset_train_cloud_custom_base(dataset_id):
    """Readiness of a CUSTOM base for cloud training: is it already pushed to
    the private `lds-base-<hash>` repo on the user's Hugging Face account
    (cache-hit → launch straight away), or does it need the one-time push?
    Also reports the background push job's state (poll-friendly, never 500s
    on a missing repo — that is just ready=false)."""
    gate = _require_cloud()
    if gate:
        return gate
    if not svc.get_dataset(LOCAL_USER, dataset_id):
        return jsonify({'error': 'not found'}), 404
    from lds_cloud_training import hf_base_push
    try:
        state = hf_base_push.base_push_state(
            LOCAL_USER, dataset_id,
            request.args.get('train_type'), request.args.get('variant'),
            (request.args.get('base_model') or '').strip(),
            cfg.secret('HF_TOKEN'))
    except hf_base_push.HfPublishError as e:
        return jsonify({'error': e.message, 'error_code': e.code}), 400
    except Exception as e:
        return _map_error(e)
    return jsonify({'ok': True, **state})

@bp.post('/dataset/<int:dataset_id>/train/cloud/custom-base/push')
def dataset_train_cloud_custom_base_push(dataset_id):
    """One-time background upload of the custom base to a PRIVATE repo on the
    user's Hugging Face account (private is forced server-side — no toggle).
    Multi-GB → daemon thread; the UI polls the custom-base route above. The
    confirmable CUSTOM_WEIGHTS_UNVERIFIED arch sniff answers synchronously so
    the dialog can confirm-and-retry."""
    gate = _require_cloud()
    if gate:
        return gate
    if not svc.get_dataset(LOCAL_USER, dataset_id):
        return jsonify({'error': 'not found'}), 404
    token = cfg.secret('HF_TOKEN')
    if not token:
        return jsonify({'error': 'no Hugging Face token configured — paste an '
                        'HF_TOKEN in Settings ▸ API keys'}), 400
    d = request.get_json(silent=True) or {}
    from lds_cloud_training import hf_base_push
    try:
        out = hf_base_push.start_push(
            current_app._get_current_object(), dataset_id,
            d.get('train_type'), d.get('variant'),
            (d.get('base_model') or '').strip(), token,
            allow_unverified_weights=bool(d.get('allow_unverified_weights')))
    except hf_base_push.HfPublishError as e:
        return jsonify({'error': e.message, 'error_code': e.code}), 400
    except ValueError as e:
        # preflight_custom_paths' confirmable marker (CUSTOM_WEIGHTS_UNVERIFIED)
        return jsonify({'error': str(e)}), 400
    return jsonify({'ok': True, **out})

def _hf_storage_namespace():
    """(namespace, token) for the account whose private storage matters, or a
    (None, reason) pair. HF_TOKEN owns the lds-base-* caches; HF_CLOUD_TOKEN is
    scoped to the dense DELIVERY namespace and may not even be able to list
    them, so the general token is preferred and the dense one is the fallback."""
    from lds_sdk.cloud_host.services.hf_publish import HfPublishError, _make_api
    for key in ('HF_TOKEN', 'HF_CLOUD_TOKEN'):
        token = cfg.secret(key)
        if not token:
            continue
        try:
            who = _make_api(token).whoami() or {}
        except HfPublishError:
            continue
        except Exception:
            continue
        name = str((who or {}).get('name') or '').strip()
        if name:
            return name, token, who
    return None, None, {}

@bp.post('/tools/fp8-deliver/plan')
def tools_fp8_deliver_plan():
    """Where the file will land, what it will weigh, and whether the disk can
    take it — answered BEFORE the click. Always 200: a refusal is a disabled
    button carrying its reason, not a toast after the user committed."""
    from lds_cloud_training import fp8_local_delivery
    d = request.get_json(silent=True) or {}
    return jsonify(fp8_local_delivery.describe(
        repo_id=d.get('repo_id'), filename=d.get('filename'), path=d.get('path'),
        family=d.get('family'), keep_master=d.get('keep_master', True),
        destination_dir=d.get('destination_dir')))

@bp.post('/tools/fp8-deliver')
def tools_fp8_deliver_start():
    from lds_cloud_training import fp8_local_delivery
    d = request.get_json(silent=True) or {}
    try:
        info = fp8_local_delivery.start(
            current_app._get_current_object(),
            repo_id=d.get('repo_id'), filename=d.get('filename'),
            path=d.get('path'), family=d.get('family'),
            keep_master=d.get('keep_master', True),
            destination_dir=d.get('destination_dir'))
    except Exception as e:
        return _map_error(e)
    return jsonify({'ok': True, **info, 'status': fp8_local_delivery.status()})

@bp.get('/tools/fp8-deliver/status')
def tools_fp8_deliver_status():
    from lds_cloud_training import fp8_local_delivery
    return jsonify({'ok': True, **(fp8_local_delivery.status() or {})})

@bp.post('/tools/fp8-deliver/cancel')
def tools_fp8_deliver_cancel():
    """Stop the job. The bytes already downloaded stay on disk, so starting
    again resumes rather than restarts."""
    from lds_cloud_training import fp8_local_delivery
    return jsonify({'ok': True, 'cancelled': fp8_local_delivery.cancel(),
                    **(fp8_local_delivery.status() or {})})

@bp.post('/dataset/<int:dataset_id>/train/dense/send-plan')
def dataset_dense_send_plan(dataset_id):
    """What "Send to ComfyUI" would do — link or copy, where, at what cost.
    Always 200: a refusal is a disabled button carrying its reason."""
    from lds_cloud_training import dense_artifacts
    if not svc.get_dataset(LOCAL_USER, dataset_id):
        return jsonify({'error': 'not found'}), 404
    d = request.get_json(silent=True) or {}
    return jsonify(dense_artifacts.send_plan(dataset_id, d.get('run_id')))

@bp.post('/dataset/<int:dataset_id>/train/dense/send')
def dataset_dense_send(dataset_id):
    from lds_cloud_training import dense_artifacts
    if not svc.get_dataset(LOCAL_USER, dataset_id):
        return jsonify({'error': 'not found'}), 404
    d = request.get_json(silent=True) or {}
    try:
        info = dense_artifacts.send_to_comfyui(
            current_app._get_current_object(), dataset_id, d.get('run_id'))
    except Exception as e:
        return _map_error(e)
    return jsonify({'ok': True, **info, 'job': dense_artifacts.status()})

@bp.get('/tools/dense-send/status')
def tools_dense_send_status():
    """Global, like the fp8 job's: one send at a time, and it outlives the tab."""
    from lds_cloud_training import dense_artifacts
    return jsonify({'ok': True, **(dense_artifacts.status() or {})})

@bp.post('/dataset/<int:dataset_id>/train/dense/delete')
def dataset_dense_delete(dataset_id):
    """Move ONE of a full model's files to the app trash — recoverable on
    purpose: these cost hours of GPU, and a mis-click must not be final."""
    from lds_cloud_training import dense_artifacts
    if not svc.get_dataset(LOCAL_USER, dataset_id):
        return jsonify({'error': 'not found'}), 404
    d = request.get_json(silent=True) or {}
    try:
        out = dense_artifacts.delete_artifact(
            dataset_id, d.get('run_id'), d.get('filename'))
    except Exception as e:
        return _map_error(e)
    return jsonify({'ok': True, **out})

@bp.post('/cloud/quantize/plan')
def cloud_quantize_plan():
    """Cost, duration cap and storage impact of quantizing a delivered artifact
    in the cloud — always answered BEFORE anything is rented."""
    gate = _require_cloud()
    if gate:
        return gate
    from lds_cloud_training import cloud_quantize
    d = request.get_json(silent=True) or {}
    try:
        return jsonify({'ok': True, **cloud_quantize.plan(
            d.get('repo_id'), filename=d.get('filename'),
            keep_bf16=d.get('keep_bf16', True))})
    except Exception as e:
        return _map_error(e)

@bp.post('/cloud/quantize')
def cloud_quantize_start():
    gate = _require_cloud()
    if gate:
        return gate
    from lds_cloud_training import cloud_quantize
    d = request.get_json(silent=True) or {}
    try:
        planned = cloud_quantize.start(
            current_app._get_current_object(), d.get('repo_id'),
            filename=d.get('filename'), keep_bf16=d.get('keep_bf16', True),
            # The price the user read on screen: the rental re-searches offers,
            # and must not silently land on a dearer machine than the one quoted.
            quoted_price=d.get('quoted_price_per_hour'))
    except Exception as e:
        return _map_error(e)
    return jsonify({'ok': True, **planned, 'status': cloud_quantize.status()})

@bp.get('/cloud/quantize/status')
def cloud_quantize_status():
    """State of the cloud quantization, and a sweep for orphaned pods.

    The sweep runs HERE on purpose: this endpoint is what the UI polls, so a
    machine left behind by an app restart is reaped by the act of looking at it.
    """
    gate = _require_cloud()
    if gate:
        return gate
    from lds_cloud_training import cloud_quantize
    reaped = cloud_quantize.reconcile_orphans()
    return jsonify({'ok': True, 'reaped': reaped, **(cloud_quantize.status() or {})})

@bp.get('/cloud/hf-storage')
def cloud_hf_storage():
    """Measured private storage + the lds-base-* cache inventory.

    Answers 200 with ok=false rather than an error status when the Hub cannot be
    measured: this card must be able to SAY it does not know."""
    gate = _require_cloud()
    if gate:
        return gate
    from lds_cloud_training import hf_storage
    namespace, token, who = _hf_storage_namespace()
    if not namespace:
        return jsonify({'ok': False, 'reason': 'no_token',
                        'error': 'no Hugging Face token configured — add HF_TOKEN '
                                 'in Settings ▸ Local tools'})
    usage = hf_storage.private_storage_usage(namespace, token)
    inventory = hf_storage.base_cache_inventory(namespace, token, LOCAL_USER,
                                                _usage=usage)
    # No dataset in hand here — this card describes the account, not one run.
    # It therefore quotes the SHIPPED defaults (1 checkpoint + the fp8 export);
    # the per-run figure, which follows that dataset's own "keep" choice, is
    # shown in the training panel and enforced at launch.
    forecast = hf_storage.dense_storage_forecast(
        namespace, token, keeps=lt.dense_max_step_saves_for(None), who=who,
        _usage=usage, fp8_export=True)
    forecast.pop('usage', None)
    inventory.pop('usage', None)
    return jsonify({'ok': usage['ok'], 'namespace': namespace,
                    'reason': usage.get('reason'),
                    'partial': usage.get('partial', False),
                    'used_bytes': usage.get('used_bytes'),
                    'private_repo_count': usage.get('private_repo_count'),
                    'unsized_repo_count': usage.get('unsized_repo_count'),
                    'forecast': forecast, **inventory})

@bp.delete('/cloud/hf-storage/base/<repo_name>')
def cloud_hf_storage_delete_base(repo_name):
    """Delete ONE lds-base-* cache repo (the service validates the name)."""
    gate = _require_cloud()
    if gate:
        return gate
    from lds_cloud_training import hf_storage
    from lds_sdk.cloud_host.services.hf_publish import HfPublishError
    namespace, token, _who = _hf_storage_namespace()
    if not namespace:
        return jsonify({'error': 'no Hugging Face token configured'}), 400
    try:
        out = hf_storage.delete_base_cache(namespace, repo_name, token)
    except HfPublishError as e:
        return jsonify({'error': e.message, 'error_code': e.code}), 400
    except Exception as e:
        return _map_error(e)
    return jsonify(out)

@bp.post('/cloud/hf-storage/base/delete-all')
def cloud_hf_storage_delete_all_bases():
    """Delete every lds-base-* cache of the account. Partial failures reported."""
    gate = _require_cloud()
    if gate:
        return gate
    from lds_cloud_training import hf_storage
    namespace, token, _who = _hf_storage_namespace()
    if not namespace:
        return jsonify({'error': 'no Hugging Face token configured'}), 400
    try:
        out = hf_storage.delete_all_base_caches(namespace, token, LOCAL_USER)
    except Exception as e:
        return _map_error(e)
    return jsonify(out)

@bp.post('/dataset/train/cloud/retry')
def dataset_train_cloud_retry():
    """↻ Retry d'un run en erreur (page Cloud) : relance avec les paramètres
    exacts du run raté — pod frais, mêmes garde-fous que tout launch."""
    gate = _require_cloud()
    if gate:
        return gate
    d = request.get_json(silent=True) or {}
    try:
        res = ct.retry_cloud_run(LOCAL_USER, int(d.get('run_id') or 0))
    except Exception as e:
        return _map_error(e)
    return jsonify({'ok': True, **res})

@bp.post('/dataset/train/cloud/continue')
def dataset_train_cloud_continue():
    """▶ Continue d'un run cloud TERMINÉ (page Runs) : reprend depuis un checkpoint
    harvesté (from_step, défaut = dernier) et vise step_de_reprise + extra_steps —
    pod frais, mêmes garde-fous que tout launch ; le monitor dépose le checkpoint
    sur le pod avant de démarrer (auto-resume ai-toolkit). overrides = réglages sûrs
    (le service refuse toute autre clé → 400)."""
    gate = _require_cloud()
    if gate:
        return gate
    d = request.get_json(silent=True) or {}
    try:
        res = ct.continue_cloud_run(LOCAL_USER, int(d.get('run_id') or 0),
                                    extra_steps=d.get('extra_steps', 1000),
                                    from_step=d.get('from_step'),
                                    overrides=d.get('overrides'),
                                    resume_mode=d.get('resume_mode', 'weights_only'),
                                    state_bundle_id=d.get('state_bundle_id'),
                                    transport=d.get('transport'),
                                    allow_parallel_run=bool(d.get('allow_parallel_run')))
    except Exception as e:
        return _map_error(e)
    return jsonify({'ok': True, **res})

@bp.post('/dataset/train/cloud/resume-plan')
def dataset_train_cloud_resume_plan():
    """The two roads a full model can take back to a pod, with their duration
    and their GPU cost — answered BEFORE anything is rented, like every other
    plan endpoint here. Always 200: a road that cannot be taken comes back
    unavailable with the reason, because a disabled button that explains itself
    is the whole point of this panel."""
    gate = _require_cloud()
    if gate:
        return gate
    d = request.get_json(silent=True) or {}
    try:
        return jsonify({'ok': True, **ct.dense_resume_plan(
            LOCAL_USER, int(d.get('run_id') or 0),
            from_step=d.get('from_step'))})
    except Exception as e:
        return _map_error(e)

@bp.post('/dataset/train/cloud/recheck-delivery')
def dataset_train_cloud_recheck_delivery():
    """Re-verify one dense run's Hugging Face delivery without renting a GPU."""
    body = request.get_json(silent=True) or {}
    if body.get('run_id') in (None, ''):
        return jsonify({'error': 'run_id is required'}), 400
    try:
        result = ct.recheck_full_transformer_delivery(body['run_id'])
    except Exception as exc:
        return _map_error(exc)
    return jsonify(result)

@bp.post('/dataset/train/cloud/fetch-local')
def dataset_train_cloud_fetch_local():
    """Bring ONE kept dense run's files home (or stop doing it).

    Answers immediately: the transfer is tens of minutes of ~26 GB and runs in
    the background, reporting through the run's own phase line. ``cancel: true``
    stops it and keeps every byte already downloaded.
    """
    body = request.get_json(silent=True) or {}
    if body.get('run_id') in (None, ''):
        return jsonify({'error': 'run_id is required'}), 400
    try:
        result = ct.fetch_dense_locally(body['run_id'],
                                        cancel=body.get('cancel') is True)
    except Exception as exc:
        return _map_error(exc)
    return jsonify(result)

@bp.post('/dataset/<int:dataset_id>/train/cloud/continue-local')
def dataset_train_cloud_continue_local(dataset_id):
    """▶ Continue d'un checkpoint LOCAL dans le CLOUD (voie « Cloud » de la modale
    Continue, côté dataset) : le fichier du run local est semé sur un pod frais
    (resume_ckpt_path) et le job vise step_de_reprise + extra_steps. Mêmes
    garde-fous que tout launch cloud (clé vast.ai, budget, limite de runs actifs,
    unicité par famille) — c'est un launch_cloud_training normal."""
    gate = _require_cloud()
    if gate:
        return gate
    ds = svc.get_dataset(LOCAL_USER, dataset_id)
    if not ds:
        return jsonify({'error': 'not found'}), 404
    d = request.get_json(silent=True) or {}
    # The seed comes from the local lane, whose checkpoints are all LoRAs.
    # Freeze the source artifact kind instead of consulting mutable UI state.
    mode = 'lora'
    kw = {'extra_steps': d.get('extra_steps', 1000),
          'training_mode': mode}
    if 'base_model' in d:
        kw['base_model'] = d.get('base_model')
    if d.get('variant'):
        kw['variant'] = d.get('variant')
    if d.get('train_type'):
        kw['train_type'] = d.get('train_type')
    if d.get('from_step') is not None:
        kw['from_step'] = d.get('from_step')
    if d.get('overrides') is not None:
        kw['overrides'] = d.get('overrides')
    kw['resume_mode'] = d.get('resume_mode', 'weights_only')
    if d.get('state_bundle_id') is not None:
        kw['state_bundle_id'] = d.get('state_bundle_id')
    if d.get('gpu_name'):
        kw['gpu_name'] = d.get('gpu_name')
    kw['masked'] = d.get('masked')
    kw['allow_unverified_weights'] = bool(d.get('allow_unverified_weights'))
    kw['allow_caption_mismatch'] = bool(d.get('allow_caption_mismatch'))
    kw['allow_uncaptioned'] = bool(d.get('allow_uncaptioned'))
    kw['allow_caption_quality'] = bool(d.get('allow_caption_quality'))
    kw['allow_not_ready'] = bool(d.get('allow_not_ready'))
    kw['allow_parallel_run'] = bool(d.get('allow_parallel_run'))
    try:
        res = ct.continue_local_run_in_cloud(LOCAL_USER, dataset_id, **kw)
    except Exception as e:
        return _map_error(e)
    return jsonify({'ok': True, **res})

@bp.get('/dataset/<int:dataset_id>/train/cloud/offers')
def dataset_train_cloud_offers(dataset_id):
    """Live GPU speed tiers for the launch dialog (price/h + approx time+cost).
    Read-only — rents nothing; the launch call rents the chosen class."""
    gate = _require_cloud()
    if gate:
        return gate
    ds = svc.get_dataset(LOCAL_USER, dataset_id)
    if not ds:
        return jsonify({'error': 'not found'}), 404
    try:
        mode = lt.training_mode(ds, request.args.get('training_mode') or None)
        data = ct.gpu_tiers(LOCAL_USER, dataset_id,
                            train_type=request.args.get('train_type'),
                            variant=request.args.get('variant'),
                            steps=request.args.get('steps', type=int),
                            training_mode=mode)
    except Exception as e:
        return _map_error(e)
    return jsonify({'ok': True, **data})

@bp.get('/dataset/train/cloud/status')
def dataset_train_cloud_status():
    return jsonify(ct.cloud_status())

@bp.get('/dataset/train/cloud/runs')
def dataset_train_cloud_runs():
    """Active + recent cloud runs for the dedicated Cloud-runs hub page.
    Open like status (no gate): an unconfigured backend just returns empties."""
    return jsonify(ct.all_runs(limit=request.args.get('limit', default=20, type=int)))

def _parse_run_id_arg():
    """?run_id= as an int, or None when absent — but a malformed value (e.g.
    '?run_id=abc') is a 404, never the silent fallback to the newest run that
    `request.args.get('run_id', type=int)` gives: it also turns "the run I
    just addressed" into a stranger."""
    raw = request.args.get('run_id')
    if raw is None:
        return None, True
    try:
        return int(raw), True
    except (TypeError, ValueError):
        return None, False

@bp.get('/dataset/<int:dataset_id>/train/cloud/progress')
def dataset_train_cloud_progress(dataset_id):
    run_id, ok = _parse_run_id_arg()
    if not ok:
        return jsonify({'error': 'invalid run_id'}), 404
    try:
        return jsonify(ct.cloud_progress(
            LOCAL_USER, dataset_id,
            train_type=request.args.get('train_type'),
            run_id=run_id))
    except LookupError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        return _map_error(e)

@bp.post('/dataset/train/cloud/stop')
def dataset_train_cloud_stop():
    """Stop a cloud run and report what really happened.

    The answer is never a courtesy 'ok': when no monitor thread is in a state
    to honour the request, request_stop terminates the pod itself, and if even
    that fails the payload carries the instance id the user must destroy by
    hand (HTTP stays 200 — the request was understood, the outcome is in the
    body, which is what the UI renders)."""
    d = request.get_json(silent=True) or {}
    # {ban_host: true} = "and do not rent this machine again" (mr.arrow,
    # Discord). Opt-in: a stop alone says nothing about the host.
    res = ct.request_stop(d.get('run_id'), ban_host=bool(d.get('ban_host')))
    if not isinstance(res, dict):       # defensive: legacy bool contract
        res = {'ok': bool(res)}
    return jsonify(res)
