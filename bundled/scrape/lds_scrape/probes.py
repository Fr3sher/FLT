"""Public scrape package presence, without importing sources or contacting sites."""
from lds_sdk.setup import missing_modules


def dependencies():
    from lds_sdk.lifecycle import is_available
    if not is_available('scrape'):
        return {'ok': False, 'detail': ''}
    # Same in-process and `python -m` modules as main's probe_scrape_deps.
    missing = missing_modules(('curl_cffi', 'gallery_dl', 'bs4', 'cloudscraper',
                               'instaloader', 'ddgs', 'yt_dlp'))
    return {'ok': not missing,
            'detail': 'scrape deps OK' if not missing else f"missing: {', '.join(missing)}"}


PROBES = {'scrape_deps': lambda: dependencies()['ok'],
          'scrape_deps_detail': lambda: dependencies()['detail']}
