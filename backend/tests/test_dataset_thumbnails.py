"""The tile-size thumbnail endpoint of the dataset lane.

What is being pinned here is not "a smaller picture comes back" — it is the
three things that make a thumbnail cache safe to put in front of every grid in
the app: it must never invent a different 404 story than /img/, it must never
serve yesterday's pixels for a file that was rewritten under the same name, and
it must never let a URL decide how much disk it gets.
"""
import io
import os

import pytest
from PIL import Image

from app.services import dataset_thumbs
from app.services.dataset_storage import ensure_dataset_dir


def _png_bytes(size=(1600, 1200), color=(200, 30, 30)):
    buf = io.BytesIO()
    Image.new('RGB', size, color).save(buf, 'PNG')
    return buf.getvalue()


def _create(client, name='Thumbs', trigger='thumbs'):
    return client.post('/api/dataset/create',
                       json={'name': name, 'trigger_word': trigger}).get_json()['id']


def _write(app, ds_id, filename, payload):
    with app.app_context():
        folder = ensure_dataset_dir(ds_id)
    path = os.path.join(folder, filename)
    with open(path, 'wb') as fh:
        fh.write(payload)
    return path


def _decoded(resp):
    return Image.open(io.BytesIO(resp.data))


# --- the size ladder ---------------------------------------------------------

@pytest.mark.parametrize('raw, expected', [
    (None, dataset_thumbs.DEFAULT_THUMB_SIDE),
    ('', dataset_thumbs.DEFAULT_THUMB_SIDE),
    ('abc', dataset_thumbs.DEFAULT_THUMB_SIDE),
    ('0', dataset_thumbs.DEFAULT_THUMB_SIDE),
    ('-40', dataset_thumbs.DEFAULT_THUMB_SIDE),
    ('1', 128),
    ('200', 256),
    ('320', 320),
    ('999999', 1024),
])
def test_requested_size_is_snapped_onto_the_ladder(raw, expected):
    """A free-form `?s=` would let any URL mint an unbounded number of cache
    entries per image; junk in it must still yield a picture, not a 400."""
    assert dataset_thumbs.clamp_thumb_side(raw) == expected


def test_huge_size_request_cannot_exceed_the_cap(client, app):
    ds_id = _create(client)
    _write(app, ds_id, 'big.png', _png_bytes((1600, 1200)))
    resp = client.get(f'/api/dataset/{ds_id}/thumb/big.png?s=99999')
    assert resp.status_code == 200
    assert max(_decoded(resp).size) == 1024


# --- the happy path ----------------------------------------------------------

def test_thumb_is_a_small_webp_and_far_lighter_than_the_original(client, app):
    ds_id = _create(client)
    original = _png_bytes((1600, 1200))
    _write(app, ds_id, 'shot.png', original)

    full = client.get(f'/api/dataset/{ds_id}/img/shot.png')
    thumb = client.get(f'/api/dataset/{ds_id}/thumb/shot.png?s=320')
    assert full.status_code == 200 and thumb.status_code == 200

    im = _decoded(thumb)
    assert im.format == 'WEBP'
    assert max(im.size) == 320
    # Aspect ratio survives — the lightbox pre-positions its action bar from the
    # ratio the TILE reported, so a squashed thumbnail would move the buttons.
    assert abs((im.size[0] / im.size[1]) - (1600 / 1200)) < 0.01
    assert len(thumb.data) < len(full.data) / 5


def test_thumb_is_cached_on_disk_and_the_second_hit_reuses_it(client, app):
    ds_id = _create(client)
    _write(app, ds_id, 'shot.png', _png_bytes())
    first = client.get(f'/api/dataset/{ds_id}/thumb/shot.png?s=256')
    assert first.status_code == 200

    with app.app_context():
        cache = dataset_thumbs.thumbs_dir(ds_id)
        files = sorted(p.name for p in cache.glob('*.webp'))
    assert len(files) == 1

    second = client.get(f'/api/dataset/{ds_id}/thumb/shot.png?s=256')
    assert second.status_code == 200 and second.data == first.data
    with app.app_context():
        assert sorted(p.name for p in dataset_thumbs.thumbs_dir(ds_id).glob('*.webp')) == files


def test_two_sizes_coexist_in_the_cache(client, app):
    """The board asks for 512 and the sweep grid for 256 in the same session —
    one must not evict the other."""
    ds_id = _create(client)
    _write(app, ds_id, 'shot.png', _png_bytes())
    assert client.get(f'/api/dataset/{ds_id}/thumb/shot.png?s=256').status_code == 200
    assert client.get(f'/api/dataset/{ds_id}/thumb/shot.png?s=512').status_code == 200
    with app.app_context():
        assert len(list(dataset_thumbs.thumbs_dir(ds_id).glob('*.webp'))) == 2


# --- staleness ---------------------------------------------------------------

