"""Named watermark operations shared with the host; no module handle escapes."""

def scan(*args, **kwargs):
    from app.services.watermark_detector import scan
    return scan(*args, **kwargs)



__all__ = ['scan']
