"""Install a persistent pre-push check while retaining the existing hook.

Only use a public baseline independently verified against the public remote.
Installation does not push, change repository visibility, or rewrite history.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import shutil
import sys
from pathlib import Path

from check_public_history import _check_history, check_history, commit_id, git
from private_plugin_pre_push import MANIFEST_FIELDS, read_config, remote_identity
from public_port_manifest import load_manifest

MARKER = '# LDS private source guard v1'
GUARD_FILES = ('check_public_history.py', 'private_plugin_policy.py',
               'public_port_manifest.py', 'private_plugin_pre_push.py')


def atomic_write(path: Path, content: bytes):
    temporary = path.with_name(path.name + '.installing')
    with temporary.open('xb') as output:
        output.write(content)
    try:
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def install(repo: Path, public_base: str, private_source: str, private_remote: str, *,
            public_port_manifest=None, public_port_manifest_sha256=None,
            public_port_review_sha256=None) -> dict:
    # Validate the trust inputs and available objects before touching hooks.
    check_history(repo, public_base, public_base, private_source)
    baseline = commit_id(repo, public_base)
    private_source = commit_id(repo, private_source)
    identity = remote_identity(git(repo, 'remote', 'get-url', '--push', private_remote).decode().strip())
    hook = Path(git(repo, 'rev-parse', '--path-format=absolute', '--git-path', 'hooks/pre-push').decode().strip())
    common = Path(git(repo, 'rev-parse', '--path-format=absolute', '--git-common-dir').decode().strip()).resolve()
    # core.hooksPath can point into a checkout that clean/checkout may erase.
    # Refuse before writing anything; every linked worktree must use Git storage.
    if hook.resolve().parent != common / 'hooks':
        raise ValueError('Persistent publication protection requires shared Git hooks.')
    source_root = Path(__file__).resolve().parent
    directory = hook.parent / 'lds-private-boundary'
    config_file = directory / 'guard.json'
    before = hook.read_bytes() if hook.exists() else b''
    previous = None
    existing = None
    shell = shutil.which('sh')
    if before:
        if MARKER.encode() in before:
            existing = read_config(config_file)
            if (existing['public_base'], existing['private_source'], existing['private_remote_identity']) != (
                    baseline, private_source, list(identity)):
                raise ValueError('Reinstallation cannot change the installed publication trust inputs.')
            previous = existing.get('previous_hook')
            shell = existing.get('shell') or shell
        else:
            if not shell:
                candidate = Path(shutil.which('git') or '').resolve().parent.parent / 'usr/bin/sh.exe'
                shell = str(candidate) if candidate.is_file() else None
            if not shell:
                raise ValueError('A shell is required to preserve the existing pre-push hook.')
            digest = hashlib.sha256(before).hexdigest()[:16]
            previous = str(directory / ('previous-pre-push-' + digest))
    options = (public_port_manifest, public_port_manifest_sha256, public_port_review_sha256)
    if not any(value is not None for value in options) and existing and existing['schema_version'] == 2:
        options = tuple(existing[key] for key in MANIFEST_FIELDS)
    approval = load_manifest(repo, *options, git) if any(value is not None for value in options) else None
    if approval is not None:
        result = _check_history(repo, approval.tip, baseline, private_source, approval)
        if not result['allowed']:
            raise ValueError('Unapproved private entries remain in the proposed export history.')
    sources = {filename: (source_root / filename).read_bytes() for filename in GUARD_FILES}
    if (hook.read_bytes() if hook.exists() else b'') != before:
        raise ValueError('The pre-push hook changed during validation; installation refused.')
    hook.parent.mkdir(parents=True, exist_ok=True)
    directory.mkdir(exist_ok=True)
    if previous and MARKER.encode() not in before:
        previous_path = Path(previous)
        if previous_path.exists() and previous_path.read_bytes() != before:
            raise ValueError('The previous-hook backup differs; refusing to overwrite it.')
        if not previous_path.exists():
            atomic_write(previous_path, before)
    config = {'schema_version': 1, 'public_base': baseline, 'private_source': private_source,
              'private_remote_identity': identity, 'previous_hook': previous, 'shell': shell}
    if approval is not None:
        pinned = directory / ('public-port-' + approval.sha256 + '.json')
        if pinned.exists() and pinned.read_bytes() != approval.content:
            raise ValueError('The persistent manifest differs; refusing to overwrite it.')
        if not pinned.exists():
            atomic_write(pinned, approval.content)
        config.update(schema_version=2, public_port_manifest=str(pinned.resolve()),
                      public_port_manifest_sha256=approval.sha256,
                      public_port_review_sha256=approval.review_sha256)
    for filename, content in sources.items():
        atomic_write(directory / filename, content)
    wrapper = ('#!/bin/sh\n' + MARKER + '\nexec ' + shlex.quote(Path(sys.executable).as_posix()) + ' '
               + shlex.quote((directory / 'private_plugin_pre_push.py').as_posix()) + ' --config '
               + shlex.quote(config_file.as_posix()) + ' "$@"\n').encode()
    if (hook.read_bytes() if hook.exists() else b'') != before:
        raise ValueError('The pre-push hook changed during installation; its content was preserved.')
    # Publish the configuration only after its exact manifest bytes and runtime exist.
    atomic_write(config_file, (json.dumps(config, indent=2) + '\n').encode())
    atomic_write(hook, wrapper)
    hook.chmod(hook.stat().st_mode | 0o111)
    return {'installed': True, 'public_base': baseline, 'private_source': private_source,
            'existing_hook_preserved': bool(previous), 'hook_sha256': hashlib.sha256(wrapper).hexdigest()}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path('.'))
    parser.add_argument('--public-base', required=True)
    parser.add_argument('--private-source', required=True)
    parser.add_argument('--private-remote', default='private')
    parser.add_argument('--public-port-manifest', type=Path)
    parser.add_argument('--public-port-manifest-sha256')
    parser.add_argument('--public-port-review-sha256')
    args = parser.parse_args(argv)
    try:
        result = install(args.repo, args.public_base, args.private_source, args.private_remote,
                         public_port_manifest=args.public_port_manifest,
                         public_port_manifest_sha256=args.public_port_manifest_sha256,
                         public_port_review_sha256=args.public_port_review_sha256)
    except (ValueError, OSError):
        print('Installation refused: verify the Git objects, private remote and existing hook.', file=sys.stderr)
        return 1
    print(json.dumps(result))
    return 0


if __name__ == '__main__':
    sys.exit(main())
