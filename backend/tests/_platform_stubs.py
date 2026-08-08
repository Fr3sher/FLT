"""Pretend to be another platform WITHOUT mutating the real ``os``/``sys``.

``monkeypatch.setattr(os, 'name', 'posix')`` on Windows does not just change
what the code under test reads -- it changes what the whole interpreter reads.
``pathlib`` picks its flavour from ``os.name``, so while such a patch is live,
``Path.relative_to`` compares two IDENTICAL Windows paths and raises
``ValueError: '<p>' is not in the subpath of '<p>'``.

Sequentially that stays invisible: nothing in the session builds a relative
path between the test's start and its teardown. Under ``pytest-xdist`` it is
fatal. The worker serialises its report for each test through
``_pytest.pathlib.bestrelpath`` -> ``Path.relative_to`` while the patch is
STILL applied, so the worker dies with an INTERNALERROR and takes the whole
session with it -- measured: ~4600 of 7151 tests ran, and the count moved
between runs because it depends on which worker got there first. Two hours of
"xdist is flaky" that were nothing of the sort.

Overriding the module reference the code under test resolves through keeps the
assertions exactly as they were and leaves the interpreter's own modules alone.
Every attribute that is not overridden is delegated to the real module, so a
function that also reaches for ``os.environ`` or ``os.path`` keeps working.
"""
from __future__ import annotations


class ModuleWithOverrides:
    """The real ``module``, with ``overrides`` shadowing some attributes."""

    def __init__(self, module, **overrides):
        # Set first: __getattr__ below reads _module, so it must exist before
        # any delegated lookup can happen.
        self.__dict__['_module'] = module
        self.__dict__.update(overrides)

    def __getattr__(self, attr):
        # Only reached when the attribute is not an override.
        return getattr(self._module, attr)

    def __repr__(self):
        overrides = {k: v for k, v in self.__dict__.items() if k != '_module'}
        return f'<{self._module.__name__} with {overrides}>'
