"""Versioned package metadata and compatibility, without importing plugin code.

The existing manifest parser owns base fields and plugin identity. This module
adds the v2 package contract; declaring a publisher never grants that identity
any trust. Legacy manifests keep their existing admission rules.
"""
from __future__ import annotations

import re

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

_PUBLISHER_ID = re.compile(r'[a-z][a-z0-9_]{1,31}')
_PLUGIN_ID = re.compile(r'[a-z][a-z0-9_]{1,31}(?:\.[a-z][a-z0-9_]{1,31})?')
_COMPATIBILITY_KEYS = frozenset({'lds', 'api', 'python', 'os', 'arch'})
_SYSTEMS = frozenset({'windows', 'linux', 'darwin'})
_ARCHITECTURES = frozenset({'x86_64', 'arm64'})
NATIVE_BACKEND_SUFFIX = '.cp312-win_amd64.pyd'
_WINDOWS_DEVICES = frozenset({'con', 'prn', 'aux', 'nul'} |
                              {f'{prefix}{number}' for prefix in ('com', 'lpt') for number in range(1, 10)})


class PackageContractError(ValueError):
    """An invalid declaration, distinct from a valid but incompatible package."""

    def __init__(self, field: str, message: str):
        self.field, self.message = field, message
        super().__init__(f'{field}: {message}')


def _object(value, field, allowed):
    if not isinstance(value, dict):
        raise PackageContractError(field, 'must be an object')
    if any(key not in allowed for key in value):
        raise PackageContractError(field, 'contains an unknown field')
    return value


def _text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise PackageContractError(field, 'must be a non-empty string')
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise PackageContractError(field, 'must not contain control characters')
    return value.strip()


def _specifier(value, field):
    value = _text(value, field)
    try:
        normalized = str(SpecifierSet(value))
    except InvalidSpecifier as exc:
        raise PackageContractError(field, 'must be a PEP 440 version specifier') from exc
    if not normalized:
        raise PackageContractError(field, 'must contain at least one PEP 440 version constraint')
    return normalized


def _choices(value, field, allowed):
    if not isinstance(value, list) or not value:
        raise PackageContractError(field, 'must be a non-empty list')
    if any(not isinstance(item, str) or item not in allowed for item in value):
        raise PackageContractError(field, 'contains an unsupported value')
    if len(value) != len(set(value)):
        raise PackageContractError(field, 'must not contain duplicates')
    return list(value)


def _style_path(value, field):
    normalized = _text(value, field)
    if normalized != value:
        raise PackageContractError(field, 'must not have surrounding whitespace')
    # Canonical forward slashes make the same archive work on every platform.
    path = value.replace('\\', '/')
    parts = path.split('/')
    if (any(char in path for char in ':?#%<>"|*')
            or any(part in ('', '.', '..') or part.endswith((' ', '.'))
                   or part.split('.', 1)[0].lower() in _WINDOWS_DEVICES for part in parts)
            or not path.endswith('.css')):
        raise PackageContractError(field, 'must be a portable relative .css path inside the plugin')
    return path


