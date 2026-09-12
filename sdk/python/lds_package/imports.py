"""Conservative static import profile, not a sandbox or a malicious-code detector."""
from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path, PurePosixPath

from packaging.utils import canonicalize_name
from packaging.specifiers import SpecifierSet
from packaging.version import InvalidVersion, Version

from .common import MAX_CODE_BYTES, PackageError, portable
from .source import requirements
from .optional import deferred_imports, optional_profile
from .bootstrap import local_bootstrap_nodes

DYNAMIC_NAMES = {'__import__', '__builtins__', '__loader__', '__spec__', 'eval', 'exec', 'compile'}
DYNAMIC_MODULES = {'importlib', 'runpy', 'pkgutil', 'builtins', '__builtin__'}
PRIVATE_ROOTS = {'app', 'backend', 'frontend', 'bundled', 'plugins', 'tests'}


def _declares_api_minimum(specifier, minimum):
    """The authoring profile requires an explicit lower bound, not a sampled point.

    Excluding a release (for example !=1.5) cannot prove that older APIs are
    excluded. Equality/wildcard and compatible-release pins also define a floor.
    """
    for spec in SpecifierSet(specifier):
        if spec.operator not in {'>=', '>', '~=', '==', '==='}:
            continue
        try:
            floor = Version(spec.version.removesuffix('.*'))
        except InvalidVersion:
            continue
        if floor >= Version(minimum):
            return True
    return False


def _module_file(module, files):
    name = module.replace('.', '/')
    return name + '.py' in files or name + '/__init__.py' in files


def _chain(node):
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, ast.Attribute):
        base = _chain(node.value)
        return base + [node.attr] if base else []
    return []


def _script_config(config, files, manifest):
    if any(key not in {'python_scripts', 'python_shared_modules', 'python_dependencies', 'python_requirements', 'optional_host_dependencies'} for key in config):
        raise PackageError('lds-package.json: unknown field')
    scripts = config.get('python_scripts', [])
    shared = config.get('python_shared_modules', [])
    mappings = config.get('python_dependencies', {})
    if (not isinstance(scripts, list) or any(not isinstance(s, str) for s in scripts)
            or len(scripts) != len(set(scripts)) or not isinstance(mappings, dict)
            or not isinstance(shared, list) or any(not isinstance(s, str) for s in shared)
            or len(shared) != len(set(shared))):
        raise PackageError('lds-package.json: invalid python_scripts/python_dependencies')
    if set(scripts) & set(shared):
        raise PackageError('Python scripts and shared modules must be disjoint')
    for path in scripts + shared:
        portable(path)
        if path not in files or not path.endswith('.py'):
            raise PackageError(f'Declared Python script/shared module is absent: {path}')
        if path == str(manifest.get('python_package')) + '/__init__.py':
            raise PackageError('The backend entry point cannot be isolated or shared')
    for root, dist in mappings.items():
        if (not isinstance(root, str) or not root.isidentifier() or not isinstance(dist, str)
                or not dist.strip()):
            raise PackageError('python_dependencies must map import roots to distribution names')
    req_path = config.get('python_requirements', manifest.get('requirements'))
    if req_path:
        portable(req_path)
        if req_path not in files:
            raise PackageError('Isolated Python requirements are absent from the package')
    reqs = requirements(files[req_path].decode('utf-8'), req_path) if req_path else {}
    for dist in mappings.values():
        req = reqs.get(canonicalize_name(dist))
        if req is None or req.marker or not str(req.specifier):
            raise PackageError(f'Isolated dependency must be unconditional in requirements with version bounds: {dist}')
    return set(scripts), set(shared), mappings


