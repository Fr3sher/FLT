"""The two image generation engines that remain in the public core."""
from .registry import EngineSpec, LOCAL, get, register


def register_builtin():
    for spec in (
        EngineSpec(id='klein', label='Klein', kind=LOCAL, order=0,
                   counts_as_recommended=True, tracked_capability='Klein (local)'),
        EngineSpec(id='krea', label='Krea 2 Edit', kind=LOCAL, order=1,
                   tracked_capability='Krea 2 Edit (local)'),
    ):
        if get(spec.id) is None:
            register(spec)
