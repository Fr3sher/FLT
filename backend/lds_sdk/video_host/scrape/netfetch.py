"""Named adapters to existing public host services; implementations remain in main."""

_EXPORTS = {'MAX_DRIVER_BYTES': ('app.scrape.netfetch', 'MAX_DRIVER_BYTES'),
 '_validate_public_http_url': ('app.scrape.netfetch', '_validate_public_http_url'),
 'download_via_ytdlp': ('app.scrape.netfetch', 'download_via_ytdlp')}
__all__ = list(_EXPORTS)


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(name)
    from importlib import import_module
    module, symbol = _EXPORTS[name]
    return getattr(import_module(module), symbol)