def test_replacing_the_file_under_the_same_name_replaces_the_thumbnail(client, app):
    """THE reason this cache is keyed on mtime+size rather than on a row id like
    the Bank's: crop, rotate, ✨ improve and regenerate all rewrite the same
    filename in place, from code paths that will never remember to call an
    invalidation helper."""
    ds_id = _create(client)
    path = _write(app, ds_id, 'shot.png', _png_bytes(color=(255, 0, 0)))
    before = client.get(f'/api/dataset/{ds_id}/thumb/shot.png?s=256')
    assert _decoded(before).convert('RGB').getpixel((10, 10))[0] > 150
    # The test client keeps the served WebP OPEN until the response is closed,
    # and on Windows an open file cannot be unlinked — the same reason the
    # collection below is best-effort in production.
    before.close()

    stat = os.stat(path)
    with open(path, 'wb') as fh:
        fh.write(_png_bytes(color=(0, 0, 255)))
    # Same-second rewrites are real (a crop is fast); force the mtime to differ
    # only if the filesystem gave us the same nanosecond back.
    if os.stat(path).st_mtime_ns == stat.st_mtime_ns:
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))

    after = client.get(f'/api/dataset/{ds_id}/thumb/shot.png?s=256')
    assert after.status_code == 200
    pixel = _decoded(after).convert('RGB').getpixel((10, 10))
    assert pixel[2] > 150 and pixel[0] < 100, 'served the pre-edit thumbnail'

    with app.app_context():
        # The superseded generation is collected, so an image edited fifty times
        # does not leave fifty dead WebPs behind.
        assert len(list(dataset_thumbs.thumbs_dir(ds_id).glob('*.webp'))) == 1


def test_browser_revalidates_instead_of_holding_the_url_for_an_hour(client, app):
    """A dataset URL's CONTENT changes, so the response must be conditional:
    a matching ETag answers 304 (no pixels on the wire), never a blind hit."""
    ds_id = _create(client)
    _write(app, ds_id, 'shot.png', _png_bytes())
    first = client.get(f'/api/dataset/{ds_id}/thumb/shot.png?s=256')
    etag = first.headers.get('ETag')
    assert etag
    again = client.get(f'/api/dataset/{ds_id}/thumb/shot.png?s=256',
                       headers={'If-None-Match': etag})
    assert again.status_code == 304
    assert not again.data


# --- 404 and traversal parity with /img/ -------------------------------------

def test_missing_file_404s_exactly_like_the_full_size_route(client, app):
    ds_id = _create(client)
    _write(app, ds_id, 'shot.png', _png_bytes())
    full = client.get(f'/api/dataset/{ds_id}/img/nope.png')
    thumb = client.get(f'/api/dataset/{ds_id}/thumb/nope.png')
    assert full.status_code == 404 and thumb.status_code == 404


def test_unknown_dataset_404s_like_the_full_size_route(client):
    full = client.get('/api/dataset/98765/img/shot.png')
    thumb = client.get('/api/dataset/98765/thumb/shot.png')
    assert full.status_code == 404 and thumb.status_code == 404
    assert thumb.get_json() == full.get_json()


def test_a_thumb_request_never_creates_the_dataset_folder(client, app):
    """Same read-only contract the /img/ route is held to: looking at a picture
    that is not there must not leave a directory behind."""
    from app.services.dataset_storage import dataset_path
    ds_id = _create(client, 'Read only', 'read_only')
    with app.app_context():
        folder = dataset_path(ds_id)
        assert not os.path.exists(folder)
        assert client.get(f'/api/dataset/{ds_id}/thumb/ghost.png').status_code == 404
        assert not os.path.exists(folder)
        assert not dataset_thumbs.thumbs_dir(ds_id).exists()


def test_traversal_is_refused(client, app):
    ds_id = _create(client)
    _write(app, ds_id, 'shot.png', _png_bytes())
    for attempt in ('../../secret.txt', '..%2f..%2fsecret.txt'):
        resp = client.get(f'/api/dataset/{ds_id}/thumb/{attempt}')
        assert resp.status_code in (400, 404), attempt


# --- fallbacks: a thumbnail is not always the right answer --------------------

def test_an_already_small_image_is_served_as_is(client, app):
    """Re-encoding a 64 px picture into a 512 px WebP spends CPU and disk to make
    it BIGGER. The original bytes come back instead — and no cache entry is
    created for it."""
    ds_id = _create(client)
    _write(app, ds_id, 'tiny.png', _png_bytes((64, 64)))
    resp = client.get(f'/api/dataset/{ds_id}/thumb/tiny.png?s=512')
    assert resp.status_code == 200
    assert _decoded(resp).format == 'PNG'
    with app.app_context():
        assert not dataset_thumbs.thumbs_dir(ds_id).exists()


def test_an_animated_gif_falls_back_to_the_original_instead_of_erroring(client, app):
    ds_id = _create(client)
    buf = io.BytesIO()
    frames = [Image.new('RGB', (900, 900), c) for c in ((255, 0, 0), (0, 255, 0))]
    frames[0].save(buf, 'GIF', save_all=True, append_images=frames[1:], duration=100)
    _write(app, ds_id, 'anim.gif', buf.getvalue())
    resp = client.get(f'/api/dataset/{ds_id}/thumb/anim.gif')
    assert resp.status_code == 200
    assert _decoded(resp).format == 'GIF'


def test_a_non_image_file_falls_back_to_the_original(client, app):
    """Datasets carry caption .txt files next to their pictures; a mistyped URL
    must not 500."""
    ds_id = _create(client)
    _write(app, ds_id, 'shot.txt', b'a blue haired woman, standing')
    resp = client.get(f'/api/dataset/{ds_id}/thumb/shot.txt')
    assert resp.status_code == 200
    assert b'blue haired' in resp.data


def test_deleting_the_dataset_takes_its_thumbnail_cache_with_it(client, app):
    ds_id = _create(client)
    _write(app, ds_id, 'shot.png', _png_bytes())
    served = client.get(f'/api/dataset/{ds_id}/thumb/shot.png')
    assert served.status_code == 200
    served.close()          # release the WebP the test client is still holding
    with app.app_context():
        assert dataset_thumbs.thumbs_dir(ds_id).exists()
    assert client.post(f'/api/dataset/{ds_id}/delete').status_code == 200
    with app.app_context():
        assert not dataset_thumbs.thumbs_dir(ds_id).exists()
