"""The engine registry — ONE catalog of the image engines, what every consumer
derives its lists from.

Before this, the facts about an engine were spread over a dozen tables: the
canonical order and the API/local split in the dataset service, the on-disk
filename tag, the labels, the "counts as recommended" set in setup_state, the
tracked capability keys, the key-test target and the key field on the Setup
screen, the per-image rate and the accent colour on the frontend — four
frontend lists that already disagreed (the activity lanes did not know
OpenRouter). A plugin that brings an engine would have had to edit them all.

An :class:`EngineSpec` carries every fact once. The core registers its own
engines (``builtin.py``); a plugin registers more through the façade. Engine
IDS NEVER CHANGE: they are on disk (the filename tag), in the database (a
row's engine) and in localStorage (the workspace selection).

``engines.enabled`` is read as *stored ∩ registered* (:func:`enabled_ids`),
``engines.default`` falls back to the first registered engine when the stored
one is not registered (:func:`default_id`), and the config's "known" ledger
only merges engines the registry knows — so disabling a plugin, saving, and
re-enabling it does not resurrect its engines as "new".
"""
from __future__ import annotations

import threading
from functools import wraps
from dataclasses import dataclass, field
from typing import Callable

API = 'api'
LOCAL = 'local'


@dataclass(frozen=True)
class EngineSpec:
    id: str
    label: str                     # the human name the screens use ("Nano Banana Pro")
    kind: str                      # 'api' | 'local'
    order: int                     # canonical order: cards, primary pick, round-robin
    rate_usd_per_image: float = 0.0
    remote: bool = False           # renders somewhere else: does not hold the local GPU
    billable: bool = False
    secret: str | None = None      # the env / stored secret that lights it up
    key_test_target: str | None = None   # the capability probe "Save & test" runs
    counts_as_recommended: bool = False  # one working engine of these = a set-up install
    tracked_capability: str | None = None  # label of the durable `engines.<id>` check (setup_state)
    file_tag: str | None = None    # filename tag of a generated image (persisted on disk)
    model_setting_key: str | None = None   # `engines.<key>`: the model slug setting
    settings_label: str | None = None      # the wording of the Settings dropdown
    setup_row: dict | None = None  # {'label', 'what', 'topic'} — the counted capability row
    generate: Callable | None = None       # () -> generate_variation(refs, prompt, **kw)
    generate_kwargs: Callable | None = None  # () -> extra kwargs pinned for a run (auth lane)
    probe: Callable | None = None  # () -> {'ok': bool, 'detail': str}
    local_preflight: Callable | None = None  # (**reference facts) -> readiness dict
    local_enqueue: Callable | None = None  # (**shot facts) -> host queue job id
    plugin: str | None = None      # the plugin that registered it, None for the core
    extra: dict = field(default_factory=dict)

    @property
    def is_api(self) -> bool:
        return self.kind == API

    def public(self) -> dict:
        """What ``GET /api/engines`` serves — every fact a screen derives from,
        never a callable."""
        return {
            'id': self.id, 'label': self.label, 'kind': self.kind, 'order': self.order,
            'rate_usd_per_image': self.rate_usd_per_image, 'remote': self.remote,
            'billable': self.billable, 'secret': self.secret,
            'key_test_target': self.key_test_target,
            'counts_as_recommended': self.counts_as_recommended,
            'tracked_capability': self.tracked_capability, 'file_tag': self.file_tag,
            'model_setting_key': self.model_setting_key, 'settings_label': self.settings_label,
            'setup_row': dict(self.setup_row) if self.setup_row else None,
            'plugin': self.plugin,
        }


class DuplicateEngine(ValueError):
    pass


_lock = threading.Lock()
_specs: dict[str, EngineSpec] = {}


def register(spec: EngineSpec, *, replace: bool = False) -> EngineSpec:
    if spec.kind not in (API, LOCAL):
        raise ValueError(f'engine {spec.id!r}: kind must be {API!r} or {LOCAL!r}')
    if spec.local_preflight is not None or spec.local_enqueue is not None:
        if spec.kind != LOCAL or not all(callable(value) for value in
                                        (spec.local_preflight, spec.local_enqueue)):
            raise ValueError('A local dataset engine needs both preflight and enqueue callbacks.')
    with _lock:
        if spec.id in _specs and not replace:
            raise DuplicateEngine(f'engine {spec.id!r} is already registered'
                                  + (f' by plugin {_specs[spec.id].plugin!r}' if _specs[spec.id].plugin else ''))
        _specs[spec.id] = spec
    return spec


