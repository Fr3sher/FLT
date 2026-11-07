"""Reddit keyword search through OAuth. Anonymous JSON endpoints are blocked, so the
source uses an anonymous installed_client token and extracts images from post
JSON. Test canonical URL-to-endpoint mapping, gallery/direct/preview/empty image
extraction, tracking removal with content parameters preserved, forced www,
deduplication, cursor pagination and host matching. Token requests and _api_get
are mocked; no real Reddit calls."""

import pytest

pytestmark = pytest.mark.plugins('scrape')

from lds_scrape.sources import reddit
from lds_scrape.sources.base import Match
from lds_scrape.validators import Platform, url_validator


# --- _endpoint_for : routage (pur) ------------------------------------------
def test_endpoint_global_search():
    ep = reddit._endpoint_for('https://www.reddit.com/search/?q=film%20portrait')
    assert ep['kind'] == 'listing' and ep['api_path'] == '/search'
    assert ep['params']['q'] == 'film portrait'
    assert 'restrict_sr' not in ep['params']


def test_endpoint_subreddit_search_scoped():
    ep = reddit._endpoint_for('https://www.reddit.com/r/analog/search/?q=portrait&sort=top&t=year')
    assert ep['api_path'] == '/r/analog/search'
    assert ep['params']['restrict_sr'] == 1
    assert ep['params']['q'] == 'portrait' and ep['params']['t'] == 'year'


def test_endpoint_subreddit_listing_default_sort():
    assert reddit._endpoint_for('https://www.reddit.com/r/pics/')['api_path'] == '/r/pics/hot'
    assert reddit._endpoint_for('https://www.reddit.com/r/pics/top/?t=week')['api_path'] == '/r/pics/top'


def test_endpoint_post_and_user_and_direct():
    assert reddit._endpoint_for('https://www.reddit.com/r/pics/comments/xy/z/')['kind'] == 'post'
    assert reddit._endpoint_for('https://www.reddit.com/user/bob')['api_path'] == '/user/bob/submitted'
    d = reddit._endpoint_for('https://i.redd.it/abc.jpeg')
    assert d['kind'] == 'direct' and d['url'].endswith('abc.jpeg')


def test_endpoint_unrecognized_returns_none():
    assert reddit._endpoint_for('https://www.reddit.com/settings') is None


# --- _items_from_post : extraction (pur) ------------------------------------
def test_items_from_gallery_respects_order_and_thumb():
    post = {
        'title': 'shoot', 'subreddit': 'analog', 'is_gallery': True,
        'gallery_data': {'items': [{'media_id': 'B'}, {'media_id': 'A'}]},
        'media_metadata': {
            'A': {'e': 'Image', 's': {'u': 'https://i/A_full.jpg'},
                  'p': [{'u': 'https://i/A_108.jpg', 'x': 108},
                        {'u': 'https://i/A_320.jpg', 'x': 320}]},
            'B': {'e': 'Image', 's': {'u': 'https://i/B_full.jpg'}, 'p': []},
        },
    }
    items = reddit._items_from_post(post)
    assert [i['url'] for i in items] == ['https://i/B_full.jpg', 'https://i/A_full.jpg']
    # A: preview ≥320 chosen as thumbnail ; B: no preview → falls back to full url
    a = next(i for i in items if i['url'].endswith('A_full.jpg'))
    assert a['thumbnail'] == 'https://i/A_320.jpg'
    assert all(i['type'] == 'image' and i['platform'] == 'reddit' for i in items)


def test_items_from_direct_link():
    post = {'title': 't', 'url_overridden_by_dest': 'https://i.redd.it/x.png',
            'preview': {'images': [{'resolutions': [{'url': 'https://p/320.png', 'width': 320}]}]}}
    items = reddit._items_from_post(post)
    assert len(items) == 1 and items[0]['url'] == 'https://i.redd.it/x.png'
    assert items[0]['thumbnail'] == 'https://p/320.png'


def test_items_from_preview_fallback_for_external_link():
    # link post to a non-image URL, but reddit generated a preview → still usable
    post = {'title': 't', 'url': 'https://imgur.com/gallery/xyz',
            'preview': {'images': [{'source': {'url': 'https://p/src.jpg'},
                                    'resolutions': [{'url': 'https://p/320.jpg', 'width': 320}]}]}}
    items = reddit._items_from_post(post)
    assert len(items) == 1 and items[0]['url'] == 'https://p/src.jpg'


def test_items_from_textpost_yields_nothing():
    assert reddit._items_from_post({'title': 't', 'url': 'https://www.reddit.com/r/x/comments/1/'}) == []


