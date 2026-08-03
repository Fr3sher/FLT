""""Single person here" — folder-level person assertions on an image bank.

The assertion itself is pure DB work (no model, no subprocess), so most of this
is hermetic by construction. The two places that DO touch the embeddings child
(the full face pass and the ~15-image sample check) drive it through
``_drive_infer_subprocess``, monkeypatched here exactly as the other bank pass
tests do. Background jobs run inline under TESTING (see bank_jobs.start)."""
import json
import os
from collections import deque

from PIL import Image

from app.config import LOCAL_USER
from app.services import folder_person


# --- factories --------------------------------------------------------------
def _save(path, im):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    im.save(path, 'JPEG', quality=92) if path.lower().endswith('.jpg') else im.save(path)


def _flat(value=128, size=64):
    return Image.new('RGB', (size, size), (value, value, value))


def _mkbank(client, tmp_path, files, name='B'):
    src = tmp_path / 'src'
    for rel, im in files.items():
        _save(str(src / rel), im)
    r = client.post('/api/bank/create', json={'name': name, 'folder': str(src)})
    assert r.status_code == 200, r.get_json()
    return r.get_json()['id'], src


def _rows(app, bank_id):
    from app.models import BankImage
    with app.app_context():
        return {r.relpath.replace('\\', '/'): (r.face_cluster, r.face_cluster_origin)
                for r in BankImage.query.filter_by(bank_id=bank_id).all()}


def _fresh_job(kind):
    return {'kind': kind, 'done': 0, 'total': 0, 'error': None, 'cancelled': False,
            'finished': False, 'detail': None, '_touched': 0, '_cancel_hook': None,
            'pipeline': None}


_TREE = {os.path.join('anna', 'a1.jpg'): _flat(10),
         os.path.join('anna', 'a2.jpg'): _flat(20),
         os.path.join('anna', 'a3.jpg'): _flat(30),
         os.path.join('bob', 'b1.jpg'): _flat(40),
         'loose.jpg': _flat(50)}


# --- the assertion ----------------------------------------------------------
def test_assert_covers_the_whole_folder_with_no_inference(client, tmp_path, app,
                                                          monkeypatch):
    """One click = every image of the folder in one person group, immediately.
    The embeddings child is booby-trapped: if anything infers, the test fails."""
    bank_id, _src = _mkbank(client, tmp_path, _TREE)
    from app.services import image_bank_service as banks

    def _boom(*a, **k):     # noqa: ANN001 — any call at all is the failure
        raise AssertionError('the assertion must not run a single inference')

    monkeypatch.setattr(banks, '_drive_infer_subprocess', _boom)
    r = client.post(f'/api/bank/{bank_id}/folder-person', json={'subfolder': 'anna'})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()['images'] == 3
    rows = _rows(app, bank_id)
    assert rows['anna/a1.jpg'] == rows['anna/a2.jpg'] == rows['anna/a3.jpg']
    assert rows['anna/a1.jpg'][1] == 'asserted'
    # Neither the sibling folder nor the root file is touched.
    assert rows['bob/b1.jpg'] == (None, None)
    assert rows['loose.jpg'] == (None, None)


def test_root_is_an_assertable_folder_of_its_own(client, tmp_path, app):
    """'' is a real subfolder (the bank root) everywhere else in the bank, so it
    is one here too — and it must NOT swallow the nested files."""
    bank_id, _src = _mkbank(client, tmp_path, _TREE)
    r = client.post(f'/api/bank/{bank_id}/folder-person', json={'subfolder': ''})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()['images'] == 1
    rows = _rows(app, bank_id)
    assert rows['loose.jpg'][1] == 'asserted'
    assert rows['anna/a1.jpg'] == (None, None)


def test_assertion_survives_a_rescan_and_adopts_new_files(client, tmp_path, app):
    """The rule, not the stamp: a file dropped in the folder later joins the
    group the moment the folder sync sees it — no pass, no second click."""
    bank_id, src = _mkbank(client, tmp_path, _TREE)
    client.post(f'/api/bank/{bank_id}/folder-person', json={'subfolder': 'anna'})
    cid = _rows(app, bank_id)['anna/a1.jpg'][0]
    _save(str(src / 'anna' / 'a4.jpg'), _flat(77))
    _save(str(src / 'bob' / 'b2.jpg'), _flat(88))
    from app.services import image_bank_service as banks
    with app.app_context():
        out = banks.refresh_bank(LOCAL_USER, bank_id, force=True)
    assert out['added'] == 2
    rows = _rows(app, bank_id)
    assert rows['anna/a4.jpg'] == (cid, 'asserted')
    assert rows['bob/b2.jpg'] == (None, None)      # the batch is not stamped whole


