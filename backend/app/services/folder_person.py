""""Single person here" — folder-level person assertions for the 🗃️ image bank.

WHY
---
"Group by person" is the bank's most expensive pass: one InsightFace embedding
per image, thousands of images, minutes of GPU (or a long CPU crawl). On scraped
material that cost usually buys nothing — the sources are already ONE FOLDER PER
PERSON, and the pass spends its time rediscovering by inference what the folder
name said for free.

This module is the user saying it instead. One click on a subfolder:
  * every image of that folder gets a person id IMMEDIATELY — zero inference;
  * the embeddings pass then SKIPS those images entirely (that skip IS the
    saving, not a nicety on top of it);
  * the rule is PERSISTED, so a re-scan keeps it and an image that lands in the
    folder tomorrow joins the group on insert;
  * it is REVOCABLE — the user was wrong, one click puts the folder back in the
    way of normal clustering and dissolves the asserted group.

WHAT IT DOES NOT DO
-------------------
It does not verify anything. A declaration is not evidence, so a SAMPLE CHECK is
offered next to it: ~15 images spread across the folder, embedded on their own,
compared at the SAME cosine threshold the clustering uses (bank.face_threshold —
there is one truth about "same person" in this app, not two). Its verdict is
INFORMATIVE: "sample consistent (14/15 same person)" or "2 different faces in
the sample — check this folder". The assertion stands either way; the user's
folder, the user's call.

HOW IT COEXISTS WITH THE EMBEDDING CLUSTERS
-------------------------------------------
Same table, same column, same id space: `bank_image.face_cluster`. An asserted
group IS a person cluster — every reader (the person chips, the coverage advice,
the cluster filter, promote) keeps working with no knowledge of this module.
What tells them apart is `bank_image.face_cluster_origin` ('asserted' vs NULL),
and it exists for exactly two reasons:
  1. the embeddings pass must not silently overwrite the user's word, and must
     not renumber its own clusters onto an asserted id — so it skips asserted
     rows and OFFSETS its ids above every asserted id in the bank;
  2. revoking must know which ids it may clear.
Because the ids share one space, a later CROSS-FOLDER MERGE (linking two folders
that turn out to be the same person, or joining an asserted folder to a computed
cluster) is a plain id remap over `face_cluster` — nothing here forbids it, and
an asserted folder is not a wall around its images.
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone

from sqlalchemy import func

from ..extensions import db
from ..models import BankFolderPerson, BankImage

logger = logging.getLogger(__name__)

# How many images the sample check embeds. Small enough to stay a few seconds of
# GPU (vs thousands for a full pass), big enough that a second person occupying a
# decent share of the folder is very likely to be drawn at least once.
SAMPLE_SIZE = 15
ASSERTED = 'asserted'


def _svc():
    """The bank service, imported late — it imports this module too."""
    from . import image_bank_service as banks
    return banks


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# --- reading ----------------------------------------------------------------
def asserted_subfolders(bank_id) -> set:
    """{subfolder} the user has declared to hold a single person."""
    return {row.subfolder for row in
            BankFolderPerson.query.filter_by(bank_id=bank_id).all()}


def assertion_for(bank_id, subfolder):
    return (BankFolderPerson.query
            .filter_by(bank_id=bank_id, subfolder=subfolder or '').first())


def _report_of(row) -> dict | None:
    if not row.sample_report:
        return None
    try:
        return json.loads(row.sample_report)
    except ValueError:
        return None


def _folder_rows_q(bank_id, subfolder):
    """Every image row of one TOP-LEVEL subfolder — the same set the Subfolder
    filter scopes to, expressed the same way (prefix match, '' = bank root)."""
    q = BankImage.query.filter_by(bank_id=bank_id)
    if (subfolder or '') == '':
        return q.filter(~BankImage.relpath.contains(os.sep))
    return q.filter(BankImage.relpath.startswith(subfolder + os.sep))


def _to_check(bank_id, subfolder) -> list:
    """Images of the folder the face machinery already looked at and could NOT
    read as one clean face: no face at all, a face too small/too turned to
    identify, an unreadable file. The assertion covers them anyway — they are
    listed, never excluded, because "I could not see a face here" is not "this
    is someone else". Only rows a pass (or the sample check) actually measured
    appear: a NULL face_state means "not looked at", a different thing."""
    rows = (_folder_rows_q(bank_id, subfolder)
            .filter(BankImage.face_state.isnot(None),
                    BankImage.face_state != 'scorable')
            .order_by(BankImage.id.asc()).limit(200).all())
    # 'name' is the BASENAME, not the relpath — the key is named for what it
    # holds. The grid already knows how to open an image from its id.
    return [{'id': r.id, 'state': r.face_state,
             'name': os.path.basename(r.relpath)} for r in rows]


def payload(user_id, bank_id) -> dict | None:
    """Every assertion of a bank, for the Subfolder panel."""
    banks = _svc()
    if not banks.get_bank(user_id, bank_id):
        return None
    out = []
    for row in (BankFolderPerson.query.filter_by(bank_id=bank_id)
                .order_by(BankFolderPerson.subfolder.asc()).all()):
        covered = (_folder_rows_q(bank_id, row.subfolder)
                   .filter(BankImage.face_cluster_origin == ASSERTED).count())
        out.append({
            'subfolder': row.subfolder,
            'cluster_id': row.cluster_id,
            'images': covered,
            'sample': _report_of(row),
            'to_check': _to_check(bank_id, row.subfolder),
        })
    return {'assertions': out, 'sample_size': SAMPLE_SIZE}


# --- writing ----------------------------------------------------------------
def _next_cluster_id(bank_id) -> int:
    """One above every person id currently in use in this bank — computed and
    asserted alike, so an assertion can never land on an id the last embeddings
    pass already handed out."""
    used = (db.session.query(func.max(BankImage.face_cluster))
            .filter(BankImage.bank_id == bank_id).scalar() or 0)
    reserved = (db.session.query(func.max(BankFolderPerson.cluster_id))
                .filter(BankFolderPerson.bank_id == bank_id).scalar() or 0)
    return int(max(used, reserved)) + 1


def asserted_offset(bank_id) -> int:
    """How far the embeddings pass must push its own 1-based cluster ids so they
    never collide with an asserted group's."""
    return int((db.session.query(func.max(BankFolderPerson.cluster_id))
                .filter(BankFolderPerson.bank_id == bank_id).scalar() or 0))


