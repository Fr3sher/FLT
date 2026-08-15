import pathlib
import pytest

from app import FRONTEND_DIST


def _first_hashed_asset():
    asset_dir = FRONTEND_DIST / 'assets'
    if not asset_dir.is_dir():
        pytest.skip('frontend dist not built')
    asset = next(asset_dir.glob('*.js'), None)
    if asset is None:
        pytest.skip('no hashed js asset in frontend/dist/assets')
    return asset.name


def test_hashed_assets_are_immutable(client):
    name = _first_hashed_asset()
    resp = client.get(f'/assets/{name}')
    assert resp.status_code == 200
    cache = resp.headers.get('Cache-Control', '')
    assert 'max-age=31536000' in cache
    assert 'immutable' in cache


def test_index_html_stays_revalidatable(client):
    resp = client.get('/')
    assert resp.status_code == 200
    cache = resp.headers.get('Cache-Control', '')
    # The app shell must NOT be cached as immutable: its URL is stable and a
    # new build must be picked up on the next visit.
    assert 'immutable' not in cache
