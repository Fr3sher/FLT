"""Shared OCR and geometry without loading the optional Video product."""
from .video_host import text_geometry as geometry

def text_engine_reason(*args, **kwargs):
    from app.services.video_safe_zone import text_engine_reason
    return text_engine_reason(*args, **kwargs)


def read_text_boxes(*args, **kwargs):
    from app.services.video_safe_zone import read_text_boxes
    return read_text_boxes(*args, **kwargs)


def luma_grid(*args, **kwargs):
    from app.services.video_safe_zone import luma_grid
    return luma_grid(*args, **kwargs)


def text_score_min(*args, **kwargs):
    from app.services.video_safe_zone import text_score_min
    return text_score_min(*args, **kwargs)



__all__ = ['geometry', 'text_engine_reason', 'read_text_boxes', 'luma_grid', 'text_score_min']
