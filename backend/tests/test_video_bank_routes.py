"""🎬 The video lane's HTTP surface — it must feel like the image lane's.

A user does not know there are two services behind the app, and the seam is not
supposed to be visible. So these tests pin the shapes the image bank already
established, on the video routes: 202 for a pass that runs in the background, 409
carrying `busy_kind` when the bank is occupied, 404 for an unknown bank, 400 for a
refusal the user can fix, 503 for a missing tool.

Two of them are not about symmetry at all:

  * the blueprints have to be REGISTERED. `routes/__init__` imports them by name
    from a tuple, and a module that is written but not listed there answers 404
    everywhere while looking perfectly correct in the diff;
  * editing a caption has to rewrite the .txt on disk. The trainer never reads our
    database — it reads the sidecar next to the .mp4. A caption saved to one and
    not the other is a dataset that trains on the previous text while the UI shows
    the new one, with nothing anywhere to reveal it.

No ffmpeg, no PyAV, no torch: the four media seams are monkeypatched.
"""
import os

import pytest

from app.services import video_bank_service as svc


@pytest.fixture()
def seams(monkeypatch):
    calls = []

    def _run(args):
        calls.append(list(args))
        with open(args[-1], 'wb') as fh:
            fh.write(b'\x00')
        return 0, ''

    monkeypatch.setattr(svc, '_probe_file', lambda _p: {
        'duration_s': 120.0, 'fps_native': 30.0, 'width': 1920, 'height': 1080,
        'codec': 'h264', 'probe_state': 'ok', 'file_size': 4096})
    monkeypatch.setattr(svc, '_detect_shots', lambda _p, _f=None: [
        {'start_s': 0.0, 'end_s': 8.0, 'start_frame': 0, 'end_frame': 240},
        {'start_s': 41.25, 'end_s': 50.0, 'start_frame': 1237, 'end_frame': 1500}])
    monkeypatch.setattr(svc, '_write_thumbnail', lambda *a, **k: True)
    monkeypatch.setattr(svc, '_run_ffmpeg', _run)
    monkeypatch.setattr(svc, '_ffmpeg_or_raise', lambda: '/usr/bin/ffmpeg')
    return calls


def _folder(tmp_path, names=('a.mp4',)):
    folder = tmp_path / 'rushes'
    folder.mkdir(parents=True, exist_ok=True)
    for n in names:
        (folder / n).write_bytes(b'\x00' * 32)
    return str(folder)


def _make_bank(client, tmp_path, names=('a.mp4',)):
    r = client.post('/api/video-bank/create',
                    json={'name': 'rushes', 'folder': _folder(tmp_path, names)})
    assert r.status_code == 200, r.get_json()
    return r.get_json()['id']


def _ready_bank(client, tmp_path):
    """A bank scanned, detected and fully kept — the state promotion starts from."""
    bank_id = _make_bank(client, tmp_path)
    assert client.post(f'/api/video-bank/{bank_id}/pipeline',
                       json={}).status_code == 202
    assert client.post(f'/api/video-bank/{bank_id}/triage',
                       json={'ids': [], 'status': 'keep'}).status_code == 200
    return bank_id


# --- the blueprints exist and are wired ---------------------------------------

def test_the_video_bank_blueprint_is_registered(client, tmp_path):
    """`routes/__init__` imports blueprints by NAME from a tuple and swallows the
    ImportError of one that does not exist yet. A module written but not added to
    that tuple therefore answers 404 on every route while looking finished."""
    assert client.get('/api/video-banks').status_code == 200


def test_the_video_dataset_blueprint_is_registered(client):
    assert client.get('/api/video-datasets').status_code == 200


# --- creating and reading a bank ----------------------------------------------

def test_creating_a_bank_reports_what_it_inventoried(client, tmp_path):
    r = client.post('/api/video-bank/create',
                    json={'name': 'rushes', 'folder': _folder(tmp_path,
                                                              ('a.mp4', 'b.MOV'))})

    assert r.status_code == 200
    assert r.get_json()['added'] == 2


