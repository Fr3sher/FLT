"""Bounded persistence for the two historical Model tools job records.

This is not a handle to the queue manager. It exposes neither admission nor
other system records, and preserves the existing keys across plugin migration.
"""

__all__ = ['ModelToolState', 'CloudState']


class ModelToolState:
    _keys = frozenset({'fp8_quantize', 'lora_merge'})

    def _check(self, key):
        if key not in self._keys:
            raise ValueError('This state record does not belong to Model tools.')

    def get(self, key, default=None):
        self._check(key)
        from app.job_queue import queue_manager
        return queue_manager._get_system_state(key, default)

    def set(self, key, value, *, ttl_seconds=None):
        self._check(key)
        from app.job_queue import queue_manager
        return queue_manager._set_system_state(key, value, ttl_seconds=ttl_seconds)

    # Compatibility for existing in-repository fixture setup. Plugin production
    # code uses get/set; these names do not expose the rest of the host manager.
    _get_system_state = get
    _set_system_state = set


class CloudState:
    """Cloud's existing keys, including raw legacy clocks and transfer samples."""
    _keys = frozenset({'cloud_quantize', 'cloud_quantize_rentals', 'dense_comfy_send',
                      'fp8_local_delivery', 'live_pod', 'cloud_uplink_samples'})

    def _check(self, key):
        import re
        if (key not in self._keys
                and not re.fullmatch(r'cloud_progress_watch:[1-9][0-9]*', str(key))
                and not re.fullmatch(r'cloud_rental_absence\.[a-f0-9]{64}', str(key))):
            raise ValueError('This state record does not belong to Cloud.')

    def get(self, key, default=None):
        self._check(key)
        from app.job_queue import queue_manager
        return queue_manager._get_system_state(key, default)

    def set(self, key, value, *, ttl_seconds=None):
        self._check(key)
        from app.job_queue import queue_manager
        return queue_manager._set_system_state(key, value, ttl_seconds=ttl_seconds)

    def read_raw(self, key):
        self._check(key)
        from app.extensions import db
        from app.models import SystemState
        row = db.session.get(SystemState, key)
        return row.value if row is not None else None

    def write_raw(self, key, value):
        self._check(key)
        from app.extensions import db
        from app.models import SystemState
        row = db.session.get(SystemState, key)
        if value is None:
            if row is not None:
                db.session.delete(row)
        elif row is None:
            db.session.add(SystemState(key=key, value=value))
        else:
            row.value = value
        db.session.commit()

    _get_system_state = get
    _set_system_state = set
