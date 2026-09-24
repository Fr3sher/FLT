"""Named adapters to the existing public host; no plugin implementation is imported."""

_EXPORTS = {'MAX_DRIVER_BYTES': ('app.scrape.netfetch', 'MAX_DRIVER_BYTES'), 'download_via_ytdlp': ('app.scrape.netfetch', 'download_via_ytdlp'), 'fetch_hardened_bytes': ('app.scrape.netfetch', 'fetch_hardened_bytes'), 'validate_public_url': ('app.scrape.netfetch', '_validate_public_http_url')}
__all__ = list(_EXPORTS)


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(name)
    from importlib import import_module
    module, symbol = _EXPORTS[name]
    return getattr(import_module(module), symbol)
