"""Installed outside the worktree so checking out an old commit keeps the guard."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

from check_public_history import HistoryError, check_history
from public_port_manifest import digest, fields, strict_json

MANIFEST_FIELDS = ('public_port_manifest', 'public_port_manifest_sha256', 'public_port_review_sha256')


def read_config(config_path):
    config = strict_json(config_path.read_bytes())
    if type(config) is not dict or type(config.get('schema_version')) is not int:
        raise ValueError('Unknown guard configuration.')
    version = config['schema_version']
    if version not in (1, 2):
        raise ValueError('Unknown guard configuration.')
    fields(config, ('schema_version', 'public_base', 'private_source', 'private_remote_identity',
                    'previous_hook', 'shell') + (MANIFEST_FIELDS if version == 2 else ()))
    if version == 2:
        if type(config['public_port_manifest']) is not str or not Path(config['public_port_manifest']).is_absolute():
            raise ValueError('The pinned manifest requires an absolute external path.')
        digest(config['public_port_manifest_sha256'])
        digest(config['public_port_review_sha256'])
    return config


def remote_identity(value: str) -> tuple[str, str]:
    """Compare the actual endpoint, never the easily renamed Git remote alias."""
    parsed = urlsplit(value)
    if parsed.scheme in ('https', 'http', 'ssh') and parsed.hostname:
        if parsed.query or parsed.fragment:
            raise ValueError('Remote URLs with queries or fragments are not supported.')
        host = parsed.hostname.casefold()
        if parsed.port:
            host += ':' + str(parsed.port)
        path = parsed.path.strip('/').removesuffix('.git')
        return host, path
    match = re.fullmatch(r'(?:[^/@:\s]+@)?([^/:\s]+):([^\s]+)', value)
    if match and not re.match(r'^[A-Za-z]:[\\/]', value):
        return match.group(1).casefold(), match.group(2).strip('/').removesuffix('.git')
    raise ValueError('The approved private remote must be an HTTPS or SSH repository URL.')


def run(config_path: Path, remote_name: str, remote_url: str, input_data: bytes) -> int:
    try:
        config = read_config(config_path)
        updates = []
        for line in input_data.decode('utf-8').splitlines():
            fields = line.split()
            if len(fields) != 4:
                raise ValueError('Malformed pre-push update.')
            updates.append(fields)
        previous = config.get('previous_hook')
        if previous:
            completed = subprocess.run(
                [config['shell'], previous, remote_name, remote_url],
                input=input_data, capture_output=True, check=False, timeout=60,
            )
            if completed.returncode:
                print('Push refused by the existing repository policy.', file=sys.stderr)
                return 1
        try:
            is_private = list(remote_identity(remote_url)) == config['private_remote_identity']
        except ValueError:
            # Local paths and unfamiliar destinations receive the public check.
            is_private = False
        if is_private:
            return 0
        for _, local_sha, _, _ in updates:
            if local_sha and set(local_sha) == {'0'}:
                continue
            options = {key: config[key] for key in MANIFEST_FIELDS} if config['schema_version'] == 2 else {}
            result = check_history(Path.cwd(), local_sha, config['public_base'], config['private_source'], **options)
            if not result['allowed']:
                print('Push refused: private plugin material occurs in the history being sent. '
                      'Keep this history on the approved private remote; publish a reviewed core snapshot.',
                      file=sys.stderr)
                print(json.dumps(result, ensure_ascii=True), file=sys.stderr)
                return 1
        return 0
    except (HistoryError, ValueError, OSError, KeyError, TypeError, RecursionError, subprocess.TimeoutExpired):
        print('Push refused: the private-source guard could not verify this update.', file=sys.stderr)
        return 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('remote_name')
    parser.add_argument('remote_url')
    args = parser.parse_args(argv)
    return run(args.config, args.remote_name, args.remote_url, sys.stdin.buffer.read())


if __name__ == '__main__':
    sys.exit(main())