def test_revoke_dissolves_the_group_but_spares_computed_ids(client, tmp_path, app):
    bank_id, _src = _mkbank(client, tmp_path, _TREE)
    client.post(f'/api/bank/{bank_id}/folder-person', json={'subfolder': 'anna'})
    # A row of the same folder whose cluster a real pass had computed earlier.
    from app.extensions import db
    from app.models import BankImage
    with app.app_context():
        row = (BankImage.query.filter_by(bank_id=bank_id)
               .filter(BankImage.relpath.contains('a3')).one())
        row.face_cluster, row.face_cluster_origin = 9, None
        db.session.commit()
    r = client.delete(f'/api/bank/{bank_id}/folder-person', json={'subfolder': 'anna'})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()['cleared'] == 2
    rows = _rows(app, bank_id)
    assert rows['anna/a1.jpg'] == (None, None)
    assert rows['anna/a3.jpg'] == (9, None)        # not ours to clear
    assert client.get(f'/api/bank/{bank_id}/folder-persons').get_json()['assertions'] == []


def test_revoke_reads_the_subfolder_from_the_query_string_too(client, tmp_path, app):
    """The browser's DELETE carries no body (the shared del() helper sends none),
    so the query-string path is the PRODUCTION one — and '' has to survive it:
    `?subfolder=` means the bank root, not "no subfolder given"."""
    bank_id, _src = _mkbank(client, tmp_path, _TREE)
    client.post(f'/api/bank/{bank_id}/folder-person', json={'subfolder': ''})
    r = client.delete(f'/api/bank/{bank_id}/folder-person?subfolder=')
    assert r.status_code == 200, r.get_json()
    assert r.get_json()['cleared'] == 1
    assert _rows(app, bank_id)['loose.jpg'] == (None, None)
    # And a request that names nothing at all is refused, never guessed.
    assert client.delete(f'/api/bank/{bank_id}/folder-person').status_code == 400


def test_revoking_a_folder_that_was_never_asserted_is_a_400(client, tmp_path):
    bank_id, _src = _mkbank(client, tmp_path, _TREE)
    r = client.delete(f'/api/bank/{bank_id}/folder-person', json={'subfolder': 'bob'})
    assert r.status_code == 400
    assert 'not asserted' in r.get_json()['error']


def test_asserting_an_empty_subfolder_is_refused(client, tmp_path):
    bank_id, _src = _mkbank(client, tmp_path, _TREE)
    r = client.post(f'/api/bank/{bank_id}/folder-person',
                    json={'subfolder': 'nobody-here'})
    assert r.status_code == 400
    assert 'no images' in r.get_json()['error']


def test_deleting_the_bank_takes_its_assertions(client, tmp_path, app):
    bank_id, _src = _mkbank(client, tmp_path, _TREE)
    client.post(f'/api/bank/{bank_id}/folder-person', json={'subfolder': 'anna'})
    assert client.delete(f'/api/bank/{bank_id}').status_code == 200
    from app.models import BankFolderPerson
    with app.app_context():
        assert BankFolderPerson.query.filter_by(bank_id=bank_id).count() == 0


# --- coexistence with the embeddings pass -----------------------------------
def test_face_pass_skips_asserted_images_and_never_reuses_their_id(
        client, tmp_path, app, monkeypatch):
    """THE saving, and the id-space contract in one test: the pass is not asked
    to embed the asserted folder at all, and the clusters it does compute are
    pushed above the asserted id instead of colliding with it."""
    bank_id, _src = _mkbank(client, tmp_path, _TREE)
    client.post(f'/api/bank/{bank_id}/folder-person', json={'subfolder': 'anna'})
    asserted_id = _rows(app, bank_id)['anna/a1.jpg'][0]
    from app.services import image_bank_service as banks
    monkeypatch.setattr(banks, '_resolve_face_device', lambda: ('cpu', False))
    seen = {}

    def fake_driver(job, python, script, payload, cache_path, rx, window):
        imgs = json.loads(payload)['images']
        seen['images'] = imgs
        return ({'ok': True,
                 'results': {p: {'state': 'scorable', 'det': 0.9} for p in imgs},
                 'clusters': {p: 1 for p in imgs}}, deque(), 0)

    monkeypatch.setattr(banks, '_drive_infer_subprocess', fake_driver)
    job = _fresh_job('faces')
    with app.app_context():
        banks._faces_job(bank_id)(job)
    # Not one of the three asserted files was handed to the child.
    assert seen['images'] and not any('anna' in p for p in seen['images'])
    assert len(seen['images']) == 2                # bob + the root file
    rows = _rows(app, bank_id)
    assert rows['anna/a1.jpg'] == (asserted_id, 'asserted')   # untouched
    assert rows['bob/b1.jpg'][0] == asserted_id + 1           # offset, no collision
    assert rows['bob/b1.jpg'][1] is None
    assert 'skipped (subfolder asserted as one person)' in (job['detail'] or '')


