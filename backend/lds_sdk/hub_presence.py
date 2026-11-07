"""Named shared operations for hub_presence."""

from app.services.hub_presence import GONE

__all__ = ['check', 'GONE']



def check(repo_id, *, force=False):
    from app.services.hub_presence import check as operation
    return operation(repo_id, force=force)