def unregister(engine_id: str) -> None:
    with _lock:
        _specs.pop(engine_id, None)


def all_specs() -> tuple[EngineSpec, ...]:
    """Every registered engine, in canonical order (then by id for equal orders)."""
    with _lock:
        return tuple(sorted(_specs.values(), key=lambda s: (s.order, s.id)))


def get(engine_id: str) -> EngineSpec | None:
    with _lock:
        return _specs.get(engine_id)


def ids() -> tuple[str, ...]:
    return tuple(s.id for s in all_specs())


def api_ids() -> tuple[str, ...]:
    return tuple(s.id for s in all_specs() if s.kind == API)


def local_ids() -> tuple[str, ...]:
    return tuple(s.id for s in all_specs() if s.kind == LOCAL)


def labels() -> dict[str, str]:
    return {s.id: s.label for s in all_specs()}


def file_tag(engine_id: str, default: str | None = None) -> str | None:
    spec = get(engine_id)
    return spec.file_tag if spec and spec.file_tag else default


def recommended_ids() -> tuple[str, ...]:
    return tuple(s.id for s in all_specs() if s.counts_as_recommended)


def tracked() -> tuple[tuple[str, str], ...]:
    """``(('engines.<id>', label), …)`` for setup_state's durable checks."""
    return tuple((f'engines.{s.id}', s.tracked_capability) for s in all_specs() if s.tracked_capability)


def generate_fn(engine_id: str):
    spec = require_available(engine_id)
    if spec is None or spec.generate is None:
        raise ValueError(f'unknown edit engine: {engine_id}')
    generate = spec.generate()
    @wraps(generate)
    def admitted(*args, **kwargs):
        require_available(engine_id)
        return generate(*args, **kwargs)
    return admitted


def generate_kwargs(engine_id: str) -> dict:
    """Extra keyword arguments an engine pins for one run (ChatGPT pins its auth
    lane so a mid-batch token refresh can never reroute rows onto the paid key)."""
    spec = require_available(engine_id)
    if spec is None or spec.generate_kwargs is None:
        return {}
    return dict(spec.generate_kwargs() or {})


# --- what the settings mean, read through the registry ---------------------------------
def enabled_ids(stored) -> tuple[str, ...]:
    """``engines.enabled`` as the app must read it: the stored list ∩ the
    registered engines, in canonical order. An EMPTY stored list is a real state
    ("no restriction" downstream) and stays empty."""
    wanted = {e for e in (stored or []) if isinstance(e, str)}
    if not wanted:
        return ()
    return tuple(s.id for s in all_specs() if s.id in wanted)


def default_id(stored, enabled=None) -> str | None:
    """``engines.default`` as the app must read it: the stored id when it is
    registered (and enabled, when a restriction is given), else the first
    enabled engine in canonical order, else the first registered one."""
    candidates = list(enabled) if enabled else list(ids())
    if isinstance(stored, str) and stored in candidates:
        return stored
    return candidates[0] if candidates else None


def probe_for_test_target(target: str):
    """The readiness probe of the engine whose key field tests as `target`
    (`/api/settings/test/<target>`), or None."""
    for spec in all_specs():
        if spec.key_test_target == target and spec.probe is not None:
            return spec.probe
    return None


def probes() -> dict[str, Callable]:
    return {s.id: s.probe for s in all_specs() if s.probe is not None}


def public_catalog() -> list[dict]:
    return [s.public() for s in available_specs()]


def require_available(engine_id):
    from ..auth_policy import plugin_available
    spec = get(engine_id)
    if spec is None or (spec.plugin and not plugin_available(spec.plugin)):
        raise ValueError(f'Image engine {engine_id!r} is unavailable. Enable its plugin and restart LDS.')
    return spec


def available_specs():
    from ..auth_policy import plugin_available
    return tuple(s for s in all_specs() if s.plugin is None or plugin_available(s.plugin))