def validate_contract(data: dict) -> dict:
    """Normalize only package metadata; base manifest validation stays separate.

    Missing schema_version and explicit v1 ignore v2 metadata. V2 requires an
    explicit publisher and all five compatibility axes. Returns fresh containers
    and never mutates the supplied manifest.
    """
    if not isinstance(data, dict):
        raise PackageContractError('plugin.json', 'must be an object')
    version = data.get('schema_version', 1)
    if type(version) is not int or version not in (1, 2):
        raise PackageContractError('schema_version', 'must be integer 1 or 2')
    result = {'schema_version': version, 'publisher': None, 'compatibility': {},
              'dependency_versions': {}, 'frontend_styles': [], 'data_schema': 1}
    if version == 1:
        if 'native_backend' in data:
            raise PackageContractError('native_backend', 'requires schema_version 2')
        return result

    if 'experience' in data:
        result['experience'] = _experience(data['experience'])
    result['frontend_workers'] = _frontend_workers(data.get('frontend_workers', []))

    host_dependencies = data.get('host_dependencies', {})
    if not isinstance(host_dependencies, dict) or len(host_dependencies) > 100:
        raise PackageContractError('host_dependencies', 'must map distribution names to version constraints')
    result['host_dependencies'] = {}
    for name, specifier in host_dependencies.items():
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?', name):
            raise PackageContractError('host_dependencies', 'contains an invalid distribution name')
        normalized = canonicalize_name(name)
        if normalized in result['host_dependencies']:
            raise PackageContractError('host_dependencies', 'contains duplicate distribution names')
        result['host_dependencies'][normalized] = _specifier(specifier, f'host_dependencies.{normalized}')

    publisher = _object(data.get('publisher'), 'publisher', {'id', 'name'})
    publisher_id = _text(publisher.get('id'), 'publisher.id')
    if not _PUBLISHER_ID.fullmatch(publisher_id):
        raise PackageContractError('publisher.id', 'must use 2-32 lowercase letters, digits or underscores, starting with a letter')
    result['publisher'] = {'id': publisher_id, 'name': _text(publisher.get('name'), 'publisher.name')}

    compatibility = _object(data.get('compatibility'), 'compatibility', _COMPATIBILITY_KEYS)
    if set(compatibility) != _COMPATIBILITY_KEYS:
        raise PackageContractError('compatibility', 'must declare lds, api, python, os and arch')
    result['compatibility'] = {key: _specifier(compatibility[key], f'compatibility.{key}')
                               for key in ('lds', 'api', 'python')}
    result['compatibility']['os'] = _choices(compatibility['os'], 'compatibility.os', _SYSTEMS)
    result['compatibility']['arch'] = _choices(compatibility['arch'], 'compatibility.arch', _ARCHITECTURES)
    if 'native_backend' in data:
        result['native_backend'] = _native_backend(data, result['compatibility'])

    requires = data.get('requires', [])
    if (not isinstance(requires, list)
            or any(not isinstance(item, str) or not _PLUGIN_ID.fullmatch(item) for item in requires)
            or len(requires) != len(set(requires))):
        raise PackageContractError('requires', 'must be a list of distinct plugin ids')
    dependencies = data.get('dependency_versions', {})
    if not isinstance(dependencies, dict):
        raise PackageContractError('dependency_versions', 'must be an object')
    for plugin_id, specifier in dependencies.items():
        if not isinstance(plugin_id, str) or plugin_id not in requires:
            raise PackageContractError('dependency_versions', 'every versioned dependency must also appear in requires')
        result['dependency_versions'][plugin_id] = _specifier(specifier, f'dependency_versions.{plugin_id}')

    styles = data.get('frontend_styles', [])
    if not isinstance(styles, list):
        raise PackageContractError('frontend_styles', 'must be a list of relative .css paths')
    result['frontend_styles'] = [_style_path(value, f'frontend_styles[{index}]')
                                 for index, value in enumerate(styles)]
    # Case-insensitive duplicate detection keeps Windows and Linux equivalent.
    folded = [path.casefold() for path in result['frontend_styles']]
    if len(set(folded)) != len(folded):
        raise PackageContractError('frontend_styles', 'must not contain duplicate paths')
    data_schema = data.get('data_schema', 1)
    if type(data_schema) is not int or data_schema < 1:
        raise PackageContractError('data_schema', 'must be a positive integer')
    result['data_schema'] = data_schema
    return result


