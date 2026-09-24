"""Validate all package bytes first, then publish an immutable ZIP snapshot."""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

from packaging.version import InvalidVersion, Version
from packaging.utils import canonicalize_name

from . import common
from .common import PackageError, decode_json, excluded, plain, portable, read_file
from .imports import audit_javascript, audit_python
from .source import HostSource


@dataclass(frozen=True)
class ValidatedPackage:
    source: Path
    files: dict[str, bytes]
    manifest: dict
    dependencies: dict
    excluded: tuple[str, ...]

    def report(self):
        return {'ok': True, 'id': self.manifest['id'], 'version': self.manifest['version'],
                'file_count': len(self.files), 'size_bytes': sum(map(len, self.files.values())),
                'manifest': self.manifest, **self.dependencies, 'excluded': list(self.excluded),
                'sha256_files': {key: hashlib.sha256(value).hexdigest() for key, value in self.files.items()}}


def _snapshot(root):
    files, skipped, seen = {}, [], set()
    total = 0

    def walk(directory):
        nonlocal total
        plain(directory, directory=True)
        for item in sorted(directory.iterdir(), key=lambda p: p.name):
            relative = item.relative_to(root).as_posix()
            if excluded(relative.split('/')):
                skipped.append(relative)
                continue
            portable(relative)
            key = relative.casefold()
            if key in seen:
                raise PackageError(f'Case-insensitive duplicate package path: {relative}')
            seen.add(key)
            if item.is_dir():
                walk(item)
                continue
            data = read_file(item, root, common.MAX_BYTES - total)
            if common.SECRET_CONTENT.search(data):
                raise PackageError(f'Credential/private-key content detected: {relative}')
            files[relative] = data
            total += len(data)
            if len(files) > common.MAX_FILES:
                raise PackageError('Package exceeds the 5000-file limit')
    walk(root)
    return files, tuple(skipped)


def _normalize(raw, host, official):
    data = dict(raw)
    data.pop('dir', None)
    if any(key in data for key in ('official', 'provenance', 'trusted', 'verified_store', 'receipt')):
        raise PackageError('Application-managed provenance cannot be supplied in a package manifest')
    for field in ('bundled', 'in_process_requirements'):
        if field in data and type(data[field]) is not bool:
            raise PackageError(f'{field}: must be a boolean')
    if official:
        if data.get('id') not in host.official_ids:
            raise PackageError('--official-lds requires an ID in the selected LDS source registry')
        publisher = data.get('publisher', {'id': 'lds'})
        if not isinstance(publisher, dict) or publisher.get('id') != 'lds':
            raise PackageError('--official-lds cannot relabel another publisher')
        data['bundled'] = False
        if data.get('schema_version', 1) == 1:
            data.update(schema_version=2, publisher={'id': 'lds', 'name': 'LDS'},
                        compatibility={'lds': '>=' + str(Version(host.lds_version)),
                                       'api': f'>={host.sdk_version},<{Version(host.sdk_version).major + 1}',
                                       'python': '>=3.10,<4', 'os': ['windows', 'linux', 'darwin'],
                                       'arch': ['x86_64', 'arm64']},
                        dependency_versions={}, data_schema=1)
    elif data.get('bundled'):
        raise PackageError('Bundled source requires the explicit --official-lds authoring mode')
    if type(data.get('schema_version')) is not int or data['schema_version'] != 2:
        raise PackageError('A distributable package must declare schema_version 2')
    data.setdefault('bundled', False)
    for field in ('version', 'name', 'id'):
        if not isinstance(data.get(field), str) or not data[field].strip():
            raise PackageError(f'{field}: must be a non-empty string')
    try:
        Version(data['version'])
    except InvalidVersion as exc:
        raise PackageError('version: must be a PEP 440 version') from exc
    return data


def _assets(manifest, files):
    for pack in manifest.get('node_packs', []):
        installation = pack.get('installation', {})
        for wheel in installation.get('wheels', []):
            name = installation['wheelhouse'] + '/' + wheel['filename']
            data = files.get(name)
            if data is None or len(data) > common.MAX_NODE_WHEEL_BYTES:
                raise PackageError('The package is missing a declared node wheel or it exceeds the size limit.')
            if hashlib.sha256(data).hexdigest() != wheel['sha256']:
                raise PackageError('A declared node wheel does not match the package SHA-256.')
    for field in ('frontend', 'requirements'):
        value = manifest.get(field)
        if value is not None:
            portable(value)
            if value not in files:
                raise PackageError(f'{field}: declared file is absent from the package: {value}')
            if field == 'frontend' and not files[value]:
                raise PackageError('frontend: declared interface is empty')
    frontend = manifest.get('frontend')
    if frontend and not frontend.endswith(('.js', '.mjs')):
        raise PackageError('frontend: must be a built ESM JavaScript entry point')
    package = manifest.get('python_package')
    if package:
        portable(package)
        if package + '/__init__.py' not in files:
            raise PackageError('python_package: requires an included __init__.py')
    styles = manifest.get('frontend_styles', [])
    for style in styles:
        portable(style)
        if style not in files:
            raise PackageError(f'frontend_styles: declared CSS is absent: {style}')
        if not files[style]:
            raise PackageError(f'frontend_styles: declared CSS is empty: {style}')
    for worker in manifest.get('frontend_workers', []):
        for name in [worker['entry'], *worker['loaders']]:
            if name not in files or not files[name].strip():
                raise PackageError(f'frontend_workers: declared JavaScript is absent or empty: {name}')
    if frontend:
        prefix = str(Path(frontend).parent).replace('\\', '/') + '/'
        missing = [name for name in files if name.startswith(prefix) and name.endswith('.css') and name not in styles]
        if missing:
            raise PackageError('frontend_styles must declare all built CSS: ' + ', '.join(missing))
    # Avoid shipping a second, hidden import mechanism in stylesheet files.
    for name, data in files.items():
        if name.endswith('.css') and re.search(rb'@import\b', data, re.IGNORECASE):
            raise PackageError(f'{name}: bundle stylesheet imports before packaging')


