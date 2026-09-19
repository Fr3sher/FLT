"""Standalone, standard-library-only migration of desktop LDS Git installs to v2.

No app imports, dependency installs, database migrations, resets, cleans or
automatic restarts. Keep this script outside the installation being switched.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import ctypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import stat
import subprocess
import sys
import uuid


class MigrationError(ValueError):
    pass


RUNTIME_NAMES = {
    'data', 'data-docker', 'data-docker-gpu', 'config.json', '.env', '.venv',
    'venv', 'env', '.python', 'python', 'plugins', 'run', 'basedir',
    'bank-images', 'ollama-data', '.git', 'backend/extensions',
}
ENV_KEYS = {'LDS_DATA_DIR', 'LDS_CONFIG', 'LDS_ENV', 'LDS_PLUGINS_DIR', 'LDS_PORT'}


def git(root, *args, optional=False):
    env = dict(os.environ, GIT_TERMINAL_PROMPT='0', GIT_OPTIONAL_LOCKS='0')
    # The selected folder, not an inherited shell override, determines the repository.
    for name in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_COMMON_DIR'):
        env.pop(name, None)
    try:
        result = subprocess.run(['git', '-C', str(root), *args], env=env,
                                capture_output=True, timeout=180)
    except FileNotFoundError as exc:
        raise MigrationError('Git is required. Install Git, then reopen this tool.') from exc
    except subprocess.TimeoutExpired as exc:
        raise MigrationError('Git timed out. Keep LDS closed and check the repository before retrying.') from exc
    if result.returncode and not optional:
        # Git errors can contain authenticated URLs. Never copy them into the report.
        raise MigrationError(f'Git {args[0]} did not complete. No force or cleanup will be attempted.')
    return result


def output(root, *args):
    return git(root, *args).stdout.decode('utf-8', 'surrogateescape').strip()


def is_link(path):
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, 'st_file_attributes', 0) & 0x400)


def official_remote(value):
    normalized = value.casefold().rstrip('/').removesuffix('.git')
    if normalized.startswith('git@'):
        normalized = 'ssh://' + normalized.replace(':', '/', 1)
    return normalized in {
        'https://github.com/perfectgf/lora-dataset-studio',
        'ssh://git@github.com/perfectgf/lora-dataset-studio',
    }


def local_settings(root):
    values = {key: os.environ[key] for key in ENV_KEYS if key in os.environ}
    env_path = Path(values.get('LDS_ENV', root / '.env'))
    if not env_path.is_absolute():
        raise MigrationError('LDS_ENV must be an absolute path for this tool.')
    if env_path.exists():
        for line in env_path.read_text(encoding='utf-8-sig').splitlines():
            match = re.match(r'^\s*(?:export\s+)?(LDS_[A-Z_]+)\s*=\s*(.*)$', line)
            if not match or match[1] not in ENV_KEYS or match[1] in values:
                continue
            value = match[2].strip()
            # Accept ordinary dotenv paths. Fail closed on expressions/escapes whose
            # meaning depends on the original launcher; never execute a dotenv file.
            if value.startswith(('"', "'")):
                quote = value[0]
                end = value.find(quote, 1)
                if end < 0 or value[end + 1:].strip() and not value[end + 1:].lstrip().startswith('#'):
                    raise MigrationError('A custom LDS environment setting needs manual review.')
                value = value[1:end]
            else:
                value = re.split(r'\s+#', value, maxsplit=1)[0].strip()
            if '$' in value or '\\' in value:
                raise MigrationError('Use absolute paths with forward slashes for custom LDS settings, or migrate manually.')
            values[match[1]] = value
    data = Path(values.get('LDS_DATA_DIR', root / 'data'))
    config = Path(values.get('LDS_CONFIG', root / 'config.json'))
    plugins = Path(values.get('LDS_PLUGINS_DIR', data / 'plugins'))
    if any(not path.is_absolute() for path in (data, config, plugins)):
        raise MigrationError('Custom LDS paths must be absolute; the tool will not guess the launcher working folder.')
    try:
        settings = json.loads(config.read_text(encoding='utf-8')) if config.exists() else {}
        if not isinstance(settings, dict):
            raise ValueError
        port = int(values.get('LDS_PORT') or settings.get('server', {}).get('port') or 5050)
        if not 0 < port < 65536:
            raise ValueError
        custom = settings.get('paths', {})
        if not isinstance(custom, dict):
            raise ValueError
    except (ValueError, TypeError, AttributeError) as exc:
        raise MigrationError('The local configuration cannot be read safely. Nothing was changed.') from exc
    protected = [root / name for name in RUNTIME_NAMES] + [data, config, env_path, plugins]
    for value in custom.values():
        if isinstance(value, str) and value:
            path = Path(value)
            protected.extend([path] if path.is_absolute() else [root / path, root / 'backend' / path])
    files = {config, env_path, root / 'config.json', root / '.env', data / 'config.json', data / '.env'}
    for suffix in ('', '-wal', '-shm', '-journal'):
        files.add(data / ('studio.db' + suffix))
    return data, port, protected, files


def pid_alive(pid):
    if pid <= 0:
        return False
    if os.name != 'nt':
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True
    # os.kill(pid, 0) terminates processes on Windows: query only.
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
    kernel.GetExitCodeProcess.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        return ctypes.get_last_error() != 87  # only ERROR_INVALID_PARAMETER proves it absent
    try:
        code = wintypes.DWORD()
        return not kernel.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value == 259
    finally:
        kernel.CloseHandle(handle)


def ensure_stopped(data, port):
    lock = data / 'server.lock'
    ports = {5000, *range(5050, 5061), port}
    if lock.exists():
        try:
            record = json.loads(lock.read_text(encoding='utf-8'))
            pid, recorded_port = int(record['pid']), int(record['port'])
            if pid <= 0 or not 0 < recorded_port < 65536:
                raise ValueError
            ports.add(recorded_port)
        except (ValueError, KeyError, TypeError) as exc:
            raise MigrationError('The server lock cannot be verified. Close LDS and resolve the lock before retrying.') from exc
        if pid_alive(pid):
            raise MigrationError('LDS may still be running. Close its launcher (or Stop in Pinokio) before retrying.')
    for candidate in ports:
        for host in ('127.0.0.1', '::1'):
            try:
                connection = socket.create_connection((host, candidate), timeout=0.08)
            except OSError:
                continue
            connection.close()
            raise MigrationError(f'Port {candidate} is still in use. Close LDS and any service on that port before retrying.')


def clean_checkout(root):
    if output(root, 'status', '--porcelain', '--untracked-files=no'):
        raise MigrationError('Local source changes were found. Keep them; ask for help before migrating. No stash/reset is used.')
    flags = git(root, 'ls-files', '-v', '-z').stdout.split(b'\0')
    if any(row and (row[:1].islower() or row[:1] == b'S') for row in flags):
        raise MigrationError('Some tracked files are hidden from Git checks. Restore normal Git tracking before migration.')


def tree_paths(root, revision):
    paths = []
    for row in git(root, 'ls-tree', '-rz', revision).stdout.split(b'\0'):
        if not row:
            continue
        header, name = row.split(b'\t', 1)
        if header.split()[0] != b'100644' and header.split()[0] != b'100755':
            raise MigrationError('Linked source files or submodules require manual migration.')
        paths.append(name.decode('utf-8', 'surrogateescape'))
    return paths


def protect_paths(root, before, target, protected):
    protected = [os.path.normcase(str(path.resolve())) for path in protected]
    checked = set()
    for relative in set(tree_paths(root, before) + tree_paths(root, target)):
        path = root / relative
        real = os.path.normcase(str(path.resolve()))
        if any(real == item or real.startswith(item + os.sep) or item.startswith(real + os.sep)
               for item in protected):
            raise MigrationError('A Git-tracked path overlaps user data or a runtime folder. Manual migration is required.')
        for candidate in (path, *path.parents):
            if candidate == root or candidate in checked:
                break
            checked.add(candidate)
            if is_link(candidate):
                raise MigrationError('A source path is redirected by a link or junction. Manual migration is required.')


def preflight(root):
    if not (root / 'backend' / 'run.py').is_file() or not (root / 'frontend' / 'dist' / 'index.html').is_file():
        raise MigrationError('Select the LDS installation folder containing backend and frontend, not its data folder.')
    if not (root / '.git').exists():
        raise MigrationError('This is a ZIP installation: no Git branch needs changing. Open LDS and use Update & restart; keep the existing installation folder.')
    if not (root / '.git').is_dir() or is_link(root / '.git'):
        raise MigrationError('Linked worktrees and redirected Git folders require manual migration.')
    if Path(output(root, 'rev-parse', '--show-toplevel')).resolve() != root:
        raise MigrationError('Select the Git repository root.')
    if not official_remote(output(root, 'remote', 'get-url', 'origin')):
        raise MigrationError('origin is not the official public LDS repository. Forks/private repositories are left unchanged.')
    branch = output(root, 'symbolic-ref', '--short', 'HEAD')
    if branch not in {'main', 'v1', 'v2'}:
        raise MigrationError('Only main, v1 and v2 installations are supported. Your current branch is left unchanged.')
    for name in ('MERGE_HEAD', 'CHERRY_PICK_HEAD', 'REVERT_HEAD', 'rebase-apply', 'rebase-merge', 'index.lock', 'BISECT_START'):
        if (root / '.git' / name).exists():
            raise MigrationError('Another Git operation is in progress. Finish it before migrating.')
    if git(root, 'config', '--bool', 'core.sparseCheckout', optional=True).stdout.strip() == b'true':
        raise MigrationError('Sparse checkouts require manual migration.')
    clean_checkout(root)
    if output(root, 'rev-list', '--count', 'HEAD', '--not', '--remotes=origin') != '0':
        raise MigrationError('Local commits were found, or the public tracking history is missing. They will not be discarded; ask for help migrating.')
    return branch, output(root, 'rev-parse', 'HEAD')


def digest(path):
    hasher = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            hasher.update(chunk)
    return hasher.hexdigest()


def backup(root, files, branch, before, target):
    existing = sorted((path for path in files if path.exists()), key=str)
    if any(not path.is_file() for path in existing):
        raise MigrationError('A settings/database path is not a regular file. Nothing was changed.')
    size = sum(path.stat().st_size for path in existing)
    if shutil.disk_usage(root).free < size * 2 + 16 * 1024 * 1024:
        raise MigrationError('Not enough disk space for the database/settings backup. Free some space first.')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8]
    parent = root / '.git' / 'lds-migration-backups'
    if is_link(parent):
        raise MigrationError('The backup folder is redirected. Nothing was changed.')
    folder = parent / stamp
    folder.mkdir(parents=True, mode=0o700)
    records = []
    for index, source in enumerate(existing):
        destination = folder / f'{index:02d}-{source.name}'
        expected = digest(source)
        shutil.copy2(source, destination)
        if digest(source) != expected or digest(destination) != expected:
            raise MigrationError('A database/settings file changed during backup. Keep LDS closed and retry.')
        records.append({'source': str(source), 'backup': destination.name, 'sha256': expected})
    # Local-only recovery metadata can contain local paths: never upload it.
    record = {'from_branch': branch, 'from_commit': before, 'to_commit': target,
              'files': records, 'media_backed_up': False, 'status': 'backup_complete'}
    (folder / 'recovery.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
    reference = 'lds-before-v2-' + stamp
    git(root, 'branch', reference, before)
    return folder, reference, record


@contextmanager
def migration_lock(root):
    path = root / '.git' / 'lds-migration.lock'
    try:
        handle = path.open('x', encoding='ascii')
    except FileExistsError as exc:
        raise MigrationError('Another migration is active, or left a migration lock. Close the other tool; ask for help if the lock remains.') from exc
    try:
        with handle:
            handle.write(str(os.getpid()))
        yield
    finally:
        path.unlink()


def migrate(root, *, confirm=input, check_only=False):
    root = Path(root).expanduser().resolve()
    if os.environ.get('LDS_RUNTIME', '').startswith('docker') or Path('/.dockerenv').exists():
        raise MigrationError('Docker installations use the Docker update guide, not this desktop tool.')
    data, port, protected, files = local_settings(root)
    branch, before = preflight(root)
    if not (data / 'studio.db').is_file():
        raise MigrationError('No studio.db was found in the detected data folder. Use the same LDS_DATA_DIR as your launcher, or ask for help locating your data.')
    with migration_lock(root):
        return _migrate(root, data, port, protected, files, branch, before, confirm, check_only)


def _migrate(root, data, port, protected, files, branch, before, confirm, check_only):
    ensure_stopped(data, port)
    print('Checking the public v2 branch...', flush=True)
    git(root, 'fetch', '--no-tags', 'origin', 'refs/heads/v2:refs/remotes/origin/v2')
    target = output(root, 'rev-parse', 'refs/remotes/origin/v2^{commit}')
    protect_paths(root, before, target, protected)
    local_v2 = git(root, 'show-ref', '--verify', '--hash', 'refs/heads/v2', optional=True).stdout.decode().strip()
    if local_v2 and git(root, 'merge-base', '--is-ancestor', local_v2, target, optional=True).returncode:
        raise MigrationError('The existing v2 branch has different local history. It will not be reset.')
    if local_v2:
        protect_paths(root, local_v2, target, protected)
    print(f'Installation: {root}\nCurrent branch: {branch}\nData folder: {data}\nDestination: v2 ({target[:12]})')
    print('Images, datasets, plugins and Python environments stay in place.\n'
          'The tool backs up studio.db and settings, NOT the media library.\n'
          'Keep your normal media backup. Close LDS and its launcher until this finishes.')
    if check_only:
        print('Check complete. Application files and branch unchanged (remote Git references refreshed).')
        return {'status': 'checked', 'target': target}
    if confirm('Continue? Type V2 to confirm: ').strip().upper() != 'V2':
        print('Cancelled. Application files and branch unchanged.')
        return {'status': 'cancelled'}
    # Repeat the mutable preconditions after the user has read the plan.
    now_branch, now_head = preflight(root)
    if (now_branch, now_head) != (branch, before):
        raise MigrationError('The checkout changed while waiting. Run the check again.')
    if local_settings(root) != (data, port, protected, files):
        raise MigrationError('The data/runtime paths changed while waiting. Run the check again.')
    ensure_stopped(data, port)
    folder, reference, record = backup(root, files, branch, before, target)
    print(f'Backup: {folder}\nRecovery branch: {reference}', flush=True)
    switched = False
    try:
        ensure_stopped(data, port)
        clean_checkout(root)
        if (output(root, 'symbolic-ref', '--short', 'HEAD'), output(root, 'rev-parse', 'HEAD')) != (branch, before):
            raise MigrationError('The checkout changed during backup. Run the check again.')
        actual_v2 = git(root, 'show-ref', '--verify', '--hash', 'refs/heads/v2', optional=True).stdout.decode().strip()
        if actual_v2 != local_v2:
            raise MigrationError('The local v2 branch changed during migration. Run the check again.')
        if not local_v2:
            git(root, 'checkout', '--no-overwrite-ignore', '--no-recurse-submodules', '-b', 'v2', target)
            switched = True
        else:
            git(root, 'checkout', '--no-overwrite-ignore', '--no-recurse-submodules', 'v2')
            switched = True
            git(root, 'merge', '--ff-only', '--no-overwrite-ignore', '--no-edit', target)
        git(root, 'branch', '--set-upstream-to=origin/v2', 'v2')
        if output(root, 'rev-parse', 'HEAD') != target:
            raise MigrationError('The checked-out version does not match the reviewed destination.')
        for item in record['files']:
            if digest(Path(item['source'])) != item['sha256']:
                raise MigrationError('A data/settings file changed externally. Keep LDS closed and retain the backup for review.')
        record['status'] = 'complete'
    except (MigrationError, OSError) as exc:
        # No hard reset: even recovery must preserve any concurrent local edit.
        current = git(root, 'symbolic-ref', '--short', 'HEAD', optional=True).stdout.decode().strip()
        if switched and current == 'v2' and branch != 'v2':
            result = git(root, 'checkout', '--no-overwrite-ignore', '--no-recurse-submodules', branch, optional=True)
            record['status'] = 'stopped_original_branch' if result.returncode == 0 else 'needs_review'
        else:
            record['status'] = 'needs_review'
        (folder / 'recovery.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
        raise MigrationError(f'Migration stopped. Keep LDS closed. Backup: {folder}. Recovery branch: {reference}. {exc}') from exc
    (folder / 'recovery.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
    print('Done: this installation now follows v2. Database and settings match their pre-migration bytes.\n'
          'Start LDS with your usual launcher. On V2, choose optional features in Plugins > Store.\n'
          'Keep the backup until you have checked your datasets and settings in V2.\n'
          'The tool did not start the app or change its database schema.')
    return {'status': 'complete', 'backup': str(folder), 'reference': reference, 'target': target}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, help='Existing LDS installation folder')
    parser.add_argument('--check', action='store_true', help='Check only; fetch v2 but do not switch or back up')
    args = parser.parse_args(argv)
    try:
        root = args.root or Path(input('Existing LDS folder: ').strip().strip('"'))
        migrate(root, check_only=args.check)
    except (MigrationError, OSError) as exc:
        print(f'\nSTOP: {exc}', file=sys.stderr)
        return 1
    except (EOFError, KeyboardInterrupt):
        print('\nInterrupted. Keep LDS closed and review the checkout/backup before retrying.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
