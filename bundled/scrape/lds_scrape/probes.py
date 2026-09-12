"""Public scrape package presence, without importing sources or contacting sites."""
import importlib.util


def dependencies():
    from lds_sdk.lifecycle import is_available
    if not is_available('scrape'):
        return {'ok': False, 'detail': ''}
    # Same in-process and `python -m` modules as main's probe_scrape_deps.
    missing = [name for name in ('curl_cffi', 'gallery_dl', 'bs4', 'cloudscraper',
                                'instaloader', 'ddgs', 'yt_dlp')
               if importlib.util.find_spec(name) is None]
    return {'ok': not missing,
            'detail': 'scrape deps OK' if not missing else f"missing: {', '.join(missing)}"}


PROBES = {'scrape_deps': lambda: dependencies()['ok'],
          'scrape_deps_detail': lambda: dependencies()['detail']}
