"""Shared disk capacity and reversible trash operations."""
from app.services.trash import TrashLockError

__all__ = ['free_space', 'send_to_trash', 'TrashLockError']


def free_space(path):
    from app.services.storage_locations import free_space as operation
    return operation(path)


def send_to_trash(path, context=''):
    from app.services.trash import send_to_trash as operation
    return operation(path, context=context)
