"""🗂️ Grid thumbnails in one round trip — /bank/<id>/thumbs.

The bank grid used to draw one <img> per tile, each costing an RTT on a slow
link. The batch endpoint returns several tile WebPs in ONE response using the
shared index-keyed container [u32 position][u32 length][bytes] — position is the
caller's index, so a grid maps each blob back to the tile it owns."""
import struct

from PIL import Image


def _bank(workdir, app):
    from app.services import image_bank_service as banks
    src = workdir / 'src'
    src.mkdir(parents=True, exist_ok=True)
    im = Image.new('RGB', (400, 300), (120, 40, 200))
    im.save(str(src / 'a0.jpg'), 'JPEG')
    im.save(str(src / 'a1.jpg'), 'JPEG')
    with app.app_context():
        bank, _added = banks.create_bank('local', 'Dump', str(src))
        from app.extensions import db
        db.session.commit()
        return bank.id


def _rows(bank_id, app):
    with app.app_context():
        from app.models import BankImage
        return [r.id for r in BankImage.query.filter_by(bank_id=bank_id).all()]


def test_bank_thumbs_batch_returns_an_index_keyed_container(app, client, tmp_path):
    bank_id = _bank(tmp_path, app)
    ids = _rows(bank_id, app)
    assert len(ids) == 2
    resp = client.post(f'/api/bank/{bank_id}/thumbs',
                       json={'ids': [ids[1], ids[0]]})
    assert resp.status_code == 200
    body = resp.get_data()
    assert resp.mimetype == 'application/octet-stream'
    # Decode the container: entries must be keyed by the caller's index, not id.
    got = {}
    off = 0
    while off + 8 <= len(body):
        pos, ln = struct.unpack_from('>II', body, off)
        off += 8
        got[pos] = body[off:off + ln]
        off += ln
    assert off == len(body), 'no trailing garbage'
    assert set(got.keys()) == {0, 1}, 'keyed by caller position'
    assert len(got[0]) > 0 and len(got[1]) > 0
    # Each payload is a WebP.
    assert got[0][:4] == b'RIFF' and got[0][8:12] == b'WEBP'


def test_bank_thumbs_batch_skips_unknown_ids_and_requires_ids(app, client, tmp_path):
    bank_id = _bank(tmp_path, app)
    ids = _rows(bank_id, app)
    # One real id, one that does not exist: the missing one is just skipped.
    resp = client.post(f'/api/bank/{bank_id}/thumbs',
                       json={'ids': [ids[0], 999999]})
    assert resp.status_code == 200
    body = resp.get_data()
    pos, ln = struct.unpack_from('>II', body, 0)
    assert pos == 0
    assert len(body) == 8 + ln
    # No ids -> 400.
    assert client.post(f'/api/bank/{bank_id}/thumbs', json={}).status_code == 400
