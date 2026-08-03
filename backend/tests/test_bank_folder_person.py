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
        req = json.loads(payload)
        imgs = req['images']
        # EVERY call is recorded, not the last one: the pass now chains a folder
        # probe behind itself, and a fake that only remembers the newest call
        # would silently measure the probe and call it the pass.
        seen.setdefault('calls', []).append(len(imgs))
        return ({'ok': True,
                 'results': {p: {'state': 'scorable', 'det': 0.9} for p in imgs},
                 'clusters': {p: 1 for p in imgs},
                 'group_clusters': {g['name']: {p: 1 for p in g['images']}
                                    for g in (req.get('groups') or [])}},
                deque(), 0)

    monkeypatch.setattr(banks, '_drive_infer_subprocess', fake_driver)
    with app.app_context():
        banks._faces_job(bank_id)(_fresh_job('faces'))
    assert seen['calls'][0] == 40          # 340 images, 300 asserted away
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


# --- automatic suggestion (probe) -------------------------------------------
def _big_tree(folders=3, per=20):
    files = {}
    for f in range(folders):
        for i in range(per):
            files[os.path.join(f'model{f}', f'{i:03d}.jpg')] = _flat(i)
    return files


def _probe_driver(seen, clusters_of):
    def fake_driver(job, python, script, payload, cache_path, rx, window):
        req = json.loads(payload)
        imgs = req['images']
        seen.setdefault('calls', []).append(req)
        return ({'ok': True,
                 'results': {p: {'state': 'scorable', 'det': 0.9} for p in imgs},
                 'group_clusters': {g['name']: clusters_of(g['name'], g['images'])
                                    for g in (req.get('groups') or [])}},
                deque(), 0)
    return fake_driver


def test_the_probe_suggests_but_never_groups_a_single_image(client, tmp_path, app,
                                                            monkeypatch):
    """The whole safety property in one test: a folder the app believes is one
    person is OFFERED, and until the user clicks, not one image has moved."""
    bank_id, _src = _mkbank(client, tmp_path, _big_tree())
    from app.services import face_similarity, image_bank_service as banks
    monkeypatch.setattr(face_similarity, 'is_available', lambda: True)
    monkeypatch.setattr(banks, '_resolve_face_device', lambda: ('cpu', False))
    seen = {}
    monkeypatch.setattr(banks, '_drive_infer_subprocess',
                        _probe_driver(seen, lambda n, imgs: {p: 1 for p in imgs}))
    r = client.post(f'/api/bank/{bank_id}/folder-scan')
    assert r.status_code == 202, r.get_json()

    data = client.get(f'/api/bank/{bank_id}/folder-persons').get_json()
    assert data['assertions'] == []                    # nothing was declared
    assert {s['subfolder'] for s in data['suggestions']} == {'model0', 'model1', 'model2'}
    assert all(s['verdict'] == 'consistent' for s in data['suggestions'])
    # NOT ONE image was grouped. This is the line that must never go green by
    # accident: a suggestion that grouped anything would be an assertion.
    assert all(v == (None, None) for v in _rows(app, bank_id).values())


def test_one_child_call_covers_every_folder_and_clusters_them_apart(
        client, tmp_path, app, monkeypatch):
    """Forty folders must not be forty subprocesses — and the folders must be
    clustered SEPARATELY, or two folders merging into one cluster would read as
    'consistent' when it means the opposite."""
    bank_id, _src = _mkbank(client, tmp_path, _big_tree(folders=4))
    from app.services import face_similarity, image_bank_service as banks
    monkeypatch.setattr(face_similarity, 'is_available', lambda: True)
    monkeypatch.setattr(banks, '_resolve_face_device', lambda: ('cpu', False))
    seen = {}
    monkeypatch.setattr(banks, '_drive_infer_subprocess',
                        _probe_driver(seen, lambda n, imgs: {p: 1 for p in imgs}))
    client.post(f'/api/bank/{bank_id}/folder-scan')
    assert len(seen['calls']) == 1                     # ONE subprocess
    req = seen['calls'][0]
    assert {g['name'] for g in req['groups']} == {'model0', 'model1', 'model2', 'model3'}
    assert all(len(g['images']) == folder_person.SAMPLE_SIZE for g in req['groups'])
    # And the child is asked to cluster per group, at the clustering threshold.
    with app.app_context():
        assert req['threshold'] == banks.thresholds()['face_threshold']


