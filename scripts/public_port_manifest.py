"""Exact, externally pinned exceptions for reviewed public plugin ports.

The digest and review reference are trust inputs supplied by the operator. This
module verifies their scope, not the human review itself; it never grants trust
to a manifest discovered in the candidate checkout.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

OID = re.compile(r'(?:[0-9a-f]{40}|[0-9a-f]{64})\Z')
SHA256 = re.compile(r'[0-9a-f]{64}\Z')
PUBLIC_PRODUCTS = frozenset({
    'api_engines', 'camera_angles', 'canvas', 'civitai_publish', 'cloud_training',
    'hf_publish', 'image_upscale', 'live', 'model_tools', 'resource_monitor',
    'scrape', 'seedvr2', 'video',
})
ARCHIVE_SUFFIXES = ('.ldsplugin', '.zip', '.whl', '.tar', '.gz', '.bz2', '.xz',
                    '.tgz', '.tbz2', '.txz', '.7z', '.rar', '.pyz')


class ManifestError(ValueError):
    pass


def require(condition, message='Invalid approved public-port manifest.'):
    if not condition:
        raise ManifestError(message)


def strict_json(content: bytes):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'Duplicate JSON field in publication policy.')
            result[key] = value
        return result

    return json.loads(content.decode('utf-8'), object_pairs_hook=unique,
                      parse_constant=lambda value: require(False, 'Non-finite JSON value.'))


def fields(value, names):
    require(type(value) is dict and set(value) == set(names))


def oid(value):
    require(type(value) is str and OID.fullmatch(value))
    return value


def digest(value):
    require(type(value) is str and SHA256.fullmatch(value))
    return value


def git_path(value):
    require(type(value) is str and value and '\\' not in value)
    require(all(part not in ('', '.', '..') for part in value.split('/')))
    require(all(32 <= ord(char) < 0xD800 or 0xDFFF < ord(char) <= 0x10FFFF
                for char in value))
    require('\x7f' not in value and ':' not in value)
    return value


def outside_checkout(repo, path, git):
    """Resolve aliases and inspect every worktree, while allowing shared Git storage."""
    require(path.is_absolute(), 'The approved manifest path must be absolute.')
    resolved = path.resolve(strict=True)
    common = Path(git(repo, 'rev-parse', '--path-format=absolute', '--git-common-dir').decode().strip()).resolve()
    require(resolved.is_file())
    if resolved.is_relative_to(common):
        return resolved
    for item in git(repo, 'worktree', 'list', '--porcelain', '-z').split(b'\0'):
        if item.startswith(b'worktree '):
            checkout = Path(item[len(b'worktree '):].decode('utf-8')).resolve()
            require(not resolved.is_relative_to(checkout),
                    'The approved manifest must be stored outside every checkout.')
    return resolved


@dataclass(frozen=True)
class ApprovedPort:
    content: bytes
    data: dict
    sha256: str
    review_sha256: str

    @property
    def tip(self):
        return self.data['tip']

    def exceptions(self, repo, tip, public_base, private_source, git, entries):
        """Validate the whole graph before returning exact contextual exceptions."""
        data = self.data
        require((tip, public_base, private_source) ==
                (data['tip'], data['public_base'], data['private_source']),
                'The approved manifest does not match the tip or installed trust inputs.')
        origin = data['public_origin']
        for commit in (tip, public_base, private_source, origin):
            require(git(repo, 'cat-file', '-t', commit).strip() == b'commit')
        # Failure is fatal; the original baseline remains the history scan boundary.
        git(repo, 'merge-base', '--is-ancestor', public_base, origin)
        git(repo, 'merge-base', '--is-ancestor', origin, tip)
        actual = set(git(repo, 'rev-list', tip, '--not', origin, '--').decode().splitlines())
        declared = {item['commit'] for item in data['commits']}
        require(actual == declared, 'The approved manifest does not match the complete export graph.')
        require(git(repo, 'rev-parse', tip + '^{tree}').decode().strip() == data['tip_tree'])
        public_entries = {name: (mode, kind, blob) for mode, kind, blob, name in entries(repo, origin)}
        exceptions = set()
        for item in data['commits']:
            commit = item['commit']
            require(git(repo, 'rev-parse', commit + '^{tree}').decode().strip() == item['tree'])
            parents = git(repo, 'show', '-s', '--format=%P', commit).decode().strip().split()
            require(parents == item['parents'], 'The approved commit parent graph differs.')
            actual_entries = {name: (mode, kind, blob) for mode, kind, blob, name in entries(repo, commit)}
            for exception in item['exceptions']:
                name, mode, blob = exception['path'], exception['mode'], exception['blob']
                require(actual_entries.get(name) == (mode, 'blob', blob),
                        'An approved entry does not match its exact commit/tree/path/mode/blob.')
                provenance = exception['provenance']
                for source in provenance['sources']:
                    require(public_entries.get(source['path']) == (source['mode'], 'blob', source['blob']),
                            'The declared public source does not exist in the public origin.')
                if provenance['kind'] == 'unchanged':
                    source = provenance['sources'][0]
                    require((mode, blob) == (source['mode'], source['blob']),
                            'An unchanged public port differs from its public source.')
                exceptions.add((commit, item['tree'], name, mode, 'blob', blob))
        return exceptions


def load_manifest(repo, path, expected_sha256, review_sha256, git):
    require(all(value is not None for value in (path, expected_sha256, review_sha256)),
            'Manifest path, pinned SHA256 and immutable review SHA256 are all required.')
    digest(expected_sha256)
    digest(review_sha256)
    resolved = outside_checkout(repo, Path(path), git)
    content = resolved.read_bytes()
    require(hashlib.sha256(content).hexdigest() == expected_sha256,
            'The approved manifest bytes differ from their installed SHA256.')
    data = strict_json(content)
    fields(data, ('schema_version', 'public_base', 'private_source', 'public_origin',
                  'tip', 'tip_tree', 'review_sha256', 'products', 'commits'))
    require(type(data['schema_version']) is int and data['schema_version'] == 1)
    require(digest(data['review_sha256']) == review_sha256)
    for name in ('public_base', 'private_source', 'public_origin', 'tip', 'tip_tree'):
        oid(data[name])
    products = data['products']
    require(type(products) is list and products and all(type(p) is str for p in products))
    require(len(products) == len(set(products)) and set(products) <= PUBLIC_PRODUCTS)
    commits = data['commits']
    require(type(commits) is list and commits)
    seen_commits, seen_products = set(), set()
    for item in commits:
        fields(item, ('commit', 'tree', 'parents', 'exceptions'))
        commit = oid(item['commit'])
        require(commit not in seen_commits, 'Duplicate approved commit.')
        seen_commits.add(commit)
        oid(item['tree'])
        require(type(item['parents']) is list)
        parents = [oid(parent) for parent in item['parents']]
        require(len(parents) == len(set(parents)))
        require(type(item['exceptions']) is list)
        seen_paths = set()
        for entry in item['exceptions']:
            fields(entry, ('path', 'mode', 'type', 'blob', 'provenance'))
            name = git_path(entry['path'])
            parts = name.split('/')
            require(len(parts) >= 3 and parts[0] == 'bundled' and parts[1] in products)
            require(all(part.casefold() != 'bundled' for part in parts[2:]))
            require(not parts[-1].casefold().endswith(ARCHIVE_SUFFIXES),
                    'Distribution archives cannot receive source-port exceptions.')
            require(name not in seen_paths, 'Duplicate approved path in a commit.')
            seen_paths.add(name)
            seen_products.add(parts[1])
            require(entry['mode'] in ('100644', '100755') and entry['type'] == 'blob',
                    'Only regular source files can receive public-port exceptions.')
            oid(entry['blob'])
            provenance = entry['provenance']
            fields(provenance, ('kind', 'sources', 'evidence_sha256'))
            require(provenance['kind'] in ('unchanged', 'reviewed_port', 'generated'))
            digest(provenance['evidence_sha256'])
            sources = provenance['sources']
            require(type(sources) is list and sources)
            require(provenance['kind'] != 'unchanged' or len(sources) == 1)
            seen_sources = set()
            for source in sources:
                fields(source, ('path', 'mode', 'blob'))
                source_path = git_path(source['path'])
                require('bundled' not in [part.casefold() for part in source_path.split('/')])
                require(not source_path.casefold().endswith('.ldsplugin')
                        and source_path.split('/')[-1].casefold() != 'transition-pack.zip')
                require(source_path not in seen_sources)
                seen_sources.add(source_path)
                require(source['mode'] in ('100644', '100755'))
                oid(source['blob'])
    require(seen_products == set(products), 'The product inventory must match the exact exceptions.')
    return ApprovedPort(content, data, expected_sha256, review_sha256)
