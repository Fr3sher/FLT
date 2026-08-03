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

from sqlalchemy import func, or_

from ..extensions import db
from ..models import BankFolderPerson, BankFolderProbe, BankImage

logger = logging.getLogger(__name__)

# How many images the sample check embeds. Small enough to stay a few seconds of
# GPU (vs thousands for a full pass), big enough that a second person occupying a
# decent share of the folder is very likely to be drawn at least once.
SAMPLE_SIZE = 15
ASSERTED = 'asserted'
# A folder too small to sample meaningfully is not probed: below this, "15 of 3
# images agree" is arithmetic, not evidence, and a suggestion built on it would
# be noise on every stray folder a scrape leaves behind.
MIN_PROBE_IMAGES = 5
# Ceiling for the MANUAL scan, which pays ~15 embeddings per folder. A bank with
# 200 subfolders would otherwise cost 3 000 inferences behind one click. The
# biggest unprobed folders go first (they are where a suggestion is worth most)
# and the job says out loud how many it left. The automatic pass after 👤 Group
# by person has NO ceiling: it reuses embeddings that pass already cached, so it
# costs nothing to cover every folder.
MAX_SCAN_FOLDERS = 20
# Ceiling for the PREFLIGHT — the same probe, run as the PREAMBLE of 👤 Group by
# person instead of hiding behind a button nobody presses. It is generous where
# the manual scan is cautious, because the comparison is the opposite one: the
# user is about to pay one embedding per image over the whole bank, so fifteen
# per folder is a rounding error next to it (200 folders = 3 000 embeddings,
# against 200 × 300 = 60 000 for the pass they just asked for). It stays a
# ceiling and not "no limit" — a bank of ten thousand folders would turn a
# preamble into a pass of its own — and whatever it does not reach is stated out
# loud, never assumed away.
MAX_PREFLIGHT_FOLDERS = 200


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
    return {'assertions': out, 'sample_size': SAMPLE_SIZE,
            # Folders the app probed by itself. They are OFFERS, not decisions:
            # nothing here has grouped a single image.
            'suggestions': suggestions(bank_id),
            'scannable': len(scan_candidates(bank_id)),
            'scan_limit': MAX_SCAN_FOLDERS}


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


# --- automatic suggestion (the same probe, over every folder) ---------------
# The single-folder check above answers "was I right?" AFTER the user declared.
# The same fifteen embeddings answer "would you like to declare?" BEFORE they
# did — which is the question that actually saves them work, because on a
# scraped bank most folders are one person and the user has no reason to guess
# which. So the probe runs over the folders on its own and the app SUGGESTS.
#
# It suggests. It never asserts. A wrong assertion made silently would corrupt
# the person grouping with something the user never said, and they would have no
# reason to look for it — so confirming stays one deliberate click.
def _folder_signature(bank_id, subfolder) -> str:
    """A cheap fingerprint of a folder's CONTENT: how many images it holds and
    the highest row id among them. Both change the moment images are added or
    removed, which is exactly when a probe stops describing reality. No hashing,
    no disk access — one aggregate query."""
    q = _folder_rows_q(bank_id, subfolder)
    n = q.count()
    top = q.with_entities(func.max(BankImage.id)).scalar() or 0
    return f'{int(n)}:{int(top)}'


def _sample_pool(bank_id, subfolder):
    """The rows a probe may sample: the folder's NON-REJECTED images. Rejected
    ones are excluded on purpose — they are outside what the face pass looks at,
    so sampling them would both cost embeddings nothing else has cached and let
    images the user already threw away drive a suggestion."""
    return (_folder_rows_q(bank_id, subfolder)
            .filter(BankImage.status != 'reject')
            .order_by(BankImage.relpath.asc()).all())


def probe_for(bank_id, subfolder):
    return (BankFolderProbe.query
            .filter_by(bank_id=bank_id, subfolder=subfolder or '').first())