def test_a_mixed_folder_is_reported_as_such_and_never_suggested_as_one(
        client, tmp_path, app, monkeypatch):
    bank_id, _src = _mkbank(client, tmp_path, _big_tree(folders=2))
    from app.services import face_similarity, image_bank_service as banks
    monkeypatch.setattr(face_similarity, 'is_available', lambda: True)
    monkeypatch.setattr(banks, '_resolve_face_device', lambda: ('cpu', False))

    def clusters_of(name, imgs):
        if name == 'model1':      # two people in this one
            return {p: (1 if i % 2 else 2) for i, p in enumerate(imgs)}
        return {p: 1 for p in imgs}

    monkeypatch.setattr(banks, '_drive_infer_subprocess',
                        _probe_driver({}, clusters_of))
    client.post(f'/api/bank/{bank_id}/folder-scan')
    got = {s['subfolder']: s['verdict'] for s in
           client.get(f'/api/bank/{bank_id}/folder-persons').get_json()['suggestions']}
    assert got == {'model0': 'consistent', 'model1': 'mixed'}


def test_a_probe_expires_when_the_folder_changes(client, tmp_path, app, monkeypatch):
    """A verdict describes the folder it sampled. Add images and it stops being
    an answer about the folder in front of you — so it is marked stale rather
    than quietly kept."""
    bank_id, src = _mkbank(client, tmp_path, _big_tree(folders=1))
    from app.services import face_similarity, image_bank_service as banks
    monkeypatch.setattr(face_similarity, 'is_available', lambda: True)
    monkeypatch.setattr(banks, '_resolve_face_device', lambda: ('cpu', False))
    monkeypatch.setattr(banks, '_drive_infer_subprocess',
                        _probe_driver({}, lambda n, imgs: {p: 1 for p in imgs}))
    client.post(f'/api/bank/{bank_id}/folder-scan')
    assert client.get(f'/api/bank/{bank_id}/folder-persons') \
        .get_json()['suggestions'][0]['stale'] is False
    _save(str(src / 'model0' / 'new.jpg'), _flat(9))
    with app.app_context():
        banks.refresh_bank(LOCAL_USER, bank_id, force=True)
    fresh = client.get(f'/api/bank/{bank_id}/folder-persons').get_json()
    assert fresh['suggestions'][0]['stale'] is True
    # And a stale folder is offered to the scan again rather than left behind.
    with app.app_context():
        assert 'model0' in [n for n, _c in folder_person.scan_candidates(bank_id)]


def test_confirming_a_suggestion_removes_it(client, tmp_path, app, monkeypatch):
    bank_id, _src = _mkbank(client, tmp_path, _big_tree(folders=2))
    from app.services import face_similarity, image_bank_service as banks
    monkeypatch.setattr(face_similarity, 'is_available', lambda: True)
    monkeypatch.setattr(banks, '_resolve_face_device', lambda: ('cpu', False))
    monkeypatch.setattr(banks, '_drive_infer_subprocess',
                        _probe_driver({}, lambda n, imgs: {p: 1 for p in imgs}))
    client.post(f'/api/bank/{bank_id}/folder-scan')
    client.post(f'/api/bank/{bank_id}/folder-person', json={'subfolder': 'model0'})
    data = client.get(f'/api/bank/{bank_id}/folder-persons').get_json()
    assert [s['subfolder'] for s in data['suggestions']] == ['model1']
    assert [a['subfolder'] for a in data['assertions']] == ['model0']


def test_tiny_and_asserted_folders_are_not_probed(client, tmp_path, app, monkeypatch):
    """Two folders a suggestion would only add noise to: one already declared,
    one too small for fifteen images to mean anything."""
    files = _big_tree(folders=1)
    files[os.path.join('scraps', 'a.jpg')] = _flat(1)
    files[os.path.join('scraps', 'b.jpg')] = _flat(2)
    bank_id, _src = _mkbank(client, tmp_path, files)
    client.post(f'/api/bank/{bank_id}/folder-person', json={'subfolder': 'model0'})
    with app.app_context():
        assert folder_person.scan_candidates(bank_id) == []


