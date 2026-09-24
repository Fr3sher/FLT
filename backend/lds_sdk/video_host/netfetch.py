"""Named netfetch operations shared with the host; no module handle escapes."""

def validate_public_http_url(*args, **kwargs):
    from app.scrape.netfetch import _validate_public_http_url
    return _validate_public_http_url(*args, **kwargs)


def download_via_ytdlp(*args, **kwargs):
    from app.scrape.netfetch import download_via_ytdlp
    return download_via_ytdlp(*args, **kwargs)


from app.scrape.netfetch import MAX_DRIVER_BYTES as MAX_DRIVER_BYTES  # noqa: E402 — stable value/type identity

__all__ = ['validate_public_http_url', 'download_via_ytdlp', 'MAX_DRIVER_BYTES']
