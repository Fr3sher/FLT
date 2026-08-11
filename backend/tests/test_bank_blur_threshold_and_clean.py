"""The 🌫 blur threshold after the per-tile rework, and the ✨ Clean counter.

THE BLUR DEFECT. The sharpness score moved to a new scale when per-tile
scoring shipped (p90 of tile variances — image_quality.py), but the default
threshold stayed at the whole-frame era's 100. Measured on a real
36 921-image bank: the LOWEST stored blur_score was 103.9 — sharp photos sit
at 4 000-9 600, a frank gaussian blur (r≈2.5) at 20-150 — so 100 could not
flag one single image, and "hard to track the blurry photos" was reported
from live use. The default is now 150 (frank blur), and a config still
carrying EXACTLY the stale 100 reads as the new default: a full-config Save
writes every default into config.json, so most installs hold 100 without
anyone having chosen it. 90 or 120 is a hand-tuned value and must survive.

THE CLEAN COUNTER. ✨ Clean was the one Quality chip with no number, which
reads as "not a filter" next to six counted neighbours. It now counts, from
the same criterion its grid filter applies, so the two can never disagree.
"""
from PIL import ImageFilter

from app import config as cfg
from app.services.image_bank_service import thresholds

from test_image_bank import _mkbank, bokeh_like


def _set_sharpness(client, value):
    with client.application.app_context():
        cfg.save_config({'bank': {'sharpness_min': value}})


def test_the_stale_pre_tiling_default_reads_as_the_new_default(client):
    _set_sharpness(client, 100)
    with client.application.app_context():
        assert thresholds()['sharpness_min'] == \
            cfg.DEFAULTS['bank']['sharpness_min']


def test_a_hand_tuned_value_survives_even_next_to_the_stale_one(client):
    # 90 is almost certainly dead on the new scale too — but a deliberate
    # setting is never rewritten; only the stale default is not a setting.
    for chosen in (90, 120, 300):
        _set_sharpness(client, chosen)
        with client.application.app_context():
            assert thresholds()['sharpness_min'] == chosen


def test_the_new_default_is_calibrated_for_the_tile_scale(client):
    # The guard against re-introducing the dead threshold: the default must
    # sit ABOVE what a frankly blurred image scores (so it can flag one) and
    # BELOW what the bokeh fixture's sharp subject scores (so a sharp region
    # still clears it — the whole point of the tile rework).
    from app.services.image_quality import quality_metrics
    default = cfg.DEFAULTS['bank']['sharpness_min']
    sharp = quality_metrics(bokeh_like())
    soft = quality_metrics(bokeh_like().filter(ImageFilter.GaussianBlur(6)))
    assert soft['blur_score'] < default < sharp['blur_score'], (
        soft['blur_score'], default, sharp['blur_score'])


def test_clean_is_counted_and_agrees_with_its_own_grid(client, tmp_path):
    # 1024 px, not the fixture's 512 default: min_side (768) would flag both
    # 'small' and the sharp one would rightly drop out of ✨ Clean.
    bank_id, _src = _mkbank(client, tmp_path, {
        'sharp.png': bokeh_like(size=1024, subject=416),
        'soft.png': bokeh_like(size=1024, subject=416)
                    .filter(ImageFilter.GaussianBlur(6)),
    })
    r = client.post(f'/api/bank/{bank_id}/scan', json={})
    assert r.status_code in (200, 202), r.get_json()

    payload = client.get(f'/api/bank/{bank_id}').get_json()
    assert payload['flags']['blur'] == 1
    assert payload['flags']['clean'] == 1

    # The chip's number and the grid it opens come from the same criterion.
    page = client.get(f'/api/bank/{bank_id}/images?flag=clean').get_json()
    assert page['total'] == payload['flags']['clean']
    rels = [im['relpath'] for im in page['images']]
    assert rels == ['sharp.png']

    # The filtered chip counters (/facets) carry the same key.
    fc = client.get(f'/api/bank/{bank_id}/facets').get_json()
    assert fc['flags']['clean'] == 1