def test_face_pass_total_promises_only_what_it_will_embed(client, tmp_path, app,
                                                          monkeypatch):
    bank_id, _src = _mkbank(client, tmp_path, _TREE)
    client.post(f'/api/bank/{bank_id}/folder-person', json={'subfolder': 'anna'})
    from app.services import face_similarity, image_bank_service as banks
    monkeypatch.setattr(face_similarity, 'is_available', lambda: True)
    monkeypatch.setattr(banks, '_resolve_face_device', lambda: ('cpu', False))
    monkeypatch.setattr(banks, '_drive_infer_subprocess',
                        lambda *a, **k: ({'ok': True, 'results': {}, 'clusters': {}},
                                         deque(), 0))
    with app.app_context():
        job = banks.start_faces(app, LOCAL_USER, bank_id)
    assert job['total'] == 2       # 5 images, 3 of them asserted away


# --- the sample check -------------------------------------------------------
def _run_check(app, bank_id, subfolder, clusters_of, monkeypatch, states=None):
    from app.services import image_bank_service as banks
    monkeypatch.setattr(banks, '_resolve_face_device', lambda: ('cpu', False))
    seen = {}

    def fake_driver(job, python, script, payload, cache_path, rx, window):
        imgs = json.loads(payload)['images']
        seen['images'] = imgs
        seen['threshold'] = json.loads(payload)['threshold']
        res = {p: {'state': (states or {}).get(os.path.basename(p), 'scorable'),
                   'det': 0.9} for p in imgs}
        return ({'ok': True, 'results': res,
                 'clusters': clusters_of(imgs)}, deque(), 0)

    monkeypatch.setattr(banks, '_drive_infer_subprocess', fake_driver)
    job = _fresh_job('folder-check')
    with app.app_context():
        folder_person._sample_job(bank_id, subfolder)(job)
    return job, seen


def test_sample_check_says_consistent_and_costs_a_sample(client, tmp_path, app,
                                                         monkeypatch):
    files = {os.path.join('anna', f'a{i:03d}.jpg'): _flat(i) for i in range(60)}
    bank_id, _src = _mkbank(client, tmp_path, files)
    client.post(f'/api/bank/{bank_id}/folder-person', json={'subfolder': 'anna'})
    job, seen = _run_check(app, bank_id, 'anna',
                           lambda imgs: {p: 1 for p in imgs}, monkeypatch)
    # 60 images in the folder, 15 embedded — that ratio IS the feature.
    assert len(seen['images']) == folder_person.SAMPLE_SIZE
    assert job['detail'] == 'sample consistent (15/15 same person)'
    data = client.get(f'/api/bank/{bank_id}/folder-persons').get_json()
    sample = data['assertions'][0]['sample']
    assert sample['verdict'] == 'consistent'
    assert sample['faces'] == 1 and sample['sample'] == 15


def test_sample_check_reuses_the_clustering_threshold(client, tmp_path, app,
                                                      monkeypatch):
    """One truth about "same person" in this app: the check must compare at the
    bank's own face_threshold, never at a second number of its own."""
    bank_id, _src = _mkbank(client, tmp_path, _TREE)
    client.post(f'/api/bank/{bank_id}/folder-person', json={'subfolder': 'anna'})
    _job, seen = _run_check(app, bank_id, 'anna',
                            lambda imgs: {p: 1 for p in imgs}, monkeypatch)
    from app.services import image_bank_service as banks
    with app.app_context():
        assert seen['threshold'] == banks.thresholds()['face_threshold']