def _native_backend(data, compatibility):
    """The initial native profile is deliberately one CPython/OS/architecture.

    This is compatibility metadata, never installation authority or proof of a
    source audit. Existing Store signatures and provenance still own admission.
    """
    expected = {'kind': 'cpython-extension', 'implementation': 'cpython', 'cache_tag': 'cpython-312'}
    native = _object(data['native_backend'], 'native_backend', {*expected, 'entry'})
    if any(native.get(key) != value for key, value in expected.items()):
        raise PackageContractError('native_backend', 'must describe a CPython 3.12 extension')
    package = data.get('python_package')
    if not isinstance(package, str) or not re.fullmatch(r'[a-z_][a-z0-9_]{0,63}', package):
        raise PackageContractError('native_backend', 'requires a valid python_package')
    entry = package + NATIVE_BACKEND_SUFFIX
    if native.get('entry') != entry:
        raise PackageContractError('native_backend.entry', 'must be python_package followed by ' + NATIVE_BACKEND_SUFFIX)
    if (compatibility['os'] != ['windows'] or compatibility['arch'] != ['x86_64']
            or SpecifierSet(compatibility['python']) != SpecifierSet('>=3.12,<3.13')):
        raise PackageContractError('native_backend', 'requires Windows x86_64 and compatibility.python >=3.12,<3.13')
    api = SpecifierSet(compatibility['api'])
    # A positive floor is necessary: merely excluding one older release does
    # not keep other hosts that ignore this new field from selecting it.
    if not any(spec.operator in {'>=', '>', '~=', '=='}
               and Version(spec.version.removesuffix('.*')) >= Version('1.19') for spec in api):
        raise PackageContractError('native_backend', 'requires an explicit compatibility.api floor >=1.19')
    return {**expected, 'entry': entry}


def _frontend_workers(value):
    if not isinstance(value, list) or len(value) > 10:
        raise PackageContractError('frontend_workers', 'must be a list of at most ten worker declarations')

    def js_path(path):
        if not isinstance(path, str) or not path.endswith(('.js', '.mjs')):
            raise PackageContractError('frontend_workers', 'entries and loaders must name built JavaScript files')
        # Reuse the strict portable path grammar without accepting a CSS entry.
        return _style_path(path + '.css', 'frontend_workers')[:-4]

    output = []
    for item in value:
        item = _object(item, 'frontend_workers', {'entry', 'loaders'})
        loaders = item.get('loaders')
        if not isinstance(loaders, list) or not 1 <= len(loaders) <= 20:
            raise PackageContractError('frontend_workers', 'each worker must declare its loader files')
        paths = [js_path(path) for path in loaders]
        if len({path.casefold() for path in paths}) != len(paths):
            raise PackageContractError('frontend_workers', 'duplicate loader path')
        output.append({'entry': js_path(item.get('entry')), 'loaders': paths})
    entries = [item['entry'].casefold() for item in output]
    if len(set(entries)) != len(entries) or any(path.casefold() in entries for item in output for path in item['loaders']):
        raise PackageContractError('frontend_workers', 'worker entries must be unique and distinct from loaders')
    return output


def _experience(value):
    value = _object(value, 'experience', {'entrypoints', 'setup', 'setup_hint', 'surfaces'})

    def link(item):
        item = _object(item, 'experience link', {'label', 'path'})
        label = _text(item.get('label'), 'experience link label')
        path = _text(item.get('path'), 'experience link path')
        if (len(label) > 100 or len(path) > 300 or not path.startswith('/') or path.startswith('//')
                or any(char in path for char in '\\%#:') or '..' in path.split('?')[0].split('/')):
            raise PackageContractError('experience', 'links must use local application routes')
        return {'label': label, 'path': path}

    entries = value.get('entrypoints', [])
    if not isinstance(entries, list) or not 1 <= len(entries) <= 5:
        raise PackageContractError('experience.entrypoints', 'must name one to five product entry points')
    result = {'entrypoints': [link(item) for item in entries]}
    if value.get('setup') is not None:
        result['setup'] = link(value['setup'])
    if value.get('setup_hint') is not None:
        hint = _text(value['setup_hint'], 'experience.setup_hint')
        if len(hint) > 1000:
            raise PackageContractError('experience.setup_hint', 'must be at most 1000 characters')
        result['setup_hint'] = hint
    surfaces = value.get('surfaces', [])
    if not isinstance(surfaces, list) or len(surfaces) > 10:
        raise PackageContractError('experience.surfaces', 'must be a short list')
    result['surfaces'] = [_text(item, 'experience.surfaces') for item in surfaces]
    return result


def _issue(code, field, message, expected, actual):
    return {'code': code, 'field': field, 'message': message, 'expected': expected, 'actual': actual}


