"""The ⚖ LoRA bench scratch dataset must stay invisible — one test per surface.

This is the real risk of the bench feature. Missing ONE listing surfaces a
phantom dataset in the user's library, or — worse — ships it inside a backup
they restore months later, when nobody will connect the two.

The surfaces below were found by auditing every site that queries `FaceDataset`,
enumerates the datasets root, exports, backs up or counts. Most of them turned
out to be fed by ONE query (`face_dataset_service.list_datasets`), which is why
the gate lives there; they are still tested individually, because "it goes
through the choke-point today" is a fact about today's code.

Two of these tests are NOT about hiding:
  * the boot orphan sweep must not eat bench cells (the inverse trap);
  * a backup/restore round trip must leave the bench able to restart from
    nothing — the scratch row is deliberately excluded from backups, so a
    restored install has none, and the code must recreate it rather than assume.
"""
import io
import json
import os
import zipfile

import pytest
from PIL import Image


LOCAL = 'local'


def _png(color=(30, 90, 200)):
    buf = io.BytesIO()
    Image.new('RGB', (32, 32), color).save(buf, 'PNG')
    return buf.getvalue()


def _real_dataset(svc, name='Alice', trigger='alice', with_image=True):
    from app.models import FaceDatasetImage
    ds = svc.create_dataset(LOCAL, name, trigger)
    if with_image:
        d = svc._dataset_dir(ds.id)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, 'img1.png'), 'wb') as fh:
            fh.write(_png())
        svc.db.session.add(FaceDatasetImage(dataset_id=ds.id, filename='img1.png',
                                            status='keep', caption='a portrait'))
        svc.db.session.commit()
    return ds


def _scratch(trigger='downloaded'):
    """The bench sandbox, with one finished cell on it — a scratch row with no
    cells could stay hidden by accident."""
    from app.models import LoraTestImage
    from app.services import lora_bench as bench
    from app.extensions import db
    ds = bench.ensure_bench_dataset(LOCAL, trigger)
    db.session.add(LoraTestImage(dataset_id=ds.id, checkpoint='krea\\civitai_thing.safetensors',
                                 strength=0.8, seed=7, run_seed=7, run_id='b' * 32,
                                 status='done', filename='cell.png', prompt='a bench prompt'))
    db.session.commit()
    return ds


# ---------------------------------------------------------------------------
# Surface 1 — the library
# ---------------------------------------------------------------------------

def test_scratch_row_is_absent_from_the_library(app, client):
    from app.services import face_dataset_service as svc
    with app.app_context():
        real_id = _real_dataset(svc).id
        hidden_id = _scratch().id
        assert [d.id for d in svc.list_datasets(LOCAL)] == [real_id]

    payload = client.get('/api/dataset/list').get_json()
    ids = [d['id'] for d in payload['datasets']]
    assert ids == [real_id]
    assert hidden_id not in ids
    # The NAME must not travel either — it is what would show up in a tile.
    from app.services.lora_bench import BENCH_DATASET_NAME
    assert BENCH_DATASET_NAME not in json.dumps(payload)


def test_dataset_list_endpoint_feeds_every_dropdown_that_picks_a_dataset(app, client):
    """`/api/dataset/list` is not only the library: the Bank's "promote into a
    dataset" select, the "caption elsewhere" target list and the bank-folder
    collision notice all read this one endpoint. Pinned separately from the
    library test because they are separate screens that would each show a
    phantom entry."""
    from app.services import face_dataset_service as svc
    with app.app_context():
        _real_dataset(svc, 'Bob', 'bob')
        _scratch()
    entries = client.get('/api/dataset/list').get_json()['datasets']
    assert [e['name'] for e in entries] == ['Bob']


# ---------------------------------------------------------------------------
# Surface 2 — the counts next to the library
# ---------------------------------------------------------------------------

