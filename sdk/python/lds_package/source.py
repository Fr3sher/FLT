"""Explicit development adapter for the host's pure manifest rules and SDK."""
from __future__ import annotations

import importlib.util
import inspect
import sys
import types
import uuid
from pathlib import Path

from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name

from .common import PackageError, literals

HOST_IMPORTS = {'flask': 'Flask', 'requests': 'requests', 'PIL': 'Pillow',
                'sqlalchemy': 'SQLAlchemy', 'packaging': 'packaging', 'huggingface_hub': 'huggingface-hub',
                'filelock': 'filelock'}


def requirements(text: str, where: str):
    result = {}
    for line in text.splitlines():
        line = line.split(' #', 1)[0].strip()
        if not line or line.startswith('#'):
            continue
        try:
            req = Requirement(line)
        except InvalidRequirement as exc:
            raise PackageError(f'{where}: use plain PEP 508 requirements, without pip options or local paths') from exc
        if req.url:
            raise PackageError(f'{where}: URL dependencies are not supported by this authoring profile')
        key = canonicalize_name(req.name)
        if key in result:
            raise PackageError(f'{where}: duplicate dependency {req.name}')
        result[key] = req
    return result


class HostSource:
    def __init__(self, root):
        self.root = Path(root).resolve(strict=True)
        plugins = self.root / 'backend/app/plugins'
        registry = plugins / 'official.py'
        self.official_ids = set(literals(registry).get('OFFICIAL_IDS', [])) if registry.exists() else set()
        self.sdk = {}
        sdk_root = self.root / 'backend/lds_sdk'
        for path in sdk_root.rglob('*.py'):
            parts = list(path.relative_to(sdk_root).with_suffix('').parts)
            if parts[-1] == '__init__':
                parts.pop()
            module = '.'.join(['lds_sdk', *parts])
            exports = literals(path).get('__all__')
            if isinstance(exports, list) and all(isinstance(v, str) and v.isidentifier() for v in exports):
                self.sdk[module] = set(exports)
        if 'lds_sdk' not in self.sdk:
            raise PackageError('--lds-source must provide the public Python SDK')
        for module in tuple(self.sdk):
            parent = module.rpartition('.')[0]
            while parent:
                self.sdk.setdefault(parent, set())
                parent = parent.rpartition('.')[0]
        self.sdk_version = literals(self.root / 'backend/lds_sdk/__init__.py').get('VERSION')
        if self.sdk_version is None:
            # The public SDK derives VERSION from these host constants. Read
            # their literals without importing SDK adapters or starting LDS.
            api = literals(plugins / 'api.py')
            parts = [api.get('LDS_PLUGIN_API_MAJOR'), api.get('LDS_PLUGIN_API_MINOR')]
            if any(type(value) is not int or value < 0 for value in parts):
                raise PackageError('--lds-source must declare a literal SDK version or host API major/minor')
            self.sdk_version = '.'.join(map(str, parts))
        self.lds_version = literals(self.root / 'backend/app/version.py')['APP_VERSION']
        self.host_requirements = requirements((self.root / 'backend/requirements.txt').read_text(encoding='utf-8'),
                                              'LDS backend/requirements.txt')
        self.host_imports = {key: value for key, value in HOST_IMPORTS.items()
                             if canonicalize_name(value) in self.host_requirements
                             and not self.host_requirements[canonicalize_name(value)].marker}
        # Keep relative imports inside a unique development namespace. The official
        # adapter is ONLY the source registry predicate, never an installation receipt.
        self.namespace = '_lds_package_' + uuid.uuid4().hex
        package = types.ModuleType(self.namespace)
        package.__path__ = [str(plugins)]
        sys.modules[self.namespace] = package
        official = types.ModuleType(self.namespace + '.official')
        official.is_official_id = lambda value: isinstance(value, str) and value in self.official_ids
        sys.modules[official.__name__] = official
        self.contract = self._module('package_contract', plugins / 'package_contract.py')
        self.manifest = self._module('manifest', plugins / 'manifest.py')

    def _module(self, name, path):
        spec = importlib.util.spec_from_file_location(self.namespace + '.' + name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module

    def close(self):
        for name in tuple(sys.modules):
            if name == self.namespace or name.startswith(self.namespace + '.'):
                del sys.modules[name]

    def validate_manifest(self, data, directory, official):
        try:
            if 'official' in inspect.signature(self.manifest.parse_manifest).parameters:
                self.manifest.parse_manifest(data, directory, official=official)
            else:
                # Older developer checkout: bundled has the same base-field rules
                # for a known official product. It never reaches the ZIP manifest.
                self.manifest.parse_manifest(data | ({'bundled': True} if official else {}), directory)
            return self.contract.validate_contract(data)
        except ValueError as exc:
            raise PackageError(str(exc)) from exc
