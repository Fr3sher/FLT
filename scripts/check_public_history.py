"""Refuse private product material before a Git history becomes public.

The caller supplies an immutable, previously verified public commit. Every new
reachable commit is checked, including deleted files and merged side branches.
An optional private snapshot also detects unchanged product blobs moved to a
different path. This is an accidental-publication guard, not copy protection.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

if __package__:
    from .private_plugin_policy import private_plugin_path_reason
    from .public_port_manifest import ManifestError, load_manifest
else:
    from private_plugin_policy import private_plugin_path_reason
    from public_port_manifest import ManifestError, load_manifest

OID = re.compile(r'(?:[0-9a-f]{40}|[0-9a-f]{64})\Z')


class HistoryError(ValueError):
    pass


def git(repo: Path, *args: str) -> bytes:
    # The explicit checkout is the inspection authority. Hook-inherited Git
    # context must not redirect it or change which object/configuration is read.
    environment = {key: value for key, value in os.environ.items() if not key.upper().startswith('GIT_')}
    try:
        result = subprocess.run(
            ['git', '--no-replace-objects', '-C', str(repo), *args],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=60,
            env=environment,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HistoryError('Git history inspection could not complete; publication refused.') from exc
    if result.returncode:
        # Git errors may contain credential-bearing URLs or local paths.
        raise HistoryError('Git history inspection failed; fetch the required objects before publication.')
    return result.stdout


def commit_id(repo: Path, oid: str) -> str:
    if not OID.fullmatch(oid):
        raise HistoryError('Use a full immutable Git object ID, not a moving reference.')
    resolved = git(repo, 'rev-parse', '--verify', '--end-of-options', oid + '^{}').decode().strip()
    if git(repo, 'cat-file', '-t', resolved).strip() != b'commit':
        raise HistoryError('Public references must resolve to a commit, not a standalone blob or tree.')
    return resolved


def tree_entries(repo: Path, commit: str):
    for item in git(repo, 'ls-tree', '-r', '-z', commit).split(b'\0'):
        if not item:
            continue
        metadata, name = item.split(b'\t', 1)
        mode, kind, oid = metadata.decode('ascii').split(' ')
        yield mode, kind, oid, name.decode('utf-8', errors='surrogateescape')


def check_history(repo: Path, tip: str, public_base: str, private_source: str | None = None, *,
                  public_port_manifest=None, public_port_manifest_sha256=None,
                  public_port_review_sha256=None) -> dict:
    try:
        options = (public_port_manifest, public_port_manifest_sha256, public_port_review_sha256)
        approval = load_manifest(Path(repo), *options, git) if any(v is not None for v in options) else None
        return _check_history(repo, tip, public_base, private_source, approval)
    except HistoryError:
        raise
    except (ValueError, OSError, RecursionError) as exc:
        raise HistoryError('The approved public-port manifest could not verify this history.') from exc


def _check_history(repo, tip, public_base, private_source, approval):
    """Internal entry for the installer, using the same already verified bytes."""
    repo = Path(repo)
    if git(repo, 'rev-parse', '--is-shallow-repository').strip() != b'false':
        raise HistoryError('A shallow repository cannot prove that private history is absent.')
    graft_path = Path(git(repo, 'rev-parse', '--path-format=absolute', '--git-path', 'info/grafts').decode().strip())
    if graft_path.exists() and graft_path.stat().st_size:
        raise HistoryError('Local Git grafts cannot be used to inspect public history.')
    baseline = commit_id(repo, public_base)
    destination = commit_id(repo, tip)
    baseline_entries = list(tree_entries(repo, baseline))
    if any(private_plugin_path_reason(name) for _, _, _, name in baseline_entries):
        raise HistoryError('The trusted public baseline itself contains private product paths.')

    exceptions = set()
    if approval is not None:
        # A tag annotation is a separate object and is not covered by a commit review.
        if tip != destination or public_base != baseline:
            raise HistoryError('Approved public ports require exact commit IDs, without tag indirection.')
        try:
            exceptions = approval.exceptions(repo, tip, public_base, private_source, git, tree_entries)
        except ManifestError as exc:
            raise HistoryError(str(exc)) from exc

    private_blobs = set()
    if private_source is not None:
        source = commit_id(repo, private_source)
        known_public_blobs = {oid for _, kind, oid, _ in baseline_entries if kind == 'blob'}
        private_blobs = {
            oid for _, kind, oid, name in tree_entries(repo, source)
            if kind == 'blob' and private_plugin_path_reason(name)
        } - known_public_blobs

    commits = git(repo, 'rev-list', destination, '--not', baseline, '--').decode().splitlines()
    checked = 0
    for commit in commits:
        checked += 1
        findings = []
        tree = git(repo, 'rev-parse', commit + '^{tree}').decode().strip() if exceptions else None
        for mode, kind, oid, name in tree_entries(repo, commit):
            reason = private_plugin_path_reason(name)
            if reason is None and kind == 'blob' and oid in private_blobs:
                reason = 'Unchanged private product content was copied to a different path'
            if reason is not None and (commit, tree, name, mode, kind, oid) not in exceptions:
                findings.append({'path': name, 'reason': reason})
            if len(findings) == 5:
                break
        if findings:
            return {'allowed': False, 'tip': destination, 'public_base': baseline,
                    'commits_checked': checked, 'private_commit': commit, 'findings': findings}
    return {'allowed': True, 'tip': destination, 'public_base': baseline, 'commits_checked': checked}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path('.'))
    parser.add_argument('--tip', required=True)
    parser.add_argument('--public-base', required=True)
    parser.add_argument('--private-source')
    parser.add_argument('--public-port-manifest', type=Path)
    parser.add_argument('--public-port-manifest-sha256')
    parser.add_argument('--public-port-review-sha256')
    args = parser.parse_args(argv)
    try:
        result = check_history(args.repo, args.tip, args.public_base, args.private_source,
                               public_port_manifest=args.public_port_manifest,
                               public_port_manifest_sha256=args.public_port_manifest_sha256,
                               public_port_review_sha256=args.public_port_review_sha256)
    except HistoryError as exc:
        print(json.dumps({'allowed': False, 'error': str(exc)}))
        return 1
    print(json.dumps(result, ensure_ascii=True))
    return 0 if result['allowed'] else 1


if __name__ == '__main__':
    sys.exit(main())