def test_scratch_row_is_absent_from_dataset_list_stats(app):
    from app.services import face_dataset_service as svc
    with app.app_context():
        real = _real_dataset(svc)
        hidden = _scratch()
        stats = svc.dataset_list_stats(LOCAL)
        assert real.id in stats
        assert hidden.id not in stats


# ---------------------------------------------------------------------------
# Surface 3 — the full backup (build AND restore)
# ---------------------------------------------------------------------------

def test_scratch_row_never_enters_a_full_backup(app, tmp_path):
    from app.services import face_dataset_service as svc
    from app.services import full_backup as fb
    with app.app_context():
        _real_dataset(svc, 'Alice', 'alice')
        _scratch()
        out = str(tmp_path / 'master.zip')
        result = fb.build_full_backup(LOCAL, out, check_disk=False)

    # The COUNT the user is shown, the per-dataset zips, and the manifest.
    assert result['datasets_total'] == 1 and result['datasets_backed_up'] == 1
    with zipfile.ZipFile(out) as z:
        entries = [n for n in z.namelist()
                   if n.startswith('datasets/') and n.endswith('.zip')]
        assert len(entries) == 1
        manifest = json.loads(z.read('manifest.json'))
        assert [d['name'] for d in manifest['datasets']] == ['Alice']
        assert 'scratch' not in json.dumps(manifest).lower()


def test_backup_restore_round_trip_leaves_the_bench_able_to_restart(app, tmp_path):
    """The scenario that would break SILENTLY.

    Bench history is test data and is deliberately left out of backups. So a
    restored install has NO scratch row — and if any bench code assumed one
    existed, the page would break weeks after a restore nobody remembers.

    Here: back up, wipe the database the way a fresh install has it, restore,
    run the boot orphan sweep, and check that (a) nothing else was lost, (b) the
    scratch row is genuinely gone, (c) the bench recreates it by itself and
    works.
    """
    from app import _cleanup_orphaned_lora_test_images
    from app.extensions import db
    from app.models import FaceDataset, LoraTestImage
    from app.services import face_dataset_service as svc
    from app.services import full_backup as fb
    from app.services import lora_bench as bench

    with app.app_context():
        _real_dataset(svc, 'Alice', 'alice')
        _scratch()
        out = str(tmp_path / 'master.zip')
        fb.build_full_backup(LOCAL, out, check_disk=False)

        # A fresh install: no rows AND no dataset folders. (Restoring on top of a
        # live database is covered by test_full_backup; the empty case is what a
        # user actually does after reinstalling.)
        import shutil
        from app import config as cfg
        LoraTestImage.query.delete()
        FaceDataset.query.delete()
        db.session.commit()
        shutil.rmtree(cfg.dataset_images_root(), ignore_errors=True)

        with open(out, 'rb') as fh:
            res = fb.restore_full_backup(LOCAL, fh)
        assert res['restored'] == 1

        # (a)+(b): the user's dataset came back, the scratch row did not, and the
        # boot sweep — which deletes lora_test_image rows with no parent — has
        # nothing to destroy because the cells left with their dataset.
        assert [d.name for d in svc.list_datasets(LOCAL)] == ['Alice']
        assert bench.get_bench_dataset(LOCAL) is None
        before = FaceDataset.query.count()
        _cleanup_orphaned_lora_test_images()
        assert FaceDataset.query.count() == before
        assert LoraTestImage.query.count() == 0

        # (c) the bench restarts from nothing.
        payload = bench.bench_payload(LOCAL)
        assert payload['dataset_id'] is None and payload['runs'] == []
        again = bench.ensure_bench_dataset(LOCAL, 'other')
        assert again is not None and again.internal == 'bench'
        assert [d.name for d in svc.list_datasets(LOCAL)] == ['Alice']


# ---------------------------------------------------------------------------
# Surface 4 — the inverse trap: the boot sweep must not EAT bench cells
# ---------------------------------------------------------------------------