def _probe_dict(row, fresh: bool, images: int = 0) -> dict:
    return {'subfolder': row.subfolder, 'verdict': row.verdict,
            'sample': row.sample, 'scorable': row.scorable,
            'largest': row.largest, 'faces': row.faces, 'note': row.note,
            # How many images accepting THIS folder would spare the pass. The
            # preflight totals them, so its offer can be answered against the
            # only number that matters: what it saves.
            'images': int(images),
            'checked_at': row.checked_at.isoformat() if row.checked_at else None,
            'stale': not fresh}


def _folder_counts(bank_id) -> dict:
    """{subfolder: non-rejected image count} — one query, the same pool the probe
    and the face pass work on."""
    from collections import Counter
    counts: Counter = Counter()
    for (rel,) in (db.session.query(BankImage.relpath)
                   .filter(BankImage.bank_id == bank_id,
                           BankImage.status != 'reject').all()):
        counts[_svc()._subfolder_of(rel)] += 1
    return dict(counts)


def suggestions(bank_id) -> list:
    """Every folder the app has probed and NOT been told about, with the stale
    ones marked rather than dropped silently."""
    asserted = asserted_subfolders(bank_id)
    counts = _folder_counts(bank_id)
    out = []
    for row in (BankFolderProbe.query.filter_by(bank_id=bank_id)
                .order_by(BankFolderProbe.subfolder.asc()).all()):
        if row.subfolder in asserted:
            continue          # already declared — a suggestion would be noise
        fresh = row.content_sig == _folder_signature(bank_id, row.subfolder)
        out.append(_probe_dict(row, fresh, counts.get(row.subfolder, 0)))
    return out


def scan_candidates(bank_id, limit=None) -> list:
    """(subfolder, image_count) for the folders worth probing, biggest first.

    Skipped: folders the user already declared (nothing to suggest), folders
    below MIN_PROBE_IMAGES (too small for a sample to mean anything), and
    folders whose probe still matches their content (already answered)."""
    counts = _folder_counts(bank_id)
    asserted = asserted_subfolders(bank_id)
    out = []
    for name, n in counts.items():
        if name in asserted or n < MIN_PROBE_IMAGES:
            continue
        got = probe_for(bank_id, name)
        if got is not None and got.content_sig == _folder_signature(bank_id, name):
            continue
        out.append((name, n))
    out.sort(key=lambda kv: (-kv[1], kv[0]))
    return out if limit is None else out[:limit]


def _write_probe(bank_id, subfolder, sizes, sample_n) -> str:
    """Persist one folder's verdict and return its sentence."""
    scorable = sum(sizes.values())
    faces = len(sizes)
    largest = max(sizes.values()) if sizes else 0
    verdict, sentence = _verdict(largest, scorable, faces)
    row = probe_for(bank_id, subfolder)
    if row is None:
        row = BankFolderProbe(bank_id=bank_id, subfolder=subfolder)
        db.session.add(row)
    row.verdict, row.note = verdict, sentence
    row.sample, row.scorable = sample_n, scorable
    row.largest, row.faces = largest, faces
    row.content_sig = _folder_signature(bank_id, subfolder)
    row.checked_at = datetime.now(timezone.utc)
    return verdict


def drop_probes_for_bank(bank_id) -> int:
    return (BankFolderProbe.query.filter_by(bank_id=bank_id)
            .delete(synchronize_session=False))


def _probe_groups(bank_id, bank, candidates) -> tuple:
    """({folder: {path: image_id}}, [child group payloads]) for a set of folders."""
    banks = _svc()
    by_folder, groups = {}, []
    for name, _n in candidates:
        picked = _stratified(_sample_pool(bank_id, name))
        paths = {}
        for r in picked:
            p = banks.abs_image_path(bank, r)
            if banks._is_safe_bank_source(p, label='folder person probe'):
                paths[p] = r.id
        if len(paths) >= 2:      # nothing to compare below two faces
            by_folder[name] = paths
            groups.append({'name': name, 'images': list(paths)})
    return by_folder, groups