def assert_single_person(user_id, bank_id, subfolder) -> dict:
    """Declare a subfolder to hold one person. Immediate, no inference at all.

    Idempotent: asserting an already-asserted folder just re-stamps it (useful
    after images arrived while a pass was running)."""
    banks = _svc()
    if not banks.get_bank(user_id, bank_id):
        raise ValueError('bank not found')
    sub = subfolder or ''
    q = _folder_rows_q(bank_id, sub)
    total = q.count()
    if not total:
        raise ValueError('this subfolder has no images')
    row = assertion_for(bank_id, sub)
    if row is None:
        row = BankFolderPerson(bank_id=bank_id, subfolder=sub,
                               cluster_id=_next_cluster_id(bank_id))
        db.session.add(row)
        db.session.flush()
    q.update({BankImage.face_cluster: row.cluster_id,
              BankImage.face_cluster_origin: ASSERTED},
             synchronize_session=False)
    db.session.commit()
    logger.info('bank %s: subfolder asserted as one person, %s image(s), '
                'person #%s', bank_id, total, row.cluster_id)
    return {'subfolder': sub, 'cluster_id': row.cluster_id, 'images': total}


def revoke(user_id, bank_id, subfolder) -> dict:
    """Undo the assertion: the group dissolves and the folder goes back to normal
    clustering. Only ids this module wrote are cleared — a row whose cluster the
    embeddings pass computed (before the assertion, or in a folder that partly
    overlaps) keeps it."""
    banks = _svc()
    if not banks.get_bank(user_id, bank_id):
        raise ValueError('bank not found')
    sub = subfolder or ''
    row = assertion_for(bank_id, sub)
    if row is None:
        raise ValueError('this subfolder is not asserted')
    cleared = (_folder_rows_q(bank_id, sub)
               .filter(BankImage.face_cluster_origin == ASSERTED)
               .update({BankImage.face_cluster: None,
                        BankImage.face_cluster_origin: None},
                       synchronize_session=False))
    db.session.delete(row)
    db.session.commit()
    logger.info('bank %s: assertion revoked, %s image(s) back to clustering',
                bank_id, cleared)
    return {'subfolder': sub, 'cleared': int(cleared)}


