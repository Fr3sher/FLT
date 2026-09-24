"""The two image generation engines that remain in the public core."""
from .registry import EngineSpec, LOCAL, get, register


def register_builtin():
    # Readiness follows the local daemon; it is not a durable installation check.
    for spec in (
        EngineSpec(id='klein', label='Klein', kind=LOCAL, order=0,
                   counts_as_recommended=True),
        EngineSpec(id='krea', label='Krea 2 Edit', kind=LOCAL, order=1),
    ):
        if get(spec.id) is None:
            register(spec)