def test_boot_orphan_sweep_keeps_bench_cells(app):
    """`_cleanup_orphaned_lora_test_images` runs at EVERY boot and deletes any
    `lora_test_image` without a `face_dataset` parent. The scratch row is that
    parent, which is precisely why the bench never deletes it — dropping the row
    to "clear history" would arm this sweep against the cells still finishing."""
    from app import _cleanup_orphaned_lora_test_images
    from app.models import LoraTestImage
    with app.app_context():
        ds = _scratch()
        assert LoraTestImage.query.filter_by(dataset_id=ds.id).count() == 1
        _cleanup_orphaned_lora_test_images()
        assert LoraTestImage.query.filter_by(dataset_id=ds.id).count() == 1


def test_clearing_bench_history_keeps_the_scratch_row(app):
    from app.models import LoraTestImage
    from app.services import lora_bench as bench
    with app.app_context():
        ds = _scratch()
        assert bench.clear_bench_history(LOCAL) == 1
        assert LoraTestImage.query.filter_by(dataset_id=ds.id).count() == 0
        assert bench.get_bench_dataset(LOCAL) is not None   # row survives


# ---------------------------------------------------------------------------
# Surface 5 — the Test Studio's own dataset enumerations
# ---------------------------------------------------------------------------

def test_scratch_row_is_absent_from_the_studio_checkpoint_picker(app, monkeypatch):
    """`/api/studio/checkpoints` groups its entries BY DATASET NAME — the leak
    guaranteed to happen, since benching is exactly what puts a checkpoint on
    the scratch row."""
    from app.services import face_dataset_service as svc
    from app.services import lora_test_studio as lts
    with app.app_context():
        _real_dataset(svc, 'Alice', 'alice')
        _scratch(trigger='alice')          # same trigger → same checkpoints match
        monkeypatch.setattr(lts, '_pool_for_family',
                            lambda fam: ([{'filename': 'z image\\alice-500.safetensors',
                                           'displayName': 'alice-500'}]
                                         if fam == 'zimage' else []))
        names = {e['dataset_name'] for e in lts.list_all_testable_checkpoints(LOCAL)}
        assert names == {'Alice'}


def test_bench_prompts_stay_out_of_the_studio_menu_but_delete_everywhere(app, monkeypatch):
    """Read excludes the sandbox, cleanup does not. An exclusion that is right
    for display is almost never right for deletion — deleting a prompt
    "everywhere" while skipping the sandbox would leave its cells and files."""
    from app.models import LoraTestImage
    from app.services import face_dataset_service as svc
    from app.services import lora_test_studio as lts
    from app.extensions import db
    with app.app_context():
        real = _real_dataset(svc, 'Alice', 'alice')
        scratch = _scratch()
        db.session.add(LoraTestImage(dataset_id=real.id, checkpoint='z image\\a-1.safetensors',
                                     strength=1.0, seed=1, run_seed=1, run_id='a' * 32,
                                     status='done', filename='r.png', prompt='a bench prompt'))
        db.session.commit()

        prompts = {p['prompt'] for p in lts.user_recent_prompts(LOCAL)}
        assert prompts == {'a bench prompt'}
        # …and the one it kept belongs to the REAL dataset, not the sandbox.
        thumbs = {p['thumb_dataset_id'] for p in lts.user_recent_prompts(LOCAL)}
        assert thumbs == {real.id}

        lts.delete_prompt_everywhere(LOCAL, 'a bench prompt')
        assert LoraTestImage.query.filter_by(dataset_id=scratch.id).count() == 0
        assert LoraTestImage.query.filter_by(dataset_id=real.id).count() == 0


def test_scratch_row_cannot_raise_a_phantom_training_collision(app):
    """`find_run_collision` enumerates the user's OTHER datasets to refuse two
    runs that would share an ai-toolkit folder. The sandbox borrows the trigger
    of the LoRA under test, so benching a file named after your own dataset used
    to make that dataset untrainable — blocked by a collision with a dataset the
    user cannot even see."""
    from app.services import face_dataset_service as svc
    from app.services import lora_training as lt
    with app.app_context():
        real = _real_dataset(svc, 'Alice', 'alice', with_image=False)
        _scratch(trigger='alice')          # same trigger → same run folder name
        assert lt.find_run_collision(LOCAL, real.id) is None