def _version_issue(value, specifier, field, label):
    try:
        if not isinstance(value, str) or not value.strip():
            raise InvalidVersion('not a version string')
        version = Version(value)
    except InvalidVersion:
        return _issue('invalid_version', field, f'The installed {label} version cannot be verified.', specifier,
                      value if isinstance(value, (str, int, float, bool, type(None))) else None)
    spec = SpecifierSet(specifier)
    # Stable ranges do not silently admit pre-release hosts/dependencies. Do
    # not rely on packaging's default, which differs between versions.
    if not spec.contains(version, prereleases=spec.prereleases is True):
        return _issue('version_mismatch', field, f'This plugin requires {label} {specifier}; installed version is {version}.',
                      specifier, str(version))
    return None


def compatibility_issues(contract: dict, *, lds_version, api_version, python_version,
                         system, machine, dependencies=None, host_dependencies=None,
                         python_implementation=None, python_cache_tag=None, pointer_bits=None) -> list[dict]:
    """Compare normalized metadata with the actual host before importing code.

    dependencies=None defers dependency checks until a complete registry exists.
    A supplied map is authoritative: an absent versioned dependency is an issue.
    A legacy contract adds no restrictions to the original manifest rules.
    """
    if not isinstance(contract, dict) or type(contract.get('schema_version')) is not int:
        raise PackageContractError('contract', 'must be normalized package metadata')
    if contract['schema_version'] == 1:
        return []
    if contract['schema_version'] != 2:
        raise PackageContractError('schema_version', 'must be integer 1 or 2')
    compatibility = contract['compatibility']
    issues = []
    for key, value, label in (('lds', lds_version, 'LDS'), ('api', api_version, 'the plugin API'),
                              ('python', python_version, 'Python')):
        issue = _version_issue(value, compatibility[key], f'compatibility.{key}', label)
        if issue:
            issues.append(issue)
    platform = system.strip().lower() if isinstance(system, str) else ''
    platform = {'win32': 'windows', 'win64': 'windows', 'macos': 'darwin'}.get(platform, platform)
    architecture = machine.strip().lower() if isinstance(machine, str) else ''
    architecture = {'amd64': 'x86_64', 'x64': 'x86_64', 'aarch64': 'arm64'}.get(architecture, architecture)
    for key, actual, label in (('os', platform, 'operating system'), ('arch', architecture, 'processor architecture')):
        if actual not in compatibility[key]:
            issues.append(_issue('unsupported_platform', f'compatibility.{key}',
                                 f'This plugin does not support this {label}.', list(compatibility[key]), actual))
    native = contract.get('native_backend')
    if native:
        for key, actual, expected in (('implementation', python_implementation, native['implementation']),
                                      ('cache_tag', python_cache_tag, native['cache_tag']),
                                      ('pointer_bits', pointer_bits, 64)):
            if actual != expected or (key == 'pointer_bits' and type(actual) is not int):
                issues.append(_issue('native_runtime_mismatch', f'native_backend.{key}',
                                     'This compiled plugin requires 64-bit CPython 3.12.', expected, actual))
    if dependencies is not None:
        if not isinstance(dependencies, dict):
            raise PackageContractError('dependencies', 'must map plugin ids to installed version strings')
        for plugin_id, specifier in contract['dependency_versions'].items():
            field = f'dependency_versions.{plugin_id}'
            if plugin_id not in dependencies:
                issues.append(_issue('missing_dependency', field,
                                     f'This plugin requires {plugin_id} {specifier}, which is not installed.', specifier, None))
                continue
            issue = _version_issue(dependencies[plugin_id], specifier, field, plugin_id)
            if issue:
                issues.append(issue)
    if host_dependencies is not None:
        for name, specifier in contract.get('host_dependencies', {}).items():
            if name not in host_dependencies:
                issues.append(_issue('missing_host_dependency', f'host_dependencies.{name}',
                                     f'This plugin requires the LDS runtime dependency {name} {specifier}. Update or repair LDS first.', specifier, None))
            else:
                issue = _version_issue(host_dependencies[name], specifier, f'host_dependencies.{name}', name)
                if issue:
                    issues.append(issue)
    return issues
