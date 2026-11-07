"""Rollback ordinary in-memory registrations when a plugin entry point raises.

The old API receives Flask itself: restore its routes, callbacks, config and
extension entries, CSRF exemptions and plugin contributions. Arbitrary trusted
Python side effects (files, threads, mutations inside opaque extension objects)
are outside this transaction, as they are outside the plugin trust boundary.
"""
from contextlib import contextmanager
from copy import copy

from .. import config as cfg
from ..engines import registry as engines


def _containers(value):
    """Copy containers while keeping functions, extension instances and locks."""
    if isinstance(value, dict):
        out = copy(value)
        out.clear()
        out.update((key, _containers(item)) for key, item in value.items())
        return out
    if isinstance(value, list):
        return [_containers(item) for item in value]
    if isinstance(value, set):
        return set(value)
    if isinstance(value, tuple):
        return tuple(_containers(item) for item in value)
    return value


@contextmanager
def registration_transaction(app, csrf, registry):
    # Registration is a boot-only operation, before application workers start.
    with cfg._lock:
        defaults = _containers(cfg.DEFAULTS)
    with engines._lock:
        # Preserve the registered specs themselves: their callbacks and opaque
        # metadata are not copied or mutated by the registration API.
        engine_specs = dict(engines._specs)
    fields = ('view_functions', 'blueprints', 'before_request_funcs', 'after_request_funcs',
              'teardown_request_funcs', 'teardown_appcontext_funcs', 'error_handler_spec',
              'url_value_preprocessors', 'url_default_functions', 'template_context_processors',
              'shell_context_processors', 'url_build_error_handlers', 'config', 'extensions')
    snapshot = {name: _containers(getattr(app, name)) for name in fields}
    old_map = app.url_map
    saved_map = type(old_map)([rule.empty() for rule in old_map.iter_rules()], **{
        name: getattr(old_map, name) for name in (
            'default_subdomain', 'strict_slashes', 'redirect_defaults', 'converters',
            'sort_parameters', 'sort_key', 'host_matching', 'merge_slashes')})
    contributions = {name: _containers(value) for name, value in registry.__dict__.items()
                     if name not in ('records', 'invalid', 'misplaced', 'stale', 'dirs')}
    exemptions = {name: set(getattr(csrf, name))
                  for name in ('_exempt_views', '_exempt_blueprints') if hasattr(csrf, name)}
    template = {name: dict(getattr(app.jinja_env, name)) for name in ('filters', 'tests', 'globals')}
    cli_commands = dict(app.cli.commands)
    try:
        yield
    except Exception:
        with cfg._lock:
            cfg.DEFAULTS.clear()
            cfg.DEFAULTS.update(defaults)
            # register(ctx) may have read config after adding defaults/engines.
            # The next reader must merge from the restored catalog and defaults.
            cfg._cache = None
        with engines._lock:
            engines._specs.clear()
            engines._specs.update(engine_specs)
        for name, value in snapshot.items():
            setattr(app, name, value)
        app.url_map = saved_map
        for name, value in contributions.items():
            setattr(registry, name, value)
        for name, value in exemptions.items():
            setattr(csrf, name, value)
        for name, value in template.items():
            setattr(app.jinja_env, name, value)
        app.cli.commands = cli_commands
        raise