def test_a_folder_that_does_not_exist_is_a_400_not_a_500(client, tmp_path):
    """The most common first click in this lane is a pasted path with a typo."""
    r = client.post('/api/video-bank/create',
                    json={'name': 'x', 'folder': str(tmp_path / 'nope')})

    assert r.status_code == 400
    assert 'error' in r.get_json()


def test_the_workspace_payload_carries_counters_sources_and_capability(
        client, tmp_path, seams):
    """Capability rides on the payload as THREE booleans, not one verdict: decode,
    detect and encode fail independently and are fixed differently, so a single
    "video unavailable" is how a user reinstalls the wrong thing."""
    bank_id = _make_bank(client, tmp_path)

    body = client.get(f'/api/video-bank/{bank_id}').get_json()

    assert body['counts']['sources'] == 1
    assert body['sources'][0]['relpath'] == 'a.mp4'
    assert set(body['capability']) >= {'ok', 'decode', 'detect', 'encode'}


def test_an_unknown_bank_is_a_404(client):
    assert client.get('/api/video-bank/9999').status_code == 404


# --- the passes ----------------------------------------------------------------

@pytest.mark.parametrize('path', ['probe', 'detect', 'thumbs', 'pipeline'])
def test_every_pass_answers_202_and_runs_in_the_background(client, tmp_path,
                                                           seams, path):
    """A pass over a folder of rushes takes minutes. Holding the HTTP request open
    for it is not an option, so the POST returns immediately and the UI polls the
    bank payload — the same contract as every image-bank pass."""
    bank_id = _make_bank(client, tmp_path)

    r = client.post(f'/api/video-bank/{bank_id}/{path}', json={})

    assert r.status_code == 202, r.get_json()


@pytest.mark.parametrize('path', ['probe', 'detect', 'thumbs', 'pipeline'])
def test_a_busy_bank_refuses_with_the_kind_that_holds_it(client, tmp_path, seams,
                                                         path):
    """`busy_kind` is the machine-readable half. The refusal often lands before the
    first progress poll, so at that instant the response body is the only thing on
    the client that knows which pass is in the way — and parsing our own English
    sentence would be one rename away from breaking."""
    import time
    from app.services import bank_jobs
    bank_id = _make_bank(client, tmp_path)
    bank_jobs._jobs[svc.job_key(bank_id)] = {
        'kind': 'detect', 'done': 3, 'total': 9, 'error': None, 'cancelled': False,
        'finished': False, 'detail': None, 'started_at': time.time(),
        '_touched': time.time(), '_cancel_hook': None, 'pipeline': None}

    r = client.post(f'/api/video-bank/{bank_id}/{path}', json={})

    assert r.status_code == 409, r.get_json()
    assert r.get_json()['busy_kind'] == 'detect'


def test_a_pass_on_an_unknown_bank_is_a_404_not_a_400(client):
    """"Bank not found" is not a validation error the user can fix by editing the
    body — it means the bank was deleted in another tab."""
    assert client.post('/api/video-bank/9999/probe', json={}).status_code == 404


# --- triage --------------------------------------------------------------------

def test_triage_marks_the_clips_and_returns_the_new_counts(client, tmp_path, seams):
    """The counters ride back on the response so the gallery updates without a
    second round trip — a triage click is the most repeated gesture in this lane."""
    bank_id = _make_bank(client, tmp_path)
    client.post(f'/api/video-bank/{bank_id}/pipeline', json={})
    ids = client.get(f'/api/video-bank/{bank_id}/clips?ids_only=1').get_json()['ids']

    r = client.post(f'/api/video-bank/{bank_id}/triage',
                    json={'ids': ids[:1], 'status': 'reject', 'reason': 'blurry'})

    assert r.status_code == 200
    assert r.get_json()['counts']['reject'] == 1


def test_an_unknown_triage_status_is_refused(client, tmp_path, seams):
    """Only three words exist. A typo'd status silently writing itself into the
    column would make a clip invisible to every filter."""
    bank_id = _make_bank(client, tmp_path)

    r = client.post(f'/api/video-bank/{bank_id}/triage',
                    json={'ids': [], 'status': 'maybe'})

    assert r.status_code == 400


