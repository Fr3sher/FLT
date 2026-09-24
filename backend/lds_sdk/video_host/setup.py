"""Named setup operations shared with the host; no module handle escapes."""

def bundled_pack_state(*args, **kwargs):
    from app.setup_installer import _bundled_pack_state
    return _bundled_pack_state(*args, **kwargs)



__all__ = ['bundled_pack_state']