def drop_for_bank(bank_id) -> int:
    """Delete every assertion of a bank. Called BEFORE the bank row itself (the
    delete-500 lesson: children first, no relationship to flush them for us)."""
    return (BankFolderPerson.query.filter_by(bank_id=bank_id)
            .delete(synchronize_session=False))


def stamp_new_rows(bank_id, rows) -> int:
    """Apply the standing assertions to freshly inventoried rows, IN PLACE, before
    they are inserted. This is what makes an assertion a rule and not a one-off
    stamp: an image dropped into an asserted folder tomorrow joins its group the
    moment the folder sync sees it, with no pass and no click.

    ``rows`` are the plain dicts _insert_bank_images is about to core-insert."""
    if not rows:
        return 0
    by_sub = {r.subfolder: r.cluster_id for r in
              BankFolderPerson.query.filter_by(bank_id=bank_id).all()}
    if not by_sub:
        return 0
    banks = _svc()
    stamped = 0
    for row in rows:
        cid = by_sub.get(banks._subfolder_of(row.get('relpath') or ''))
        # Both keys are written on EVERY row, not only the matching ones: these
        # dicts go to one executemany, which takes its column list from the first
        # of them — a half-stamped batch would drop the ids of all the others.
        row['face_cluster'] = cid
        row['face_cluster_origin'] = ASSERTED if cid is not None else None
        if cid is not None:
            stamped += 1
    return stamped


# --- sample check -----------------------------------------------------------
_SAMPLE_PROGRESS_RE = re.compile(r'\[embed\] (\d+)/(\d+)')