# ---------------------------------------------------------------------------
# Surface N+1 — the pattern guard
# ---------------------------------------------------------------------------

def test_internal_dataset_filter_guard():
    """Every query that ENUMERATES datasets for a user must decide about
    internal rows — filter them out, or say in a comment why it keeps them.

    This is a HEURISTIC, and it is worth saying exactly what it can and cannot
    do. It catches the shape that already leaked: a literal
    `FaceDataset.query.filter…(user_id…)` or `db.session.query(FaceDataset.id)`
    that is not narrowed to one id. It CANNOT catch a query built dynamically,
    one that reaches the table through a join or raw SQL, one that goes through
    another model, or a listing added in a different table entirely. A green run
    means "the known pattern has not come back" — never "no leak is possible".
    """
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / 'app'
    starts = re.compile(r'FaceDataset\.query\s*\.\s*filter(?:_by)?\(|'
                        r'db\.session\.query\(\s*FaceDataset\.id\s*\)')
    # Narrowed to ONE dataset → it is a lookup, not a listing.
    id_scoped = re.compile(r'FaceDataset\.id\s*(?:==|\.in_)|(?<![a-z_])id\s*=\s*(?!=)')
    offenders = []
    for path in sorted(root.rglob('*.py')):
        src = path.read_text(encoding='utf-8')
        lines = src.splitlines()
        for m in starts.finditer(src):
            line_no = src.count('\n', 0, m.start()) + 1
            body = '\n'.join(lines[line_no - 1:line_no + 7])
            before = '\n'.join(lines[max(0, line_no - 6):line_no - 1])
            if 'user_id' not in body:
                continue                       # not scoped to a user: not a listing
            if id_scoped.search(body):
                continue                       # resolves one dataset
            if 'internal' in body:
                continue                       # decided: filtered
            if 'lds-allow-internal-datasets' in before or 'lds-allow-internal-datasets' in body:
                continue                       # decided: kept, with a reason
            offenders.append(f'{path.relative_to(root.parent)}:{line_no}')
    assert not offenders, (
        'these queries enumerate a user\'s datasets without deciding about internal '
        'scratch rows — add `.filter(FaceDataset.internal.is_(None))`, or a '
        '`lds-allow-internal-datasets:` comment saying why they must be kept:\n  '
        + '\n  '.join(offenders))


def test_the_guard_would_actually_catch_a_regression(tmp_path):
    """A guard nobody has seen fail is a guard nobody can trust. Same predicate,
    run against a snippet that reintroduces the leak."""
    import re
    starts = re.compile(r'FaceDataset\.query\s*\.\s*filter(?:_by)?\(|'
                        r'db\.session\.query\(\s*FaceDataset\.id\s*\)')
    id_scoped = re.compile(r'FaceDataset\.id\s*(?:==|\.in_)|(?<![a-z_])id\s*=\s*(?!=)')

    def flags(src):
        lines = src.splitlines()
        for m in starts.finditer(src):
            line_no = src.count('\n', 0, m.start()) + 1
            body = '\n'.join(lines[line_no - 1:line_no + 7])
            if 'user_id' not in body or id_scoped.search(body) or 'internal' in body:
                continue
            if 'lds-allow-internal-datasets' in body:
                continue
            return True
        return False

    assert flags('rows = FaceDataset.query.filter_by(user_id=str(user_id)).all()')
    assert not flags('rows = (FaceDataset.query.filter_by(user_id=str(user_id))\n'
                     '        .filter(FaceDataset.internal.is_(None)).all())')
    assert not flags('ds = FaceDataset.query.filter_by(id=did, user_id=uid).first()')
