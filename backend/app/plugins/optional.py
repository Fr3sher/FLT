"""Late-bound handles on services that may belong to a plugin the install does not carry.

WHY
---
Measured on 2026-09-04 (``scripts/tests/plugin_partition_probe.py``): with the
cloud-training modules not importable, the app did not boot at all —
``_start_workers`` imported ``cloud_training`` unconditionally — and with the
API image engines not importable, the dataset service failed at import time.
A core file that binds a plugin's module at load time turns "this install does
not have that feature" into "this install does not start".

An :class:`OptionalService` binds the module on FIRST USE instead. The core
module imports, its blueprint registers, and the first call that actually needs
the absent service raises :class:`ServiceUnavailable`, which the app answers
as a 501 with a code the UI can act on (``create_app`` registers the handler,
so every route gets it, wrapped in ``_map_error`` or not).

TWO KINDS OF IMPORT FAILURE, TWO ANSWERS
----------------------------------------
* The module itself is MISSING (``ModuleNotFoundError`` naming it, or one of
  its parent packages): the plugin is not part of this install. Cached, logged
  once at INFO, listed by ``/api/health`` under ``services_unavailable``.
* The module is PRESENT but its import failed (a name it imports was renamed,
  a dependency of its own is gone): that is a bug, not a missing plugin. It is
  logged with its traceback and RE-RAISED, exactly as loudly as the eager
  import used to fail — a broken cloud module must never turn into "cloud
  training is not part of this install" with the run supervisor quietly off.

The handle keeps no public attribute of its own (``available(handle)`` is a
module function), so any name the wrapped module defines is reachable through
it. Attribute writes are forwarded too, so ``monkeypatch.setattr(routes.ct,
'fn', fake)`` patches the real module exactly as it did when ``ct`` was the
module itself. ``bool(handle)`` says whether the service is available, and an
absent service reads as "no such attribute" to ``hasattr``/``getattr``.
"""
from __future__ import annotations

import importlib
import logging
import threading

from ..utils.redact import redact_tokens, redact_user_paths

log = logging.getLogger(__name__)

# qualname -> {'service', 'reason'} for every service found absent in this
# process; /api/health publishes it so a trimmed install can say what it lacks.
_UNAVAILABLE = {}
_REGISTRY_LOCK = threading.Lock()


def _paste_safe(text: str, limit: int = 300) -> str:
    """Diagnostic text stays paste-safe (no user path, no token) — CLAUDE.md."""
    return redact_user_paths(redact_tokens(str(text)))[:limit]


class ServiceUnavailable(RuntimeError, AttributeError):
    """A feature was asked of a service this install does not carry.

    A ``RuntimeError`` so every generic handler that already turns runtime errors
    into a user-facing sentence keeps working, and an ``AttributeError`` so an
    absent service reads as "no such attribute" to ``hasattr``/``getattr``
    with a default. ``create_app`` maps it to 501 ``plugin_unavailable``."""

    def __init__(self, service: str, reason: str):
        self.service = service
        self.reason = reason
        super().__init__(
            f"{service.replace('_', ' ')} is not available in this install ({reason})")


def unavailable_services() -> list:
    """What this process has found absent so far, for /api/health."""
    with _REGISTRY_LOCK:
        return [dict(v) for v in _UNAVAILABLE.values()]


def _is_absence(exc: ImportError, qualname: str) -> bool:
    """True when the module ITSELF (or a parent package) is what is missing —
    not a name it tried to import, not one of its own dependencies."""
    name = getattr(exc, 'name', None)
    if not isinstance(exc, ModuleNotFoundError) or not name:
        return False
    return qualname == name or qualname.startswith(name + '.')


class OptionalService:
    """``app.services.<name>`` resolved on first attribute access.

    Every attribute is read from — or written to — the real module, so a handle
    is a drop-in replacement for ``from ..services import <name> as <alias>``.
    Ask :func:`available` (or ``bool(handle)``) whether the module imports.
    """

    def __init__(self, name: str, package: str = 'app.services'):
        # Private state lives under names no service module defines, seeded
        # with object.__setattr__ so __setattr__ below never sees them.
        object.__setattr__(self, '_os_name', name)
        object.__setattr__(self, '_os_qualname', f'{package}.{name}')
        object.__setattr__(self, '_os_module', None)
        object.__setattr__(self, '_os_absence', None)
        object.__setattr__(self, '_os_lock', threading.Lock())

    def _os_resolve(self):
        module = self._os_module
        if module is not None:
            return module
        with self._os_lock:
            if self._os_module is None and self._os_absence is None:
                qualname = self._os_qualname
                try:
                    object.__setattr__(self, '_os_module', importlib.import_module(qualname))
                except ImportError as exc:
                    if not _is_absence(exc, qualname):
                        # Present but broken: a bug, said with its traceback and
                        # re-raised — never disguised as a missing plugin.
                        log.exception('service %s is present but failed to import — '
                                      'this is a bug, not a missing plugin', qualname)
                        raise
                    reason = _paste_safe(exc)
                    object.__setattr__(self, '_os_absence', reason)
                    log.info('service %s is not part of this install (%s)', qualname, reason)
                    with _REGISTRY_LOCK:
                        _UNAVAILABLE[qualname] = {'service': self._os_name, 'reason': reason}
        if self._os_module is None:
            raise ServiceUnavailable(self._os_name, self._os_absence)
        return self._os_module

    def __getattr__(self, attr):
        return getattr(self._os_resolve(), attr)

    def __setattr__(self, attr, value):
        setattr(self._os_resolve(), attr, value)

    def __delattr__(self, attr):
        delattr(self._os_resolve(), attr)

    def __bool__(self):
        return available(self)

    def __repr__(self):
        if self._os_module is not None:
            state = 'loaded'
        elif self._os_absence is not None:
            state = 'absent'
        else:
            state = 'unbound'
        return f'<OptionalService {self._os_qualname} {state}>'


def available(handle: OptionalService) -> bool:
    """Does the wrapped module import? False only when it is ABSENT; a module
    that is present but broken raises, like any other import bug."""
    try:
        handle._os_resolve()
    except ServiceUnavailable:
        return False
    return True