def _stratified(rows, k=SAMPLE_SIZE) -> list:
    """``k`` rows spread EVENLY across the folder, not the first k and not a
    coin toss. Scraped folders are ordered by name, which is usually order of
    arrival — the first 15 files are one shoot, one day, often one outfit, and a
    second person who appears halfway through would never be drawn. Evenly
    spaced picks cover the whole folder, and being deterministic the same folder
    always gets the same verdict."""
    n = len(rows)
    if n <= k:
        return list(rows)
    return [rows[(i * n) // k] for i in range(k)]


def start_sample_check(app, user_id, bank_id, subfolder):
    """Embed ~15 images of the folder and report whether they look like ONE
    person, at the clustering threshold. Runs as a normal bank job (one per
    bank) because it loads the same model the full pass does."""
    banks = _svc()
    from .face_similarity import is_available
    from . import bank_jobs
    bank = banks.get_bank(user_id, bank_id)
    if not bank:
        raise ValueError('bank not found')
    if assertion_for(bank_id, subfolder or '') is None:
        raise ValueError('this subfolder is not asserted')
    if not is_available():
        raise RuntimeError(
            'face scoring is not installed (Quality tools step in Setup)')
    return bank_jobs.start(app, bank_id, 'folder-check',
                           _sample_job(bank_id, subfolder or ''),
                           total=SAMPLE_SIZE)


def _verdict(largest, scorable, faces) -> tuple:
    """(verdict, sentence) — plain English, and never more certain than 15 images
    allow. It says what the SAMPLE showed; it never says the folder is clean."""
    if scorable < 2:
        return 'inconclusive', (
            f'only {scorable} of the sampled images had a usable face — '
            'nothing to compare, the folder is unchanged')
    if faces <= 1:
        return 'consistent', (
            f'sample consistent ({largest}/{scorable} same person)')
    return 'mixed', (
        f'{faces} different faces in the sample — check this folder')


def _sample_job(bank_id, subfolder):
    def run(job):
        from contextlib import nullcontext
        from . import bank_jobs
        from ..gpu_window import gpu_exclusive_vision_window
        from ..models import ImageBank
        banks = _svc()
        bank = db.session.get(ImageBank, bank_id)
        row = assertion_for(bank_id, subfolder)
        if not bank or row is None:
            return
        pool = (_folder_rows_q(bank_id, subfolder)
                .order_by(BankImage.relpath.asc()).all())
        picked = _stratified(pool)
        by_path = {}
        for r in picked:
            p = banks.abs_image_path(bank, r)
            if banks._is_safe_bank_source(p, label='folder sample check'):
                by_path[p] = r.id
        paths = list(by_path)
        bank_jobs.progress(job, done=0, total=len(paths), detail='sample check')
        if not paths:
            bank_jobs.progress(job, detail='no readable image to sample')
            return
        banks._bank_dir(bank_id).mkdir(parents=True, exist_ok=True)
        th = banks.thresholds()
        device, use_gpu = banks._resolve_face_device()
        # Its OWN cache, never the bank-wide face cache: a 15-row .npz written
        # here must not race (or truncate) the full pass's thousands of rows.
        cache_path = banks._bank_dir(bank_id) / 'folder_sample.npz'
        req = json.dumps({
            'images': paths,
            'models_root': banks.cfg.get('face_scoring.models_root') or None,
            'cache': str(cache_path),
            'cancel_file': str(cache_path) + '.cancel',
            'threshold': th['face_threshold'],
            'device': device,
        })
        import sys
        python = banks.cfg.get('face_scoring.python') or sys.executable
        window = (gpu_exclusive_vision_window(flag_ttl=600) if use_gpu
                  else nullcontext())
        banks._release_db_before_inference()
        data, stderr_tail, returncode = banks._drive_infer_subprocess(
            job, python, banks._EMBED_SCRIPT, req, cache_path,
            _SAMPLE_PROGRESS_RE, window)
        if data.get('cancelled') or (bank_jobs.cancelled(job) and not data.get('ok')):
            bank_jobs.progress(job, detail='sample check stopped — '
                                           'the assertion is unchanged')
            return
        if not data.get('ok'):
            tail = data.get('error') or (stderr_tail[-1] if stderr_tail else '')
            raise RuntimeError(tail or f'sample check produced no output '
                                       f'(rc={returncode})')
        results = data.get('results') or {}
        clusters = data.get('clusters') or {}
        # The states are REAL measurements on real images of this folder: write
        # them back (never the cluster id — that belongs to the assertion), so
        # the "to check" list has substance even on a bank whose face pass never
        # ran. This is also why the sample is not wasted work.
        for p, image_id in by_path.items():
            live = banks._live_image(image_id)
            if live is None or live.face_state is not None:
                continue
            res = results.get(p) or {}
            live.face_state = res.get('state')
            live.face_det = res.get('det')
        db.session.commit()
        sizes = {}
        for cid in clusters.values():
            sizes[cid] = sizes.get(cid, 0) + 1
        scorable = sum(sizes.values())
        faces = len(sizes)
        largest = max(sizes.values()) if sizes else 0
        verdict, sentence = _verdict(largest, scorable, faces)
        fresh = assertion_for(bank_id, subfolder)
        if fresh is not None:      # revoked while the check ran — say nothing
            fresh.sample_report = json.dumps({
                'checked_at': _now_iso(), 'sample': len(paths),
                'scorable': scorable, 'largest': largest, 'faces': faces,
                'threshold': th['face_threshold'],
                'verdict': verdict, 'note': sentence})
            db.session.commit()
        bank_jobs.progress(job, detail=sentence)
    return run