def _apply_probe_results(bank_id, by_folder, data) -> dict:
    """Write the states back and persist one probe per folder. Returns
    {verdict: count} for the job's report."""
    banks = _svc()
    results = data.get('results') or {}
    group_clusters = data.get('group_clusters') or {}
    tally = {}
    for name, paths in by_folder.items():
        for p, image_id in paths.items():
            live = banks._live_image(image_id)
            if live is None or live.face_state is not None:
                continue
            res = results.get(p) or {}
            live.face_state = res.get('state')
            live.face_det = res.get('det')
        sizes = {}
        for cid in (group_clusters.get(name) or {}).values():
            sizes[cid] = sizes.get(cid, 0) + 1
        verdict = _write_probe(bank_id, name, sizes, len(paths))
        tally[verdict] = tally.get(verdict, 0) + 1
    db.session.commit()
    return tally


def _probe_detail(tally, scanned, left) -> str:
    """What the scan found, in the user's terms — and what it did NOT reach."""
    if not scanned:
        return 'no folder left to look at'
    likely = tally.get('consistent', 0)
    bits = [f'{likely} folder(s) look like one person' if likely
            else 'no folder looked like a single person']
    if tally.get('mixed'):
        bits.append(f'{tally["mixed"]} hold several')
    if tally.get('inconclusive'):
        bits.append(f'{tally["inconclusive"]} had too few faces to tell')
    out = f'{scanned} folder(s) sampled — ' + ', '.join(bits)
    if likely:
        out += ' — confirm the ones you recognise'
    if left:
        # Never mute a ceiling: a scan that covered 20 of 200 folders and said
        # nothing would read as "the other 180 are not one person".
        out += f' · {left} folder(s) not reached (biggest first — run it again)'
    return out


def _run_probe(job, bank_id, candidates, *, allow_inference: bool):
    """Sample ``candidates`` in ONE child call and persist their verdicts.

    ``allow_inference=False`` is the automatic path: it runs straight after the
    face pass, whose cache already holds every embedding it needs, so the child
    loads no model and touches no GPU. If an image is somehow missing from that
    cache the child would embed it — cheap at this size, and still bounded by the
    sample, but the flag is what lets the caller say honestly which it was."""
    from contextlib import nullcontext
    from . import bank_jobs
    from ..gpu_window import gpu_exclusive_vision_window
    from ..models import ImageBank
    banks = _svc()
    bank = db.session.get(ImageBank, bank_id)
    if not bank or not candidates:
        return None
    by_folder, groups = _probe_groups(bank_id, bank, candidates)
    if not groups:
        return None
    every_path = [p for g in groups for p in g['images']]
    banks._bank_dir(bank_id).mkdir(parents=True, exist_ok=True)
    th = banks.thresholds()
    device, use_gpu = banks._resolve_face_device()
    # The BANK's own face cache, deliberately: after 👤 Group by person every one
    # of these images is already in it, so the probe is free. One job runs per
    # bank, so nothing else can be writing this file underneath us.
    cache_path = banks._face_cache_path(bank_id)
    req = json.dumps({
        'images': every_path,
        'groups': groups,
        'models_root': banks.cfg.get('face_scoring.models_root') or None,
        'cache': str(cache_path),
        'cancel_file': str(cache_path) + '.cancel',
        'threshold': th['face_threshold'],
        'device': device,
    })
    import sys
    python = banks.cfg.get('face_scoring.python') or sys.executable
    window = (gpu_exclusive_vision_window(flag_ttl=900)
              if (use_gpu and allow_inference) else nullcontext())
    banks._release_db_before_inference()
    data, stderr_tail, returncode = banks._drive_infer_subprocess(
        job, python, banks._EMBED_SCRIPT, req, cache_path,
        _SAMPLE_PROGRESS_RE, window)
    if data.get('cancelled'):
        return None
    if not data.get('ok'):
        tail = data.get('error') or (stderr_tail[-1] if stderr_tail else '')
        raise RuntimeError(tail or f'folder scan produced no output '
                                   f'(rc={returncode})')
    return _apply_probe_results(bank_id, by_folder, data)


