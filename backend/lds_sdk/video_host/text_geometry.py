"""Shared picture-container and text geometry used by image and video passes."""
from app.services.video_safe_zone_geometry import BAND_PROBE, SIDES

def bands_of_grid(*args, **kwargs):
    from app.services.video_safe_zone_geometry import bands_of_grid
    return bands_of_grid(*args, **kwargs)


def vote_bands(*args, **kwargs):
    from app.services.video_safe_zone_geometry import vote_bands
    return vote_bands(*args, **kwargs)


def bars_ratio(*args, **kwargs):
    from app.services.video_safe_zone_geometry import bars_ratio
    return bars_ratio(*args, **kwargs)


def structural_text(*args, **kwargs):
    from app.services.video_safe_zone_geometry import structural_text
    return structural_text(*args, **kwargs)


def union_area(*args, **kwargs):
    from app.services.video_safe_zone_geometry import union_area
    return union_area(*args, **kwargs)


def safe_rect(*args, **kwargs):
    from app.services.video_safe_zone_geometry import safe_rect
    return safe_rect(*args, **kwargs)


def safe_area(*args, **kwargs):
    from app.services.video_safe_zone_geometry import safe_area
    return safe_area(*args, **kwargs)


__all__ = ['BAND_PROBE', 'SIDES', 'bands_of_grid', 'vote_bands', 'bars_ratio', 'structural_text', 'union_area', 'safe_rect', 'safe_area']