def test_the_clip_list_pages_and_filters(client, tmp_path, seams):
    bank_id = _make_bank(client, tmp_path)
    client.post(f'/api/video-bank/{bank_id}/pipeline', json={})

    body = client.get(f'/api/video-bank/{bank_id}/clips?status=pending').get_json()

    assert body['total'] == 2
    assert body['clips'][0]['start_s'] == 0.0
    assert body['clips'][0]['relpath'] == 'a.mp4'


def test_a_missing_thumbnail_is_a_404_rather_than_a_broken_image(client, tmp_path,
                                                                 seams):
    """The gallery renders a placeholder on 404. A 500 here would fill the console
    with errors for the ordinary case of a thumbnail pass that has not run."""
    bank_id = _make_bank(client, tmp_path)
    client.post(f'/api/video-bank/{bank_id}/probe', json={})
    client.post(f'/api/video-bank/{bank_id}/detect', json={})
    ids = client.get(f'/api/video-bank/{bank_id}/clips?ids_only=1').get_json()['ids']

    r = client.get(f'/api/video-bank/{bank_id}/clip/{ids[0]}/thumb')

    assert r.status_code == 404


# --- the target catalogue -------------------------------------------------------

def test_the_target_catalogue_is_served_with_its_caveats(client):
    """The frontend cannot hard-code these. Three fields decide whether a user
    wastes a week: `training_verified` (does the installed ai-toolkit have an
    architecture for it), `aitk_arch` (the string the training config needs, which
    is NOT our key — our wan22_ti2v5b is its wan22_5b), and `licence_note`.

    This test used to assert `wan22_ti2v5b.training_verified is False`, on the
    strength of web research about OTHER trainers. The installed ai-toolkit ships
    the architecture. Asserting a wrong fact is worse than asserting none: it
    defended the mistake."""
    body = client.get('/api/video/targets').get_json()

    by_key = {t['key']: t for t in body['targets']}
    assert by_key['wan22_14b']['fps'] == 16
    assert by_key['wan22_14b']['training_verified'] is True
    assert by_key['wan22_ti2v5b']['training_verified'] is True
    assert by_key['wan22_ti2v5b']['aitk_arch'] == 'wan22_5b'
    assert 'EU' in by_key['minimax_h3']['licence_note']
    assert 81 in by_key['wan22_14b']['frame_choices']


def test_each_target_says_how_long_its_default_clip_lasts(client):
    """"81 frames" means nothing to a user picking clips out of a rush; "5.0 s"
    does. Both Wan variants land on exactly 5.00 s at their own rate, which is the
    cross-check that the intervals arithmetic is right."""
    by_key = {t['key']: t for t in client.get('/api/video/targets')
              .get_json()['targets']}

    assert by_key['wan22_14b']['default_seconds'] == pytest.approx(5.0)
    assert by_key['wan22_ti2v5b']['default_seconds'] == pytest.approx(5.0)


# --- promotion ------------------------------------------------------------------

def test_promotion_answers_with_the_dataset_it_is_filling(client, tmp_path, seams):
    """202 and an id, so the UI can navigate straight to the dataset being built
    instead of guessing which one appeared."""
    bank_id = _ready_bank(client, tmp_path)

    r = client.post(f'/api/video-bank/{bank_id}/promote',
                    json={'name': 'wan set', 'target_profile': 'wan22_14b',
                          'frames': 81})

    assert r.status_code == 202, r.get_json()
    assert r.get_json()['id'] > 0


def test_a_frame_count_the_target_refuses_is_a_400_that_names_a_legal_one(
        client, tmp_path, seams):
    """29 is legal for Wan and illegal for LTX — the counter-example has to be
    picked with care, because every length Wan OFFERS also satisfies 8n+1."""
    bank_id = _ready_bank(client, tmp_path)

    r = client.post(f'/api/video-bank/{bank_id}/promote',
                    json={'name': 'x', 'target_profile': 'ltx23', 'frames': 29})

    assert r.status_code == 400
    assert '25' in r.get_json()['error']