def audit_python(files, manifest, config, host, *, official=False):
    scripts, shared_modules, mappings = _script_config(config, files, manifest)
    optional = optional_profile(config, files, manifest, official=official)
    package = manifest.get('python_package')
    used_host, used_private, used_optional = {}, set(), set()
    for path, content in files.items():
        if not path.endswith('.py'):
            continue
        isolated = path in scripts
        shared = path in shared_modules
        if not isolated and not shared and (not package or not path.startswith(package + '/')):
            raise PackageError(f'{path}: Python must belong to python_package or explicit python_scripts')
        if len(content) > MAX_CODE_BYTES:
            raise PackageError(f'{path}: Python source exceeds the audit limit')
        try:
            tree = ast.parse(content, filename=path)
        except (SyntaxError, ValueError) as exc:
            raise PackageError(f'{path}: invalid Python source') from exc
        aliases = {}
        deferred = deferred_imports(tree)
        shared_imports = {PurePosixPath(name).stem for name in shared_modules
                          if PurePosixPath(name).parent == PurePosixPath(path).parent}
        bootstrap = local_bootstrap_nodes(tree, shared_imports=shared_imports) if isolated else set()

        def fail(node, message):
            raise PackageError(f'{path}:{node.lineno}: {message}')

        def module_ok(module, node):
            root = module.split('.')[0]
            if root in PRIVATE_ROOTS:
                fail(node, 'private LDS imports are forbidden; use lds_sdk')
            if root in DYNAMIC_MODULES:
                fail(node, 'dynamic module loading is outside the auditable package profile')
            direct = {module.replace('.', '/') + suffix for suffix in ('.py', '/__init__.py')}
            local = str(PurePosixPath(path).parent / module.replace('.', '/'))
            nearby = {local + suffix for suffix in ('.py', '/__init__.py')}
            if direct & shared_modules or ((isolated or shared) and nearby & shared_modules):
                return
            if shared:
                if root in sys.stdlib_module_names:
                    return
                fail(node, 'shared Python modules can only import stdlib or declared shared modules')
            if root == 'lds_sdk':
                if isolated or module not in host.sdk:
                    fail(node, f'unsupported public SDK module: {module}')
                return
            if root == package and _module_file(module, files):
                if module.replace('.', '/') + '.py' in scripts or module.replace('.', '/') + '/__init__.py' in scripts:
                    if not isolated:
                        fail(node, 'backend cannot import an isolated Python script')
                    return
                if isolated:
                    fail(node, 'isolated scripts cannot import the in-process backend package')
                return
            if root in sys.stdlib_module_names:
                return
            if isolated:
                if local + '.py' in scripts or local + '/__init__.py' in scripts:
                    return
                if root in mappings:
                    used_private.add(root)
                    return
                fail(node, f'isolated import requires python_dependencies and requirements: {root}')
            if root in host.host_imports:
                dist = host.host_imports[root]
                used_host[canonicalize_name(dist)] = str(host.host_requirements[canonicalize_name(dist)].specifier)
                return
            if root in optional:
                if node not in deferred:
                    fail(node, f'optional host import must be lazy or handle ImportError at boot: {root}')
                used_optional.add(root)
                return
            fail(node, f'backend dependency is not guaranteed by the host SDK: {root}; '
                 'plugin venv requirements do not extend the host process')

        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == 'register_restore_engine'
                    and not _declares_api_minimum(manifest['compatibility']['api'], '1.9')):
                fail(node, 'Image restoration providers require compatibility.api >=1.9')
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr in {'register_data_migration', 'register_health_check'}
                    and not _declares_api_minimum(manifest['compatibility']['api'], '1.6')):
                fail(node, f'{node.func.attr} requires compatibility.api >=1.6')
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == 'register_model_download'
                    and any(k.arg in {'companions', 'complete', 'extra_roots'} for k in node.keywords)
                    and not _declares_api_minimum(manifest['compatibility']['api'], '1.8')):
                fail(node, 'Model companions/completeness require compatibility.api >=1.8')
            if isinstance(node, ast.Import):
                for item in node.names:
                    module_ok(item.name, node)
                    aliases[item.asname or item.name.split('.')[0]] = item.name if item.asname else item.name.split('.')[0]
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    parts = list(PurePosixPath(path).parent.parts)
                    if node.level > len(parts):
                        fail(node, 'relative import escapes the Python package')
                    base = parts[:len(parts) - node.level + 1]
                    module = '.'.join(base + (node.module.split('.') if node.module else []))
                    if not _module_file(module, files):
                        fail(node, f'missing local Python module: {module}')
                    if not isolated and not shared and module.split('.')[0] != package:
                        fail(node, 'relative import escapes the backend package')
                    if shared:
                        candidates = [module] if node.module else [module + '.' + item.name for item in node.names]
                        if any(not any(candidate.replace('.', '/') + suffix in shared_modules
                                       for suffix in ('.py', '/__init__.py')) for candidate in candidates):
                            fail(node, 'shared Python modules can only import declared shared modules')
                    elif not isolated:
                        candidates = [module] + [module + '.' + item.name for item in node.names]
                        if any(candidate.replace('.', '/') + suffix in scripts
                               for candidate in candidates for suffix in ('.py', '/__init__.py')):
                            fail(node, 'backend cannot import an isolated Python script')
                    else:
                        candidates = [module] if node.module else [module + '.' + item.name for item in node.names]
                        if any(not any(candidate.replace('.', '/') + suffix in scripts | shared_modules for suffix in ('.py', '/__init__.py'))
                               for candidate in candidates):
                            fail(node, 'isolated scripts can only import explicitly listed Python helpers')
                    continue
                module = node.module or ''
                module_ok(module, node)
                for item in node.names:
                    full = module + '.' + item.name
                    if module.split('.')[0] == package and _module_file(full, files):
                        module_ok(full, node)
                    if module.startswith('lds_sdk'):
                        if full in host.sdk:
                            aliases[item.asname or item.name] = full
                        elif item.name not in host.sdk[module]:
                            fail(node, f'non-public SDK export: {full}')
                    elif item.name == '*':
                        fail(node, 'wildcard imports are outside the auditable package profile')
                    if module == 'sys' and item.name in {'modules', 'path', 'meta_path', 'path_hooks'}:
                        fail(node, 'runtime import path/module manipulation is forbidden')
        # Follow simple aliases as well as direct dotted SDK accesses.
        for _ in range(3):
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign) and isinstance(node.value, ast.Name) and node.value.id in aliases:
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            aliases[target.id] = aliases[node.value.id]
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id in DYNAMIC_NAMES:
                fail(node, 'dynamic code/import execution is outside the auditable package profile')
            # Object methods such as re.compile() and torch_model.eval() do not
            # execute Python source. Builtin dynamic calls and module reflection
            # remain rejected separately; this is a static profile, not a sandbox.
            if isinstance(node, ast.Attribute) and node.attr in {
                    '__import__', '__builtins__', '__loader__', '__spec__', '__globals__'}:
                fail(node, 'reflective code/import execution is outside the auditable package profile')
            chain = _chain(node)
            if chain and chain[0] in aliases:
                full = aliases[chain[0]].split('.') + chain[1:]
                if (full[0] == 'sys' and len(full) > 1 and full[1] in {'modules', 'path', 'meta_path', 'path_hooks'}
                        and node not in bootstrap):
                    fail(node, 'runtime import path/module manipulation is forbidden')
                if full[0] == 'lds_sdk':
                    for end in range(2, len(full) + 1):
                        prefix, name = '.'.join(full[:end - 1]), full[end - 1]
                        if '.'.join(full[:end]) not in host.sdk and name not in host.sdk.get(prefix, set()):
                            fail(node, f'non-public SDK access: {".".join(full[:end])}')
                        if name in host.sdk.get(prefix, set()) and '.'.join(full[:end]) not in host.sdk:
                            # The export is an object/value, not another module.
                            # Its public methods belong to the documented API.
                            if any(part.startswith('_') for part in full[end:]):
                                fail(node, 'non-public SDK object access')
                            break
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {'getattr', 'vars'}:
                if node.args and _chain(node.args[0]) and _chain(node.args[0])[0] in aliases:
                    module = aliases[_chain(node.args[0])[0]]
                    attribute = node.args[1].value if len(node.args) > 1 and isinstance(node.args[1], ast.Constant) else None
                    safe_constant = (node.func.id == 'getattr' and module.split('.')[0] in sys.stdlib_module_names
                                     and isinstance(attribute, str) and not attribute.startswith('_')
                                     and attribute not in DYNAMIC_NAMES | {'modules', 'path', 'meta_path', 'path_hooks'})
                    if not safe_constant:
                        fail(node, 'reflective module access is outside the auditable package profile')
    unused = set(mappings) - used_private
    if unused:
        raise PackageError('Unused isolated dependency mappings: ' + ', '.join(sorted(unused)))
    if set(optional) - used_optional:
        raise PackageError('Unused optional host dependency mappings: ' + ', '.join(sorted(set(optional) - used_optional)))
    return {'host_dependencies': dict(sorted(used_host.items())),
            'optional_host_dependencies': dict(sorted(optional.items())),
            'isolated_dependencies': dict(sorted(mappings.items())), 'python_scripts': sorted(scripts),
            'python_shared_modules': sorted(shared_modules)}