def test_the_scan_states_what_it_did_not_reach(client, tmp_path, app, monkeypatch):
    """A ceiling that says nothing would read as 'the rest are not one person'."""
    from app.services import folder_person as fp
    monkeypatch.setattr(fp, 'MAX_SCAN_FOLDERS', 2)
    bank_id, _src = _mkbank(client, tmp_path, _big_tree(folders=5))
    from app.services import face_similarity, image_bank_service as banks
    monkeypatch.setattr(face_similarity, 'is_available', lambda: True)
    monkeypatch.setattr(banks, '_resolve_face_device', lambda: ('cpu', False))
    monkeypatch.setattr(banks, '_drive_infer_subprocess',
                        _probe_driver({}, lambda n, imgs: {p: 1 for p in imgs}))
    job = _fresh_job('folder-scan')
    with app.app_context():
        fp._folder_scan_job(bank_id)(job)
    assert '2 folder(s) sampled' in job['detail']
    assert '3 folder(s) not reached' in job['detail']


def test_the_face_pass_probes_for_free_and_says_what_it_found(
        client, tmp_path, app, monkeypatch):
    """The automatic trigger. It runs inside the face pass because that is the
    one moment the embeddings are already cached."""
    bank_id, _src = _mkbank(client, tmp_path, _big_tree(folders=2))
    from app.services import image_bank_service as banks
    monkeypatch.setattr(banks, '_resolve_face_device', lambda: ('cpu', False))
    seen = {}
    monkeypatch.setattr(banks, '_drive_infer_subprocess',
                        _probe_driver(seen, lambda n, imgs: {p: 1 for p in imgs}))
    job = _fresh_job('faces')
    with app.app_context():
        banks._faces_job(bank_id)(job)
    assert '2 folder(s) look like a single person' in job['detail']
    # Two calls: the pass, then the probe — and the probe reuses the pass's OWN
    # cache file, which is what makes it free.
    assert len(seen['calls']) == 2
    assert seen['calls'][1]['cache'] == seen['calls'][0]['cache']
    data = client.get(f'/api/bank/{bank_id}/folder-persons').get_json()
    assert len(data['suggestions']) == 2
    assert all(v[1] is None for v in _rows(app, bank_id).values())   # still nothing asserted


def test_a_failing_probe_never_turns_a_finished_face_pass_red(
        client, tmp_path, app, monkeypatch):
    bank_id, _src = _mkbank(client, tmp_path, _big_tree(folders=1))
    from app.services import folder_person as fp, image_bank_service as banks
    monkeypatch.setattr(banks, '_resolve_face_device', lambda: ('cpu', False))

    def fake_driver(job, python, script, payload, cache_path, rx, window):
        imgs = json.loads(payload)['images']
        return ({'ok': True,
                 'results': {p: {'state': 'scorable', 'det': 0.9} for p in imgs},
                 'clusters': {p: 1 for p in imgs}}, deque(), 0)

    monkeypatch.setattr(banks, '_drive_infer_subprocess', fake_driver)
    monkeypatch.setattr(fp, '_run_probe',
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError('boom')))
    job = _fresh_job('faces')
    with app.app_context():
        banks._faces_job(bank_id)(job)
    assert job['error'] is None
    assert 'person cluster' in job['detail']       # the pass still reports itself
    assert 'boom' not in (job['detail'] or '')


def test_the_angle_lane_never_probes(client, tmp_path, app, monkeypatch):
    """⤢ Angles re-runs on rows that already have a face_state. Probing there
    would re-suggest folders on every backfill, for nothing new."""
    bank_id, _src = _mkbank(client, tmp_path, _big_tree(folders=1))
    from app.services import image_bank_service as banks
    from app.extensions import db as _db
    from app.models import BankImage
    monkeypatch.setattr(banks, '_resolve_face_device', lambda: ('cpu', False))
    with app.app_context():
        for r in BankImage.query.filter_by(bank_id=bank_id).all():
            r.face_state = 'scorable'
        _db.session.commit()
    seen = {}
    monkeypatch.setattr(banks, '_drive_infer_subprocess',
                        _probe_driver(seen, lambda n, imgs: {p: 1 for p in imgs}))
    with app.app_context():
        banks._faces_job(bank_id, angles_only=True)(_fresh_job('angles'))
    assert len(seen['calls']) == 1
    assert not seen['calls'][0].get('groups')


def test_a_stratified_sample_spans_the_whole_folder():
    """The first 15 files of a scraped folder are one shoot; a second person
    appearing halfway through must still be reachable."""
    picked = folder_person._stratified(list(range(100)), k=10)
    assert len(picked) == 10
    assert picked[0] == 0 and picked[-1] >= 80      # reaches the far end
    assert len(set(picked)) == 10                   # no image sampled twice
    assert folder_person._stratified([1, 2, 3], k=10) == [1, 2, 3]