def start_folder_scan(app, user_id, bank_id, limit=None, kind='folder-scan'):
    """Sample every unprobed folder and suggest the ones that look like a single
    person. Costs ~15 embeddings per folder, capped at ``limit``.

    ``limit``/``kind`` exist for the PREFLIGHT, which is the same work with a
    different ceiling and a different name in the progress bar — not a second
    implementation. Both write ordinary probes, and a probe is an offer whoever
    produced it."""
    from .face_similarity import is_available
    from . import bank_jobs
    banks = _svc()
    if not banks.get_bank(user_id, bank_id):
        raise ValueError('bank not found')
    if not is_available():
        raise RuntimeError(
            'face scoring is not installed (Quality tools step in Setup)')
    cap = limit or MAX_SCAN_FOLDERS
    pending = scan_candidates(bank_id)
    if not pending:
        raise ValueError('every folder here has already been looked at '
                         '(or is asserted, or too small to sample)')
    return bank_jobs.start(app, bank_id, kind,
                           _folder_scan_job(bank_id, limit=cap),
                           total=min(len(pending), cap))


def _folder_scan_job(bank_id, limit=None):
    def run(job):
        from . import bank_jobs
        # Read at CALL time, never captured at import: the ceiling is a module
        # constant tests move around, and a default frozen into the signature
        # would quietly ignore them.
        cap = limit or MAX_SCAN_FOLDERS
        pending = scan_candidates(bank_id)
        picked = pending[:cap]
        left = len(pending) - len(picked)
        bank_jobs.progress(job, done=0, total=len(picked),
                           detail=f'sampling {len(picked)} folder(s)')
        tally = _run_probe(job, bank_id, picked, allow_inference=True)
        if tally is None:
            bank_jobs.progress(job, detail='folder scan stopped — '
                                           'nothing was changed')
            return
        bank_jobs.progress(job, detail=_probe_detail(tally, len(picked), left))
    return run


def probe_after_faces(job, bank_id) -> str:
    """Run the probe over EVERY unprobed folder right after the face pass, in
    that pass's own job. This is where the suggestion belongs: the embeddings it
    needs were just computed and cached, so covering two hundred folders costs no
    inference at all — the child loads no model when nothing is left to embed.

    It never raises: the face pass has already succeeded by the time this runs,
    and a failed suggestion must not turn a finished pass into a red one."""
    try:
        pending = scan_candidates(bank_id)
        if not pending:
            return ''
        tally = _run_probe(job, bank_id, pending, allow_inference=False)
        if not tally:
            return ''
        likely = tally.get('consistent', 0)
        if not likely:
            return ''
        return (f' · {likely} folder(s) look like a single person — '
                f'confirm to skip them next time')
    except Exception as e:      # noqa: BLE001 — a suggestion is never worth a failure
        logger.warning('bank %s: folder probe after the face pass failed: %s',
                       bank_id, e, exc_info=True)
        return ''


