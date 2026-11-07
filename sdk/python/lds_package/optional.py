"""Reviewed in-process extras installed explicitly by their owning product."""
from __future__ import annotations

import ast

from packaging.utils import canonicalize_name

from .common import PackageError, portable
from .source import requirements


def optional_profile(config, files, manifest, *, official):
    mappings = config.get('optional_host_dependencies', {})
    if not isinstance(mappings, dict) or len(mappings) > 100:
        raise PackageError('optional_host_dependencies must be an object of at most 100 imports')
    if mappings and not (official and manifest.get('in_process_requirements')):
        raise PackageError('Optional host dependencies require reviewed official in_process_requirements')
    actions = manifest.get('owns', {}).get('install_actions', [])
    result = {}
    for root, spec in mappings.items():
        if (not root.isidentifier() or not isinstance(spec, dict)
                or set(spec) != {'distribution', 'requirements', 'setup_action'}
                or any(not isinstance(value, str) or not value for value in spec.values())):
            raise PackageError('Optional host import needs distribution, requirements and setup_action')
        portable(spec['requirements'])
        if spec['requirements'] not in files or spec['setup_action'] not in actions:
            raise PackageError('Optional dependency needs an included requirements file and owned Setup action')
        reqs = requirements(files[spec['requirements']].decode('utf-8'), spec['requirements'])
        req = reqs.get(canonicalize_name(spec['distribution']))
        if req is None or req.marker or not str(req.specifier):
            raise PackageError('Optional dependency must have an unconditional versioned requirement')
        result[root] = dict(spec, distribution=canonicalize_name(spec['distribution']))
    return result


def deferred_imports(tree):
    """Imports within functions or guarded by an ImportError handler can be absent at boot."""
    allowed = set()

    def handles_import(handler):
        values = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
        return any(isinstance(value, ast.Name) and value.id in {'ImportError', 'ModuleNotFoundError'}
                   for value in values)

    def visit(node, optional=False):
        if isinstance(node, (ast.Import, ast.ImportFrom)) and optional:
            allowed.add(node)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Decorators and defaults execute at definition time; only the body is deferred.
            for child in node.body:
                visit(child, True)
            return
        if isinstance(node, ast.Try):
            guarded = optional or any(handles_import(handler) for handler in node.handlers)
            for child in node.body:
                visit(child, guarded)
            for child in [*node.handlers, *node.orelse, *node.finalbody]:
                visit(child, optional)
            return
        for child in ast.iter_child_nodes(node):
            visit(child, optional)

    visit(tree)
    return allowed