# _canonical_reddit_url without network calls: no /s/ or redd.it links.
def test_canonical_purges_tracking_keeps_content_params():
    out = reddit._canonical_reddit_url(
        'https://old.reddit.com/r/analog/top/?t=month&utm_source=share&share_id=abc')
    assert out.startswith('https://www.reddit.com/r/analog/top/')
    assert 't=month' in out and 'utm_source' not in out and 'share_id' not in out


def test_canonical_leaves_cdn_untouched():
    u = 'https://i.redd.it/abc.jpeg'
    assert reddit._canonical_reddit_url(u) == u


# --- RedditSource.match ------------------------------------------------------
def test_match_detects_reddit_hosts_only():
    src = reddit.RedditSource()
    assert src.match('https://www.reddit.com/r/pics/') is not None
    assert src.match('https://redd.it/abc') is not None
    assert src.match('https://example.com/r/pics/') is None
    assert url_validator.detect_platform('https://old.reddit.com/r/x') == Platform.REDDIT


# RedditSource.scan with a mocked API.
def _listing(children, after=None):
    return {'data': {'after': after, 'children': [{'data': d} for d in children]}}


def _img_post(pid):
    return {'title': pid, 'subreddit': 's', 'url_overridden_by_dest': f'https://i.redd.it/{pid}.jpg'}


def test_scan_listing_extracts_and_dedups(monkeypatch):
    monkeypatch.setattr(reddit, '_get_token', lambda: 'tok')
    # duplicate url across two posts → deduped to one item
    dup = _img_post('same')
    monkeypatch.setattr(reddit, '_api_get',
                        lambda path, params, tok: _listing([_img_post('a'), dup, dup]))
    items, err = reddit.RedditSource().scan(Match(url='https://www.reddit.com/r/x/'))
    assert err is None
    assert sorted(i['url'] for i in items) == ['https://i.redd.it/a.jpg', 'https://i.redd.it/same.jpg']


def test_scan_small_listing_consumed_on_first_page_hides_load_more(monkeypatch):
    """A listing containing no more than _SCAN_MAX items is fully consumed on page
    zero. Walk batches while after is live and the limit is not reached; set
    match.paginated=False to hide a Load more action that cannot return anything."""
    monkeypatch.setattr(reddit, '_get_token', lambda: 'tok')
    pages = {
        None: _listing([_img_post('p0')], after='c1'),
        'c1': _listing([_img_post('p1')], after=None),
    }
    monkeypatch.setattr(reddit, '_api_get', lambda path, params, tok: pages[params.get('after')])

    m0 = Match(url='https://www.reddit.com/r/x/top/'); m0.page = 0
    items0, err0 = reddit.RedditSource().scan(m0)
    assert err0 is None
    assert sorted(i['url'] for i in items0) == ['https://i.redd.it/p0.jpg', 'https://i.redd.it/p1.jpg']
    assert m0.paginated is False   # listing exhausted on page 0 → no more to load


def test_scan_pagination_past_end_returns_empty(monkeypatch):
    monkeypatch.setattr(reddit, '_get_token', lambda: 'tok')
    # only one page exists (after=None) → requesting page 1 (skip past everything) yields nothing new
    monkeypatch.setattr(reddit, '_api_get',
                        lambda path, params, tok: _listing([_img_post('only')], after=None))
    m = Match(url='https://www.reddit.com/r/x/'); m.page = 1
    items, err = reddit.RedditSource().scan(m)
    assert err is None and items == []
    assert m.paginated is False


def _gallery_post(pid, n):
    """Synthetic gallery post with n images using Reddit media_metadata/gallery_data
    structure; see the ordering and thumbnail test."""
    order = [f'{pid}_{i}' for i in range(n)]
    return {
        'title': pid, 'subreddit': 's', 'is_gallery': True,
        'gallery_data': {'items': [{'media_id': mid} for mid in order]},
        'media_metadata': {mid: {'e': 'Image', 's': {'u': f'https://i.redd.it/{mid}.jpg'}, 'p': []}
                           for mid in order},
    }


