"""▶ Review lightbox image — full-res, WebP, cached.

ensure_review_image must keep the source's pixel dimensions (no downscale — the
win is compression + caching, not losing detail you're deciding on) while
producing a WebP that is smaller than the raw source, and reuse the file on the
second call instead of re-encoding."""
import os
import pytest
from PIL import Image


def _bank(workdir):
    from app.services import image_bank_service as banks
    src = workdir / 'src'
    src.mkdir(parents=True, exist_ok=True)
    # A noisier image so the WebP re-encode is measurably smaller than the JPEG.
    im = Image.new('RGB', (1200, 800))
    px = im.load()
    for y in range(0, 800, 2):
        for x in range(0, 1200, 2):
            px[x, y] = ((x * 7) % 256, (y * 13) % 256, (x ^ y) % 256)
    im.save(str(src / 'a0.jpg'), 'JPEG', quality=95)
    bank, _added = banks.create_bank('local', 'Dump', str(src))
    from app.extensions import db
    db.session.commit()
    return bank.id


def _row(bank_id):
    from app.models import BankImage
    return BankImage.query.filter_by(bank_id=bank_id).first()


def test_review_image_keeps_resolution_and_smaller_webp(app, tmp_path):
    from app.services import image_bank_service as banks
    with app.app_context():
        bank_id = _bank(tmp_path)
        bank = banks.get_bank('local', bank_id)
        row = _row(bank_id)
        raw = banks.resolved_image_path(bank, row)
        raw_bytes = os.path.getsize(raw)
        with Image.open(raw) as im:
            src_size = im.size
        rpath = banks.ensure_review_image(bank, row)
        assert rpath is not None
        with Image.open(rpath) as im:
            assert im.size == src_size, 'review image must keep full resolution'
            assert im.format == 'WEBP'
        assert os.path.getsize(rpath) < raw_bytes, 'webp must be smaller than the raw source'
        # Second call reuses the cached file (same inode/bytes, no re-encode).
        again = banks.ensure_review_image(bank, row)
        assert again == rpath
