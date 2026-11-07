"""Dataset lifecycle for registered local plugin engines (API 1.23).

The host owns rows, references and GPU admission; plugins own their graph and
preparation. No engine-specific model or prompt policy belongs here.
"""
from __future__ import annotations

import os
import random

from ..engines import registry
from ..extensions import db
from ..models import FaceDatasetImage


class LocalEngineNotReady(ValueError):
    def __init__(self, engine, detail):
        super().__init__(detail)
        self.engine = engine
        self.plugin = registry.get(engine).plugin


def is_plugin_engine(engine):
    spec = registry.get(engine)
    return bool(spec and spec.kind == registry.LOCAL and spec.plugin
                and spec.local_enqueue is not None)


def _spec(engine):
    from .. import config
    spec = registry.require_available(engine)
    if not is_plugin_engine(engine):
        raise ValueError(f'Unsupported local dataset engine: {engine}')
    enabled = config.get('engines.enabled') or []
    if enabled and engine not in enabled:
        raise ValueError(f'Enable {spec.label} in its plugin settings before generating.')
    return spec


def _references(ds):
    from . import face_dataset_service as datasets
    if not ds.ref_filename:
        raise ValueError('reference image required')
    source = datasets._ref_path(ds)
    extras = [os.path.join(datasets._dataset_dir(ds.id), name)
              for name in datasets.extra_ref_filenames(ds)]
    if not all(os.path.isfile(path) for path in [source, *extras]):
        raise ValueError('reference image file missing')
    return source, extras


def preflight(user_id, dataset_id, engine):
    from . import face_dataset_service as datasets
    spec = _spec(engine)
    ds = datasets.get_dataset(user_id, dataset_id)
    if ds is None:
        raise ValueError('dataset not found')
    datasets._guard_not_bank_export(dataset_id)
    _source, extras = _references(ds)
    result = spec.local_preflight(reference_count=1 + len(extras),
                                  subject_type=datasets.subject_type_of(ds))
    if not isinstance(result, dict) or result.get('ok') is not True:
        detail = result.get('detail') if isinstance(result, dict) else None
        raise LocalEngineNotReady(engine, detail or 'Prepare this engine in Plugins before generating.')
    return ds


def enqueue(user_id, ds, engine, prompt, *, label=None, framing=None, seed=None):
    from . import face_dataset_service as datasets
    spec = _spec(engine)  # Recheck enablement at every admission, including retries.
    source, extras = _references(ds)
    suffix = datasets.dataset_prompt_suffix(ds, framing)
    edit_prompt = '\n\n'.join(part for part in (prompt, suffix) if part)
    return spec.local_enqueue(
        user_id=str(user_id), source_filename=ds.ref_filename,
        source_path=source, extra_ref_paths=extras, edit_prompt=edit_prompt,
        subject_type=datasets.subject_type_of(ds), framing=framing, seed=seed,
        aspect_ratio=datasets.aspect_for_label(label, framing),
        extra_metadata={'is_dataset': True, 'dataset_id': ds.id,
                        'variation_label': label, 'engine': engine,
                        'dataset_engine_plugin': spec.plugin,
                        'engine_label': spec.label})


def _cancel_unlinked(user_id, job_id):
    from ..job_queue import queue_manager
    queue_manager.cancel_job(job_id, str(user_id), 'image')


def generate(user_id, dataset_id, variations, multiplier, *, engine):
    from . import face_dataset_service as datasets
    ds = preflight(user_id, dataset_id, engine)
    mult = max(1, int(multiplier))
    datasets.check_fanout_budget(dataset_id, len(variations) * mult, generators=(engine,))
    ids = []
    try:
        for shot in variations:
            for _ in range(mult):
                seed = random.randint(0, 2**64 - 1)
                row = FaceDatasetImage(
                    dataset_id=dataset_id, source='generated', status='pending',
                    variation_label=shot.get('label'), framing=shot.get('framing'),
                    variation_prompt=shot['prompt'], klein_model=engine,
                    generation_meta=datasets._generation_meta_json(
                        engine=engine, seed=seed,
                        aspect=datasets.aspect_for_label(shot.get('label'), shot.get('framing'))))
                db.session.add(row)
                db.session.commit()
                image_id, job_id = row.id, None
                try:
                    job_id = enqueue(user_id, ds, engine, shot['prompt'], seed=seed,
                                     label=shot.get('label'), framing=shot.get('framing'))
                    row = datasets._live_image_row(image_id)
                    if row is None:
                        _cancel_unlinked(user_id, job_id)
                        break  # Stop removed the candidate during admission.
                    row.job_id = job_id
                    db.session.commit()
                    ids.append(image_id)
                except Exception:
                    db.session.rollback()
                    if job_id:
                        _cancel_unlinked(user_id, job_id)
                    row = datasets._live_image_row(image_id)
                    if row is not None:
                        row.status = 'failed'
                        db.session.commit()
                    raise
            else:
                continue
            break
    finally:
        datasets._sync_generate_activity(dataset_id)
    return ids