# --- the preflight (the probe, moved IN FRONT of the pass) ------------------
# WHY THIS EXISTS. Everything above was reachable only from the Subfolder panel
# or a 🔎 Scan folders button. The first thing a new user does is press 🚀 Launch
# all — so they never saw any of it, and paid the full pass on forty folders that
# each held one person. A saving nobody walks past is not a saving.
#
# So the sampling now runs where the decision is made: as the preamble of 👤
# Group by person, standalone or inside Launch all. Same probe, same verdicts,
# same ASSERTION at the end of it (nothing here invents a second kind of "this
# folder is one person" — the acceptance goes through assert_single_person, which
# is why ↩ Not one person after all still works on it).
#
# The safety rule of the module is unchanged and non-negotiable: it still never
# asserts by itself. What changed is that the confirmation is now ON THE ROAD the
# user is already travelling, pre-ticked, one click for all of it — instead of
# down a side street they had no reason to take.
def face_pass_cost(bank_id) -> int:
    """How many images 👤 Group by person would embed if it started right now:
    every non-rejected image no assertion already covers. This is the number the
    preflight is measured against, and it is computed exactly the way the pass
    computes its own total — so the comparison the UI prints is not a rhetorical
    one."""
    return (BankImage.query.filter_by(bank_id=bank_id)
            .filter(BankImage.status != 'reject',
                    or_(BankImage.face_cluster_origin.is_(None),
                        BankImage.face_cluster_origin != ASSERTED)).count())


def preflight_payload(user_id, bank_id) -> dict | None:
    """What the preflight would cost and what it already knows, BEFORE anything
    runs. The caller uses it to decide whether there is a question worth asking
    at all: on a bank with no subfolder (or one already fully declared) there is
    nothing to show, and showing a dialog anyway would be the detour this feature
    exists to remove."""
    banks = _svc()
    if not banks.get_bank(user_id, bank_id):
        return None
    from .face_similarity import is_available
    pending = scan_candidates(bank_id)
    covered = min(len(pending), MAX_PREFLIGHT_FOLDERS)
    return {
        # Without the extra there is no probe and no pass either; the caller
        # skips straight through and lets the pass report the missing install.
        'available': bool(is_available()),
        'sample_size': SAMPLE_SIZE,
        'min_images': MIN_PROBE_IMAGES,
        'candidates': len(pending),
        'covered': covered,
        # Folders the ceiling will NOT reach. Reported as a number the UI has to
        # print, not as silence that would read as "the rest are not one person".
        'left': len(pending) - covered,
        'sample_cost': covered * SAMPLE_SIZE,
        'full_cost': face_pass_cost(bank_id),
        # Fresh verdicts already on file (from an earlier preflight, a 🔎 Scan,
        # or the free probe at the end of a previous pass). They cost nothing to
        # show and they are the whole answer when no folder is left to sample.
        'known': [s for s in suggestions(bank_id) if not s['stale']],
        'asserted': sorted(asserted_subfolders(bank_id)),
    }


def start_preflight(app, user_id, bank_id):
    """Sample every unprobed folder as the preamble of the person pass."""
    return start_folder_scan(app, user_id, bank_id,
                             limit=MAX_PREFLIGHT_FOLDERS, kind='folder-preflight')


def accept_suggestions(user_id, bank_id, subfolders) -> dict:
    """Confirm the preflight's offers in ONE gesture.

    Each folder goes through ``assert_single_person`` — the same persisted,
    revocable, origin='asserted' rule a manual click writes. There is deliberately
    no second state: afterwards nothing distinguishes a folder accepted here from
    one declared by hand, which is what keeps revoke, re-scan adoption and the
    pass's skip working on both.

    A folder that cannot be asserted (emptied since the probe, say) is REPORTED,
    not swallowed: the caller has to be able to say "11 of the 12 you ticked"."""
    banks = _svc()
    if not banks.get_bank(user_id, bank_id):
        raise ValueError('bank not found')
    if not isinstance(subfolders, (list, tuple)):
        raise ValueError('subfolders must be a list')
    accepted, images, failed = [], 0, []
    for sub in subfolders:
        name = '' if sub is None else str(sub)
        try:
            out = assert_single_person(user_id, bank_id, name)
        except ValueError as e:
            failed.append({'subfolder': name, 'error': str(e)})
            continue
        accepted.append(out['subfolder'])
        images += out['images']
    return {'accepted': accepted, 'images': images, 'failed': failed}
