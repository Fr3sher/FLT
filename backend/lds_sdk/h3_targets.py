"""Named public H3 target settings shared by Video and Live."""

from app.services.video_targets import (
    PROFILE_KEYS, clip_seconds, frame_choices, get, is_legal_frames,
    snap_frames, validate_resolution, wants_audio,
)

__all__ = ['PROFILE_KEYS', 'clip_seconds', 'frame_choices', 'get', 'is_legal_frames', 'snap_frames', 'validate_resolution', 'wants_audio']