def test_promoting_without_ffmpeg_is_a_503_before_anything_is_created(
        app, client, tmp_path, seams, monkeypatch):
    """503, not 400: nothing about the request is wrong, a tool is missing. And it
    has to land BEFORE the dataset row, or the user is left with an empty folder to
    clean up after a refusal."""
    from app.models import VideoDataset
    bank_id = _ready_bank(client, tmp_path)
    monkeypatch.setattr(svc, '_ffmpeg_or_raise', lambda: (_ for _ in ()).throw(
        RuntimeError('ffmpeg is required to cut clips and was not found')))

    r = client.post(f'/api/video-bank/{bank_id}/promote',
                    json={'name': 'x', 'target_profile': 'wan22_14b'})

    assert r.status_code == 503
    assert 'ffmpeg' in r.get_json()['error']
    with app.app_context():
        assert VideoDataset.query.count() == 0


def test_promotion_with_nothing_kept_is_a_400(client, tmp_path, seams):
    bank_id = _make_bank(client, tmp_path)
    client.post(f'/api/video-bank/{bank_id}/pipeline', json={})

    r = client.post(f'/api/video-bank/{bank_id}/promote',
                    json={'name': 'x', 'target_profile': 'wan22_14b'})

    assert r.status_code == 400


# --- the built dataset ----------------------------------------------------------

def _promote(client, tmp_path):
    bank_id = _ready_bank(client, tmp_path)
    r = client.post(f'/api/video-bank/{bank_id}/promote',
                    json={'name': 'wan set', 'target_profile': 'wan22_14b',
                          'frames': 81})
    assert r.status_code == 202, r.get_json()
    return bank_id, r.get_json()['id']


def test_the_dataset_payload_lists_its_clips_with_their_provenance(client, tmp_path,
                                                                   seams):
    _bank_id, ds_id = _promote(client, tmp_path)

    body = client.get(f'/api/video-dataset/{ds_id}').get_json()

    assert body['fps'] == 16 and body['frames'] == 81
    assert [i['filename'] for i in body['items']] == ['clip_0001.mp4',
                                                      'clip_0002.mp4']
    assert body['items'][1]['start_s'] == 41.25


def test_editing_a_caption_rewrites_the_sidecar_on_disk(client, tmp_path, seams):
    """THE test of this route. The trainer never reads our database — it reads the
    .txt next to the .mp4. A caption stored only in the DB trains the dataset on
    the previous text while the UI shows the new one, and nothing anywhere reveals
    it. So the write to disk is the feature; the row is the bookkeeping."""
    _bank_id, ds_id = _promote(client, tmp_path)
    body = client.get(f'/api/video-dataset/{ds_id}').get_json()
    item = body['items'][0]

    r = client.post(f'/api/video-dataset/{ds_id}/clip/{item["id"]}/caption',
                    json={'caption': 'a woman walking through a café at dusk'})

    assert r.status_code == 200
    sidecar = os.path.join(body['output_dir'], 'clip_0001.txt')
    assert open(sidecar, encoding='utf-8').read() == \
        'a woman walking through a café at dusk'


def test_clearing_a_caption_leaves_an_empty_file_never_a_missing_one(client,
                                                                     tmp_path, seams):
    """Deleting the sidecar would be the intuitive way to "remove" a caption and it
    is the one thing that must not happen: musubi-tuner raises FileNotFoundError
    out of a worker with no handler, and diffusion-pipe drops the clip."""
    _bank_id, ds_id = _promote(client, tmp_path)
    body = client.get(f'/api/video-dataset/{ds_id}').get_json()
    item = body['items'][0]
    client.post(f'/api/video-dataset/{ds_id}/clip/{item["id"]}/caption',
                json={'caption': 'something'})

    client.post(f'/api/video-dataset/{ds_id}/clip/{item["id"]}/caption',
                json={'caption': ''})

    assert os.path.isfile(os.path.join(body['output_dir'], 'clip_0001.txt'))


def test_deleting_a_dataset_is_a_404_when_it_is_not_yours(client):
    assert client.delete('/api/video-dataset/9999').status_code == 404


def test_deleting_a_dataset_removes_it_from_the_list(client, tmp_path, seams):
    _bank_id, ds_id = _promote(client, tmp_path)

    assert client.delete(f'/api/video-dataset/{ds_id}').status_code == 200

    assert client.get('/api/video-datasets').get_json()['datasets'] == []