def audit_javascript(files, js_tools=None, *, workers=()):
    scripts = {path: data.decode('utf-8') for path, data in files.items() if path.endswith(('.js', '.mjs'))}
    if any(path.endswith(('.jsx', '.tsx', '.ts', '.cjs')) for path in files):
        raise PackageError('Ship built ESM JavaScript, not JSX/TypeScript/CommonJS sources')
    if not scripts:
        return
    if any(len(code.encode('utf-8')) > MAX_CODE_BYTES for code in scripts.values()):
        raise PackageError('JavaScript source exceeds the audit limit')
    tools = Path(js_tools or os.environ.get('LDS_PLUGIN_JS_TOOLS') or Path(__file__).resolve().parents[1]).resolve()
    helper = Path(__file__).resolve().parents[1] / 'audit-js.mjs'
    try:
        result = subprocess.run(['node', str(helper), str(tools)], input=json.dumps({'scripts': scripts, 'files': list(files),
                                                                                  'workers': list(workers)}),
                                capture_output=True, text=True, encoding='utf-8', timeout=45, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PackageError('JavaScript audit requires Node and installed Acorn tooling (--js-tools)') from exc
    if result.returncode:
        # Only the owned helper generates diagnostics; plugin code is never run.
        raise PackageError(result.stdout.strip() or 'JavaScript audit failed; check Node/Acorn tooling')