def validate(source, *, lds_source=None, official_lds=False, js_tools=None):
    """Snapshot/validate without executing plugin code or writing to its tree.

    ``lds_source`` is an explicitly trusted development checkout, not plugin input.
    """
    root = Path(source).absolute()
    plain(root, directory=True)
    root = root.resolve(strict=True)
    files, skipped = _snapshot(root)
    if 'plugin.json' not in files:
        raise PackageError('plugin.json is required at the package root')
    raw = decode_json(files['plugin.json'], 'plugin.json')
    config_path = root / 'lds-package.json'
    config = decode_json(read_file(config_path, root, common.MAX_CODE_BYTES), 'lds-package.json') if config_path.exists() else {}
    host = HostSource(lds_source or Path(__file__).resolve().parents[3])
    try:
        manifest = _normalize(raw, host, official_lds)
        if official_lds and raw.get('schema_version', 1) == 1:
            manifest['frontend_styles'] = sorted(name for name in files if name.endswith('.css'))
        manifest.update(host.validate_manifest(manifest, root, official_lds))
        _assets(manifest, files)
        dependencies = audit_python(files, manifest, config, host, official=official_lds)
        # A separate declaration records host requirements; it never asks the
        # installer to put these dependencies into a plugin-only virtualenv.
        declared = raw.get('host_dependencies')
        if declared is not None:
            declared = {canonicalize_name(name): value for name, value in host.validate_manifest(manifest, root, official_lds)['host_dependencies'].items()}
        if declared is not None and declared != dependencies['host_dependencies']:
            raise PackageError('host_dependencies does not match the audited host imports')
        manifest['host_dependencies'] = dependencies['host_dependencies']
        audit_javascript(files, js_tools, workers=manifest.get('frontend_workers', []))
        files['plugin.json'] = (json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8')
        if len(files['plugin.json']) > common.MAX_MANIFEST_BYTES:
            raise PackageError(f'Normalized manifest exceeds the {common.MAX_MANIFEST_BYTES}-byte installer limit')
        if sum(map(len, files.values())) > common.MAX_BYTES:
            raise PackageError('Normalized package exceeds the 200 MiB limit')
        return ValidatedPackage(root, dict(sorted(files.items())), manifest, dependencies, skipped)
    finally:
        host.close()


def _destination(output, source, overwrite):
    dest = Path(output).absolute()
    if dest.suffix.lower() not in ('.zip', '.ldsplugin'):
        raise PackageError('Output must have a .ldsplugin or .zip extension')
    parent = dest.parent.resolve(strict=True)
    if parent.is_relative_to(source):
        raise PackageError('Output must be outside the source tree')
    portable(dest.name)
    plain(dest.parent, directory=True)
    dest = parent / dest.name
    if dest.exists() or dest.is_symlink():
        plain(dest)
        if not overwrite:
            raise PackageError('Output already exists; use --overwrite explicitly')
    return dest


def pack(source, output, *, overwrite=False, **options):
    """Validate first, then atomically publish a deterministic, uncompressed ZIP."""
    prepared = validate(source, **options)
    dest = _destination(output, prepared.source, overwrite)
    fd, temporary = tempfile.mkstemp(prefix='.lds-package-', suffix='.tmp', dir=dest.parent)
    temp = Path(temporary)
    try:
        with os.fdopen(fd, 'w+b') as stream:
            with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_STORED, allowZip64=False) as archive:
                for name, data in prepared.files.items():
                    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                    info.create_system = 3
                    info.external_attr = 0o100644 << 16
                    info.compress_type = zipfile.ZIP_STORED
                    archive.writestr(info, data)
            stream.flush()
            os.fsync(stream.fileno())
        _destination(dest, prepared.source, overwrite)
        if overwrite:
            os.replace(temp, dest)
        else:
            # Unlike rename on POSIX, link is atomically no-clobber. Failure on
            # filesystems without hard links is explicit and leaves no archive.
            os.link(temp, dest)
        result = prepared.report()
        result.update(archive=str(dest), sha256=hashlib.sha256(dest.read_bytes()).hexdigest())
        return result
    finally:
        temp.unlink(missing_ok=True)
