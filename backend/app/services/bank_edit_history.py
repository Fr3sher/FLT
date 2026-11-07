"""Retain the inputs of bank crops/upscales without copying their pixels."""
import json
import os
from types import SimpleNamespace

from . import bank_transfer_metadata


STATE_FIELDS = ('edit_method', 'edit_generation', 'edit_baked_rotation',
                'rotation', 'width', 'height')


def history(row):
    try:
        value = json.loads(row.edit_history or '[]')
    except (ValueError, TypeError):
        return []
    return value if isinstance(value, list) else []


def next_generation(row):
    return max(int(row.edit_sequence or 0), int(row.edit_generation or 0)) + 1


def snapshot(row, source):
    """Capture the input before processing; external folders can change."""
    state = {key: getattr(row, key) for key in STATE_FIELDS}
    state['fingerprint'] = bank_transfer_metadata.content_fingerprint_path(source)
    return state


def remember(row, state):
    """Publish a captured input only once its new edited blob succeeds."""
    row.edit_history = json.dumps([*history(row), state])


def previous_path(bank, row):
    """Fail closed: never label a missing crop or changed source as 'Before'."""
    from . import image_bank_service as banks

    states = history(row)
    if not states:
        return None
    state = states[-1]
    if state.get('edit_method'):
        path = str(banks.edited_image_path(bank.id, row.id, state['edit_generation']))
    else:
        previous = SimpleNamespace(**{c.name: getattr(row, c.name)
                                      for c in row.__table__.columns})
        for key in STATE_FIELDS:
            setattr(previous, key, state.get(key))
        path = banks.resolved_image_path(bank, previous)
    if not path or not os.path.isfile(path):
        return None
    fingerprint = bank_transfer_metadata.content_fingerprint_path(path)
    return path if fingerprint and fingerprint == state.get('fingerprint') else None


def availability(row):
    states = history(row)
    return {'edit_history_count': len(states),
            'edit_sequence': int(row.edit_sequence or 0)}


def prune(bank_id, row):
    from . import image_bank_service as banks

    keep = {banks.edited_image_path(bank_id, row.id, s['edit_generation'])
            for s in history(row) if s.get('edit_method')}
    if row.edit_method:
        keep.add(banks.edited_image_path(bank_id, row.id, row.edit_generation))
    banks._prune_edited_generations(bank_id, row.id, None, retained=keep)
