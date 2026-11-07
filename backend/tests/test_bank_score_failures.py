"""Failed scoring attempts must be visible without discarding successful work."""
import pytest

from test_bank_score_resume import (
    _fake_child, _flat, _mkbank, _rows, scoring_available,  # noqa: F401
)


@pytest.mark.parametrize('successful,with_reason', [(0, True), (0, False), (1, True)])
def test_score_failure_summary_and_saved_results(
        client, tmp_path, app, monkeypatch, scoring_available,
        successful, with_reason):
    from app.services import image_bank_service as banks

    bank_id = _mkbank(client, tmp_path, {'a.jpg': _flat(30), 'b.jpg': _flat(60)})
    body = (
        f'good = images[:{successful}]\n'
        'results = {p: {"state": "ok", "aesthetic": 6.5, "nsfw": 0.25}\n'
        '           if p in good else {"state": "error"} for p in images}\n'
        'out = {"ok": True, "computed": len(images), "reused": 0,\n'
        '       "results": results, "clusters": {p: 1 for p in good}}\n'
    )
    if with_reason:
        body += 'out["image_errors"] = ["RuntimeError: CLIP computation failed"]\n'
    monkeypatch.setattr(banks, '_SCORE_SCRIPT', _fake_child(tmp_path, body))
    chained = []
    monkeypatch.setattr(banks, '_chain_medium_after_score',
                        lambda *args: chained.append(True) or '')

    assert client.post(f'/api/bank/{bank_id}/score', json={}).status_code == 202
    activity = client.get(f'/api/bank/{bank_id}').get_json()['activity']
    detail = activity['detail']
    assert f'{2 - successful} image(s) failed' in detail
    assert 'run Score again to retry' in detail
    assert 'Successful cached images are kept' in detail
    assert ('CLIP computation failed' in detail) == with_reason
    assert 'no image carried a usable embedding' not in detail
    if successful:
        assert not activity['error']
        assert 'scored 1 image(s)' in detail
        assert chained == [True]
    else:
        assert activity['error'].startswith('Scoring failed')
        assert chained == []
    rows = _rows(app, bank_id)
    assert sum(r.aesthetic_score == 6.5 for r in rows.values()) == successful
    assert sum(r.style_cluster is not None for r in rows.values()) == successful
