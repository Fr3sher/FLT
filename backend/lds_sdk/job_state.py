"""Bounded persistence for the two historical Model tools job records.

This is not a handle to the queue manager. It exposes neither admission nor
other system records, and preserves the existing keys across plugin migration.
"""


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


__all__ = ['ModelToolState']