def test_scan_batch_cap_split_post_recovered_via_pagination(monkeypatch):
    """Regression: a gallery-heavy subreddit reaches _SCAN_MAX=200 halfway through
    post23 of30, dropping remaining images and posts24-30. A listing-level after
    cursor already points beyond the entire fetched batch, losing those items
    forever. Item-level skipping in _walk_items replays the ordered stream and
    resumes exactly at the cap without loss."""
    monkeypatch.setattr(reddit, '_get_token', lambda: 'tok')
    posts = [_gallery_post(f'p{i}', 9) for i in range(30)]   # 30 posts * 9 imgs = 270
    monkeypatch.setattr(reddit, '_api_get',
                        lambda path, params, tok: _listing(posts, after=None))  # A single batch.

    src = reddit.RedditSource()
    m0 = Match(url='https://www.reddit.com/r/x/'); m0.page = 0
    items0, err0 = src.scan(m0)
    assert err0 is None
    assert len(items0) == reddit._SCAN_MAX            # capped at 200 (198 + 2 of post #23)
    assert m0.paginated is not False                   # more remains → "Load more" stays visible

    m1 = Match(url='https://www.reddit.com/r/x/'); m1.page = 1
    items1, err1 = src.scan(m1)
    assert err1 is None

    urls0 = {i['url'] for i in items0}
    urls1 = {i['url'] for i in items1}
    assert urls0.isdisjoint(urls1)                      # no duplicate across pages
    expected = {f'https://i.redd.it/p{i}_{j}.jpg' for i in range(30) for j in range(9)}
    assert urls0 | urls1 == expected                    # every image reachable — nothing lost
    assert len(urls1) == 270 - reddit._SCAN_MAX          # exactly the leftover: 70
    assert m1.paginated is False                         # page 1 exhausts the listing


def test_scan_pagination_replay_crosses_listing_batches(monkeypatch):
    """Item skipping must replay from the BEGINNING across multiple API calls when
    needed, not just the final batch. Verify requested cursor count and order."""
    monkeypatch.setattr(reddit, '_get_token', lambda: 'tok')
    batch1 = [_gallery_post(f'a{i}', 9) for i in range(25)]   # 225 imgs, after='c1'
    batch2 = [_gallery_post(f'b{i}', 9) for i in range(5)]    # 45 imgs, after=None
    pages = {None: _listing(batch1, after='c1'), 'c1': _listing(batch2, after=None)}
    calls = []

    def fake_get(path, params, tok):
        calls.append(params.get('after'))
        return pages[params.get('after')]
    monkeypatch.setattr(reddit, '_api_get', fake_get)

    m1 = Match(url='https://www.reddit.com/r/x/'); m1.page = 1
    items1, err1 = reddit.RedditSource().scan(m1)
    assert err1 is None
    # page 1 = items 200..269 → the last 25 of batch1 + all 45 of batch2 → both
    # cursors get re-requested from scratch (replay), in order.
    assert calls == [None, 'c1']
    urls1 = {i['url'] for i in items1}
    assert any(u.startswith('https://i.redd.it/a24_') for u in urls1)   # tail of batch1
    assert any(u.startswith('https://i.redd.it/b0_') for u in urls1)    # start of batch2
    assert len(urls1) == 70
    assert m1.paginated is False


def test_scan_listing_budget_exhausted_marks_partial(monkeypatch):
    """A pathological listing with a never-ending cursor and few images must stop
    after _MAX_LISTING_CALLS. Return collected results as partial so reaching the
    API-call budget is never silent."""
    monkeypatch.setattr(reddit, '_get_token', lambda: 'tok')
    calls = {'n': 0}

    def fake_get(path, params, tok):
        calls['n'] += 1
        # One text post without images per call; the cursor never expires.
        return _listing([{'title': 't', 'subreddit': 's'}], after=f'c{calls["n"]}')
    monkeypatch.setattr(reddit, '_api_get', fake_get)

    m = Match(url='https://www.reddit.com/r/x/'); m.page = 0
    items, err = reddit.RedditSource().scan(m)
    assert err is None
    assert items == []
    assert getattr(items, 'partial', False) is True
    assert calls['n'] == reddit._MAX_LISTING_CALLS
    # Budget exhausted before filling the page. Deeper pages would require larger skips
    # against the same budget and can never succeed either. Hide Load more and disclose
    # partial results in the banner. Otherwise the route would keep reporting
    # paginated=True, spending 60 API calls for zero items on every click.
    assert m.paginated is False


def test_scan_empty_keyword_is_error(monkeypatch):
    monkeypatch.setattr(reddit, '_get_token', lambda: 'tok')
    items, err = reddit.RedditSource().scan(Match(url='https://www.reddit.com/search/?q='))
    assert items is None and 'keyword' in err


def test_scan_direct_image_needs_no_api():
    items, err = reddit.RedditSource().scan(Match(url='https://i.redd.it/z.jpeg'))
    assert err is None and len(items) == 1 and items[0]['url'].endswith('z.jpeg')


