"""Portable package paths and bounded, non-executing source reads."""
from __future__ import annotations

import ast
import json
import re
import stat
import unicodedata
from pathlib import Path

MAX_BYTES = 200 * 1024 * 1024
MAX_FILES = 5000
MAX_MANIFEST_BYTES = 64 * 1024
MAX_CODE_BYTES = 8 * 1024 * 1024
MAX_NODE_WHEEL_BYTES = 64 * 1024 * 1024
DEVICES = {'con', 'prn', 'aux', 'nul'} | {f'{p}{n}' for p in ('com', 'lpt') for n in range(1, 10)}
EXCLUDED_DIRS = {'node_modules', 'tests', 'test', 'authoring', 'data', 'plugin-data', '__pycache__', 'env', 'venv',
                 'cache', 'coverage', 'htmlcov'}
EXCLUDED_FILES = {'lds-package.json', 'package.json', 'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml',
                  'build-report.json', 'credentials.json', 'secrets.json', 'token.txt', 'tokens.json'}
SECRET_CONTENT = re.compile(rb'-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----|'
                            rb'\b(?:ghp_|github_pat_|hf_)[A-Za-z0-9_]{20,}|'
                            rb'\bAKIA[A-Z0-9]{16}\b')


class PackageError(ValueError):
    """Actionable authoring error; never includes credential contents."""


def portable(path: str) -> str:
    if (not isinstance(path, str) or not path or path != unicodedata.normalize('NFC', path)
            or any(ord(c) < 32 or ord(c) == 127 for c in path)
            or any(c in path for c in '\\:?#%<>"|*')):
        raise PackageError(f'Non-portable package path: {path!r}')
    if any(p in ('', '.', '..') or p.endswith((' ', '.')) or p.split('.')[0].casefold() in DEVICES
           for p in path.split('/')):
        raise PackageError(f'Non-portable package path: {path!r}')
    return path


def plain(path: Path, *, directory=False):
    info = path.lstat()
    # Reparse points include NTFS junctions, not just symbolic links.
    if (stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400
            or (not directory and info.st_nlink != 1)):
        raise PackageError(f'Links and reparse points are forbidden: {path.name}')
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    if not expected(info.st_mode):
        raise PackageError(f'Expected a regular {"directory" if directory else "file"}: {path.name}')
    return info


def read_file(path: Path, root: Path, limit=MAX_BYTES) -> bytes:
    for parent in (path.parent, *path.parent.parents):
        if parent == root.parent:
            break
        plain(parent, directory=True)
    before = plain(path)
    if before.st_size > limit:
        raise PackageError(f'File exceeds the size limit: {path.name}')
    if not path.resolve().is_relative_to(root):
        raise PackageError(f'File escapes the package: {path.name}')
    with path.open('rb') as stream:
        import os
        opened = os.fstat(stream.fileno())
        if (opened.st_dev, opened.st_ino, opened.st_size) != (before.st_dev, before.st_ino, before.st_size):
            raise PackageError(f'File changed during validation: {path.name}')
        data = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
    current = plain(path)
    signature = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)
    # Windows Python may expose creation time through fstat().st_ctime while
    # lstat().st_ctime reports metadata change time. Compare within each API.
    if (len(data) > limit or signature(before) != signature(after) or signature(before) != signature(current)
            or opened.st_ctime_ns != after.st_ctime_ns or before.st_ctime_ns != current.st_ctime_ns):
        raise PackageError(f'File changed during validation: {path.name}')
    return data


def decode_json(data: bytes, where: str):
    def unique(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise PackageError(f'{where}: duplicate JSON field {key!r}')
            out[key] = value
        return out
    try:
        value = json.loads(data.decode('utf-8'), object_pairs_hook=unique)
    except (UnicodeError, ValueError) as exc:
        if isinstance(exc, PackageError):
            raise
        raise PackageError(f'{where}: invalid UTF-8 JSON') from exc
    if not isinstance(value, dict):
        raise PackageError(f'{where}: expected a JSON object')
    return value


def literals(path: Path):
    tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    values = {}
    for node in tree.body:
        if (isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name)
                and node.target.id == '__all__' and isinstance(node.op, ast.Add)
                and isinstance(values.get('__all__'), list)):
            try:
                extra = ast.literal_eval(node.value)
            except (ValueError, TypeError):
                continue
            if isinstance(extra, list) and all(isinstance(name, str) for name in extra):
                values['__all__'] += extra
            continue
        if isinstance(node, ast.Assign):
            value = node.value
            if (any(isinstance(target, ast.Name) and target.id == '__all__' for target in node.targets)
                    and isinstance(value, ast.Call) and isinstance(value.func, ast.Name)
                    and value.func.id == 'list' and len(value.args) == 1 and not value.keywords
                    and isinstance(value.args[0], ast.Name)
                    and isinstance(values.get(value.args[0].id), dict)):
                # Public lazy adapters name their exports with list(_EXPORTS).
                # Only a previously read literal mapping is accepted; no calls run.
                values['__all__'] = list(values[value.args[0].id])
                continue
            if isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id == 'frozenset':
                value = value.args[0]
            try:
                value = ast.literal_eval(value)
            except (ValueError, TypeError):
                continue
            for target in node.targets:
                if isinstance(target, ast.Name):
                    values[target.id] = value
    return values


def excluded(parts):
    name = parts[-1].casefold()
    return (any(p.startswith('.') or p.casefold() in EXCLUDED_DIRS for p in parts)
            or name in EXCLUDED_FILES or name.endswith(('.pyc', '.pyo', '.pem', '.key', '.p12', '.pfx', '.env',
                                                        '.log', '.sqlite', '.sqlite3', '.db', '.safetensors',
                                                        '.ckpt', '.pt', '.pth', '.onnx'))
            or name.startswith(('.env', 'test_')) or name.endswith('_test.py'))
