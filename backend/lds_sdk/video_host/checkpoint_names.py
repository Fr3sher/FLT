"""Named checkpoint names operations shared with the host; no module handle escapes."""

def group_saves_by_step(*args, **kwargs):
    from app.services.checkpoint_names import group_saves_by_step
    return group_saves_by_step(*args, **kwargs)


def restage_checkpoint_name(*args, **kwargs):
    from app.services.checkpoint_names import restage_checkpoint_name
    return restage_checkpoint_name(*args, **kwargs)


def split_checkpoint_name(*args, **kwargs):
    from app.services.checkpoint_names import split_checkpoint_name
    return split_checkpoint_name(*args, **kwargs)


from app.services.checkpoint_names import _STAGE_SUFFIXES as STAGE_SUFFIXES  # noqa: E402 — stable value/type identity
from app.services.checkpoint_names import _STEP_RE as STEP_RE  # noqa: E402 — stable value/type identity

__all__ = ['group_saves_by_step', 'restage_checkpoint_name', 'split_checkpoint_name', 'STAGE_SUFFIXES', 'STEP_RE']