def test_scan_unrecognized_url_is_error():
    items, err = reddit.RedditSource().scan(Match(url='https://www.reddit.com/settings'))
    assert items is None and 'unrecognized' in err


def test_scan_token_failure_is_graceful(monkeypatch):
    monkeypatch.setattr(reddit, '_get_token', lambda: None)
    items, err = reddit.RedditSource().scan(Match(url='https://www.reddit.com/r/x/'))
    assert items is None and 'authentication' in err


# --- 429 rate-limit handling ------------------------------------------------
class _Resp:
    def __init__(self, status, headers=None, body=None):
        self.status_code = status
        self.headers = headers or {}
        self._body = body or {}

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests as _r
            raise _r.HTTPError(f'{self.status_code}')


def test_reset_seconds_reads_headers():
    assert reddit._reset_seconds(_Resp(429, {'retry-after': '30'})) == 30
    assert reddit._reset_seconds(_Resp(429, {'x-ratelimit-reset': '540.0'})) == 540
    assert reddit._reset_seconds(_Resp(429, {})) is None


def test_api_get_429_far_reset_raises_ratelimited(monkeypatch):
    monkeypatch.setattr(reddit.requests, 'get',
                        lambda *a, **k: _Resp(429, {'x-ratelimit-reset': '600'}))
    slept = []
    monkeypatch.setattr(reddit.time, 'sleep', lambda s: slept.append(s))
    try:
        reddit._api_get('/search', {}, 'tok')
        assert False, 'should have raised'
    except reddit.RedditRateLimited as e:
        assert e.reset_seconds == 600
    assert slept == []          # far reset → no retry sleep


def test_api_get_429_near_reset_retries_once(monkeypatch):
    seq = [_Resp(429, {'retry-after': '2'}), _Resp(200, {}, {'ok': 1})]
    monkeypatch.setattr(reddit.requests, 'get', lambda *a, **k: seq.pop(0))
    monkeypatch.setattr(reddit.time, 'sleep', lambda s: None)
    monkeypatch.setitem(reddit._token_cache, 'value', 'tok')
    assert reddit._api_get('/search', {}, 'tok') == {'ok': 1}   # retry succeeded


def test_scan_rate_limited_returns_actionable_message(monkeypatch):
    monkeypatch.setattr(reddit, '_get_token', lambda: 'tok')

    def boom(path, params, tok):
        raise reddit.RedditRateLimited(45)
    monkeypatch.setattr(reddit, '_api_get', boom)
    items, err = reddit.RedditSource().scan(Match(url='https://www.reddit.com/search/?q=cats'))
    assert items is None
    assert '1000' in err and '~45s' in err


# --- client-id perso & invalidation du cache de jeton ------------------------
def test_client_id_env_overrides_shared_default(monkeypatch):
    monkeypatch.setattr(reddit, 'resolve_cookies', lambda key: None)   # No local admin file.
    monkeypatch.setenv('REDDIT_CLIENT_ID', 'my-own-id')
    assert reddit._client_id() == 'my-own-id'
    monkeypatch.delenv('REDDIT_CLIENT_ID')
    assert reddit._client_id() == reddit._GDL_CLIENT_ID


def test_get_token_remints_when_client_id_changes(monkeypatch):
    """A cached token belongs to the client ID and quota that issued it. Saving a
    personal ID in Settings changes the environment without restart; invalidate
    and reissue the token rather than using the shared quota for up to 24 hours."""
    calls = []

    def fake_post(url, data=None, auth=None, headers=None, timeout=None):
        calls.append(auth[0])
        return _Resp(200, {}, {'access_token': f'tok-{auth[0]}', 'expires_in': 3600})
    monkeypatch.setattr(reddit.requests, 'post', fake_post)
    monkeypatch.setattr(reddit, 'resolve_cookies', lambda key: None)
    monkeypatch.setattr(reddit, '_token_cache', {'value': None, 'exp': 0.0, 'cid': None})
    monkeypatch.delenv('REDDIT_CLIENT_ID', raising=False)
    assert reddit._get_token() == f'tok-{reddit._GDL_CLIENT_ID}'
    assert reddit._get_token() == f'tok-{reddit._GDL_CLIENT_ID}'
    assert calls == [reddit._GDL_CLIENT_ID]                  # 2e appel servi par le cache
    monkeypatch.setenv('REDDIT_CLIENT_ID', 'my-own-id')
    assert reddit._get_token() == 'tok-my-own-id'            # Token issued again with the new client ID.
    assert calls == [reddit._GDL_CLIENT_ID, 'my-own-id']
