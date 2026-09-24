"""Installing an external plugin from a ZIP — the parts that must not trust the archive.

The design review served a ``.env`` through a directory junction and a hard
link placed inside a plugin's ``frontend/`` folder (``safe_join`` is lexical),
so everything here works on ``realpath``: an archive entry may not be
absolute, may not climb, may not be a link, and must land inside the target
directory after the path is resolved. Size and count are capped.
"""
from __future__ import annotations

import json
import hashlib
import os
import re
import stat
import struct
import zipfile
from pathlib import Path

from .manifest import MANIFEST_NAME, ManifestError, parse_manifest

MAX_ENTRIES = 5000
MAX_TOTAL_BYTES = 200 * 1024 * 1024
MAX_MANIFEST_BYTES = 64 * 1024


class ArchiveError(ValueError):
    """The archive is not a plugin, or not one we would extract."""


def _entry_relpath(name: str) -> str:
    """The safe relative path of an archive member, or raise."""
    norm = name.replace('\\', '/')
    if norm.startswith('/') or ':' in norm:
        raise ArchiveError(f'archive entry {name!r} is an absolute path')
    parts = norm.rstrip('/').split('/')
    if '..' in parts:
        raise ArchiveError(f'archive entry {name!r} climbs out of the plugin directory')
    for part in parts:
        if (not part or part == '.' or part.endswith((' ', '.'))
                or any(ord(c) < 32 or c in '<>"|?*' for c in part)
                or re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', part, re.I)):
            raise ArchiveError('archive contains an ambiguous or reserved file name')
    return '/'.join(parts)


def _is_link(info: zipfile.ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0o170000
    return mode == stat.S_IFLNK


def _validated_entries(zf):
    """One interpretation on all platforms, before inspecting or extracting."""
    infos = zf.infolist()
    if len(infos) > MAX_ENTRIES:
        raise ArchiveError(f'archive has more than {MAX_ENTRIES} entries')
    if sum(i.file_size for i in infos) > MAX_TOTAL_BYTES:
        raise ArchiveError(f'archive unpacks to more than {MAX_TOTAL_BYTES // (1024 * 1024)} MB')
    entries, seen, files, parents = [], set(), set(), set()
    for info in infos:
        mode = (info.external_attr >> 16) & 0o170000
        if _is_link(info) or mode not in (0, stat.S_IFREG, stat.S_IFDIR):
            raise ArchiveError('archive contains a link or special file')
        if info.flag_bits & 1:
            raise ArchiveError('encrypted plugin archives are not supported')
        rel = _entry_relpath(info.filename)
        key = rel.casefold()
        if key in seen:
            raise ArchiveError('archive contains duplicate or case-aliased paths')
        seen.add(key)
        if not info.is_dir():
            files.add(key)
        parts = key.split('/')
        parents.update('/'.join(parts[:n]) for n in range(1, len(parts)))
        entries.append((info, rel))
    if files & parents:
        raise ArchiveError('archive uses a file as a directory')
    return entries


def inspect_archive(zf: zipfile.ZipFile) -> tuple[dict, str]:
    """Find and decode the manifest. Returns ``(manifest dict, root prefix)``
    where the prefix is '' when the manifest is at the archive root, or
    ``'<dir>/'`` when the whole plugin sits in one top-level folder."""
    candidates = []
    for info, rel in _validated_entries(zf):
        parts = rel.split('/')
        if parts[-1] == MANIFEST_NAME and len(parts) <= 2:
            candidates.append((rel, info))
    roots = sorted({rel[:-len(MANIFEST_NAME)] for rel, _ in candidates}, key=len)
    if not roots:
        raise ArchiveError(f'no {MANIFEST_NAME} at the archive root or in its top-level folder')
    if len(roots) > 1:
        raise ArchiveError('the archive carries more than one plugin')
    prefix = roots[0]
    info = next(i for rel, i in candidates if rel.startswith(prefix))
    if info.file_size > MAX_MANIFEST_BYTES:
        raise ArchiveError(f'{MANIFEST_NAME} is larger than {MAX_MANIFEST_BYTES} bytes')
    try:
        data = json.loads(zf.read(info).decode('utf-8'))
    except (ValueError, UnicodeDecodeError) as exc:
        raise ArchiveError(f'{MANIFEST_NAME}: not valid JSON ({exc})') from exc
    return data, prefix


def inspect_plugin_zip(path, *, official: bool = False) -> tuple:
    """Validate a plugin archive without extracting it. Returns
    ``(manifest, prefix)``; the manifest's ``dir`` is not final yet."""
    try:
        with zipfile.ZipFile(path) as zf:
            data, prefix = inspect_archive(zf)
            entries = {rel: info.file_size for info, rel in _validated_entries(zf) if not info.is_dir()}
    except zipfile.BadZipFile as exc:
        raise ArchiveError(f'not a ZIP archive ({exc})') from exc
    try:
        manifest = parse_manifest(data, Path('.'), official=official)
    except ManifestError as exc:
        raise ArchiveError(str(exc)) from exc
    if manifest.bundled:
        raise ArchiveError('this archive declares a BUNDLED plugin; only external plugins ("publisher.name") install here')
    if manifest.contract['schema_version'] >= 2:
        required = [manifest.frontend, manifest.requirements, *manifest.contract['frontend_styles']]
        for worker in manifest.contract['frontend_workers']:
            required.extend([worker['entry'], *worker['loaders']])
        if manifest.python_package:
            native = manifest.contract.get('native_backend')
            required.append(native['entry'] if native else manifest.python_package + '/__init__.py')
        for name in filter(None, required):
            if prefix + name not in entries:
                raise ArchiveError('The package is missing a declared interface, stylesheet, requirements file or Python entry point.')
            if name.endswith(('.js', '.mjs', '.css')) and not entries[prefix + name]:
                raise ArchiveError('The package contains an empty declared interface or stylesheet.')
        if manifest.contract.get('native_backend'):
            _inspect_native_backend(path, manifest, prefix, entries)
        _inspect_node_wheels(path, manifest, prefix, entries)
    return manifest, prefix


def _inspect_node_wheels(path, manifest, prefix, entries):
    """A package must actually carry every hashed wheel its node recipes declare."""
    if not any(pack.get('installation', {}).get('wheels') for pack in manifest.node_packs):
        return
    from .node_recipe import MAX_ARCHIVE_BYTES
    with zipfile.ZipFile(path) as archive:
        members = {rel: info for info, rel in _validated_entries(archive) if not info.is_dir()}
        for pack in manifest.node_packs:
            install = pack.get('installation', {})
            for wheel in install.get('wheels', []):
                name = prefix + install['wheelhouse'] + '/' + wheel['filename']
                if name not in entries or name not in members or members[name].file_size > MAX_ARCHIVE_BYTES:
                    raise ArchiveError('The package is missing a declared node wheel or it exceeds the size limit.')
                digest, size = hashlib.sha256(), 0
                with archive.open(members[name]) as source:
                    while chunk := source.read(64 * 1024):
                        size += len(chunk)
                        if size > MAX_ARCHIVE_BYTES:
                            raise ArchiveError('A declared node wheel exceeds the size limit.')
                        digest.update(chunk)
                if digest.hexdigest() != wheel['sha256']:
                    raise ArchiveError('A declared node wheel does not match the package SHA-256.')


def _inspect_native_backend(path, manifest, prefix, entries):
    """Check the declared PE header without executing any archive code.

    This rejects wrong/truncated artifacts, not hostile machine code. The
    signed Store and its existing consent/transaction path remain mandatory.
    """
    native_entry = manifest.contract['native_backend']['entry']
    package = manifest.python_package.casefold()
    for name in entries:
        if not name.startswith(prefix):
            continue
        relative = name[len(prefix):].casefold()
        if relative == native_entry.casefold():
            continue
        if (relative in {package + suffix for suffix in ('.py', '.pyc', '.pyo', '.pyd')}
                or (relative.startswith(package + '/') and relative.endswith(('.py', '.pyc', '.pyo', '.pyd')))
                or (relative.startswith(package + '.') and relative.endswith('.pyd'))):
            raise ArchiveError('A native backend cannot include a competing Python entry point or package.')
    message = 'The native backend must be a complete Windows x86_64 PE extension DLL.'
    with zipfile.ZipFile(path) as archive, archive.open(prefix + native_entry) as stream:
        header = stream.read(64)
        if len(header) != 64 or header[:2] != b'MZ':
            raise ArchiveError(message)
        offset = struct.unpack_from('<I', header, 60)[0]
        # Bound header inspection independently from the archive's payload cap.
        if offset < 64 or offset > 1024 * 1024:
            raise ArchiveError(message)
        stream.seek(offset)
        pe = stream.read(24)
        if len(pe) != 24 or pe[:4] != b'PE\0\0':
            raise ArchiveError(message)
        machine, sections, _, _, _, optional_size, flags = struct.unpack('<HHIIIHH', pe[4:])
        if machine != 0x8664 or not 1 <= sections <= 96 or optional_size < 112 or not flags & 0x2000:
            raise ArchiveError(message)
        optional = stream.read(optional_size)
        section_table = stream.read(sections * 40)
        if len(optional) != optional_size or optional[:2] != b'\x0b\x02' or len(section_table) != sections * 40:
            raise ArchiveError(message)
        size = entries[prefix + native_entry]
        for section in range(sections):
            raw_size, raw_offset = struct.unpack_from('<II', section_table, section * 40 + 16)
            if raw_size and (raw_offset < offset + 24 + optional_size + len(section_table)
                             or raw_offset + raw_size > size):
                raise ArchiveError(message)


def extract_plugin_zip(path, dest: Path, prefix: str) -> None:
    """Extract the plugin's files under ``dest`` (which must not exist), every
    path checked on realpath after joining."""
    dest = Path(dest)
    if dest.exists():
        raise ArchiveError(f'{dest.name} already exists')
    dest.mkdir(parents=True)
    base = os.path.realpath(dest)
    with zipfile.ZipFile(path) as zf:
        for info, rel in _validated_entries(zf):
            if prefix:
                if not rel.startswith(prefix):
                    continue    # a stray file beside the plugin folder
                rel = rel[len(prefix):]
            if not rel:
                continue
            target = os.path.realpath(os.path.join(base, rel))
            if target != base and not target.startswith(base + os.sep):
                raise ArchiveError(f'archive entry {info.filename!r} resolves outside the plugin directory')
            if info.is_dir():
                os.makedirs(target, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with zf.open(info) as src, open(target, 'wb') as out:
                while True:
                    chunk = src.read(1024 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)


def file_is_safe_to_serve(path: str, base_dir: str) -> bool:
    """A file under ``base_dir`` after realpath resolution, that is not a link
    and has a single hard link — the two escapes the review measured."""
    real = os.path.realpath(path)
    base = os.path.realpath(base_dir)
    if not (real == base or real.startswith(base + os.sep)):
        return False
    try:
        st = os.lstat(path)
    except OSError:
        return False
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(os.stat(real).st_mode):
        return False
    return os.stat(real).st_nlink <= 1