def test_sample_check_warns_on_two_faces_without_touching_the_assertion(
        client, tmp_path, app, monkeypatch):
    bank_id, _src = _mkbank(client, tmp_path, _TREE)
    client.post(f'/api/bank/{bank_id}/folder-person', json={'subfolder': 'anna'})
    before = _rows(app, bank_id)['anna/a1.jpg']
    job, _seen = _run_check(
        app, bank_id, 'anna',
        lambda imgs: {p: (1 if i else 2) for i, p in enumerate(imgs)}, monkeypatch)
    assert job['detail'] == '2 different faces in the sample — check this folder'
    # The warning INFORMS. The user's folder, the user's call.
    assert _rows(app, bank_id)['anna/a1.jpg'] == before
    data = client.get(f'/api/bank/{bank_id}/folder-persons').get_json()
    assert data['assertions'][0]['sample']['verdict'] == 'mixed'


def test_sample_check_is_honest_when_it_saw_no_face(client, tmp_path, app,
                                                    monkeypatch):
    bank_id, _src = _mkbank(client, tmp_path, _TREE)
    client.post(f'/api/bank/{bank_id}/folder-person', json={'subfolder': 'anna'})
    job, _seen = _run_check(app, bank_id, 'anna', lambda imgs: {}, monkeypatch,
                            states={'a1.jpg': 'no_face', 'a2.jpg': 'no_face',
                                    'a3.jpg': 'unreadable'})
    assert 'nothing to compare' in job['detail']
    data = client.get(f'/api/bank/{bank_id}/folder-persons').get_json()
    entry = data['assertions'][0]
    assert entry['sample']['verdict'] == 'inconclusive'
    # Guard-rail: what the machinery could not read is LISTED, never dropped.
    assert {t['state'] for t in entry['to_check']} == {'no_face', 'unreadable'}
    assert len(entry['to_check']) == 3


def test_sample_check_needs_an_assertion(client, tmp_path, app):
    bank_id, _src = _mkbank(client, tmp_path, _TREE)
    r = client.post(f'/api/bank/{bank_id}/folder-person/check',
                    json={'subfolder': 'anna'})
    assert r.status_code == 400
    assert 'not asserted' in r.get_json()['error']


def test_the_saving_is_counted_in_inferences_not_claimed(client, tmp_path, app,
                                                          monkeypatch):
    """The feature's whole promise is a NUMBER, so it is measured here rather
    than asserted in a comment: on a bank shaped like a real scrape (six folders
    of one person each, plus a mixed one), the embeddings child is handed only
    the images no assertion covers."""
    files = {}
    for f in range(6):
        for i in range(50):
            files[os.path.join(f'person{f}', f'{i:03d}.jpg')] = _flat(i)
    for i in range(40):
        files[os.path.join('mixed', f'{i:03d}.jpg')] = _flat(i)
    bank_id, _src = _mkbank(client, tmp_path, files)       # 340 images
    for f in range(6):
        r = client.post(f'/api/bank/{bank_id}/folder-person',
                        json={'subfolder': f'person{f}'})
        assert r.status_code == 200, r.get_json()
    from app.services import image_bank_service as banks
    monkeypatch.setattr(banks, '_resolve_face_device', lambda: ('cpu', False))
    seen = {}

    def fake_driver(job, python, script, payload, cache_path, rx, window):
        imgs = json.loads(payload)['images']
        seen['n'] = len(imgs)
        return ({'ok': True,
                 'results': {p: {'state': 'scorable', 'det': 0.9} for p in imgs},
                 'clusters': {p: 1 for p in imgs}}, deque(), 0)

    monkeypatch.setattr(banks, '_drive_infer_subprocess', fake_driver)
    with app.app_context():
        banks._faces_job(bank_id)(_fresh_job('faces'))
    assert seen['n'] == 40                 # 340 images, 300 asserted away
    # And every one of those 300 still has a person id — the group is real, it
    # was simply not paid for.
    from app.models import BankImage
    with app.app_context():
        grouped = (BankImage.query.filter_by(bank_id=bank_id)
                   .filter(BankImage.face_cluster_origin == 'asserted').count())
    assert grouped == 300
    # Six declared folders = six distinct person ids, not one merged blob.
    rows = _rows(app, bank_id)
    ids = {rows[f'person{f}/000.jpg'][0] for f in range(6)}
    assert len(ids) == 6


def test_a_stratified_sample_spans_the_whole_folder():
    """The first 15 files of a scraped folder are one shoot; a second person
    appearing halfway through must still be reachable."""
    picked = folder_person._stratified(list(range(100)), k=10)
    assert len(picked) == 10
    assert picked[0] == 0 and picked[-1] >= 80      # reaches the far end
    assert len(set(picked)) == 10                   # no image sampled twice
    assert folder_person._stratified([1, 2, 3], k=10) == [1, 2, 3]
