"""Exercise real Git checkouts against disposable local remotes; no app launch."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess

import pytest

spec = importlib.util.spec_from_file_location('migration', Path(__file__).parents[1] / 'migrate_to_v2.py')
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.PIPE).decode().strip()


@pytest.fixture
def installation(tmp_path, monkeypatch):
    for key in migration.ENV_KEYS | {'LDS_RUNTIME'}:
        monkeypatch.delenv(key, raising=False)
    source = tmp_path / 'upstream'
    source.mkdir()
    git(source, 'init', '-q', '-b', 'main')
    git(source, 'config', 'user.name', 'LDS test')
    git(source, 'config', 'user.email', 'test@example.invalid')
    for name, text in {
        'backend/run.py': '# old app\n', 'frontend/dist/index.html': 'old UI\n',
        '.gitignore': 'data/\nconfig.json\n.env\n.venv/\nignored.txt\n',
    }.items():
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    git(source, 'add', '.')
    git(source, 'commit', '-qm', 'Old public version')
    root = tmp_path / 'LDS installation with spaces'
    git(tmp_path, 'clone', '-q', str(source), str(root))
    git(source, 'checkout', '-qb', 'v2')
    (source / 'backend/run.py').write_text('# V2 app\n')
    git(source, 'commit', '-qam', 'V2 public version')
    data = root / 'data'
    data.mkdir()
    with sqlite3.connect(data / 'studio.db') as db:
        db.execute('CREATE TABLE datasets (name TEXT)')
        db.execute("INSERT INTO datasets VALUES ('kept dataset')")
    db.close()
    for name, body in {
        'data/datasets/one/photo.png': b'media bytes',
        'data/datasets/one/photo.txt': b'caption bytes',
        'data/plugins/example/plugin.json': b'plugin bytes',
        'data/plugin-data/example/settings.json': b'plugin settings',
        '.venv/keep.txt': b'environment bytes',
        'config.json': b'{"paths":{}}', '.env': b'EXAMPLE_KEY=local-test-value\n',
    }.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
    # Only the test substitutes a local transport and suppresses unrelated host ports.
    monkeypatch.setattr(migration, 'official_remote', lambda value: Path(value) == source)
    monkeypatch.setattr(migration, 'ensure_stopped', lambda *args: None)
    return root, source


def snapshot(root):
    return {path.relative_to(root).as_posix(): path.read_bytes() for directory in ('data', '.venv')
            for path in (root / directory).rglob('*') if path.is_file()} | {
                name: (root / name).read_bytes() for name in ('config.json', '.env')}


def test_migration_preserves_data_settings_plugins_runtime_and_recovery(installation):
    root, source = installation
    before = git(root, 'rev-parse', 'HEAD')
    original = snapshot(root)
    result = migration.migrate(root, confirm=lambda _: 'V2')
    assert result['status'] == 'complete'
    assert git(root, 'branch', '--show-current') == 'v2'
    assert git(root, 'rev-parse', 'HEAD') == git(source, 'rev-parse', 'v2')
    assert git(root, 'rev-parse', '@{upstream}') == result['target']
    assert git(root, 'rev-parse', result['reference']) == before
    assert snapshot(root) == original
    backup = Path(result['backup'])
    record = json.loads((backup / 'recovery.json').read_text())
    assert record['status'] == 'complete' and not record['media_backed_up']
    assert (backup / next(item['backup'] for item in record['files'] if item['source'].endswith('studio.db'))).read_bytes() == original['data/studio.db']
    assert not (root / '.git/lds-migration.lock').exists()
    # Safe to run a second time; already-on-v2 does not lose the data either.
    assert migration.migrate(root, confirm=lambda _: 'V2')['status'] == 'complete'
    assert snapshot(root) == original


@pytest.mark.parametrize('kind', ['tracked_edit', 'staged_edit', 'local_commit', 'hidden_edit', 'git_operation', 'other_branch'])
def test_refuses_local_work_without_changing_it(installation, kind):
    root, _ = installation
    if kind in {'tracked_edit', 'staged_edit', 'local_commit', 'hidden_edit'}:
        (root / 'backend/run.py').write_text('# local customization\n')
    if kind == 'staged_edit':
        git(root, 'add', '.')
    if kind == 'local_commit':
        git(root, '-c', 'user.name=LDS test', '-c', 'user.email=test@example.invalid', 'commit', '-qam', 'Local work')
    if kind == 'hidden_edit':
        git(root, 'update-index', '--assume-unchanged', 'backend/run.py')
    if kind == 'git_operation':
        (root / '.git/MERGE_HEAD').write_text(git(root, 'rev-parse', 'HEAD'))
    if kind == 'other_branch':
        git(root, 'checkout', '-qb', 'personal-work')
    head = git(root, 'rev-parse', 'HEAD')
    source = (root / 'backend/run.py').read_bytes()
    with pytest.raises(migration.MigrationError):
        migration.migrate(root, confirm=lambda _: 'V2')
    assert git(root, 'rev-parse', 'HEAD') == head
    assert (root / 'backend/run.py').read_bytes() == source
    assert not (root / '.git/lds-migration-backups').exists()


@pytest.mark.parametrize('check_only,answer,status', [(True, 'V2', 'checked'), (False, 'no', 'cancelled')])
def test_check_and_cancel_leave_branch_and_files(installation, check_only, answer, status):
    root, _ = installation
    original = snapshot(root)
    before = git(root, 'rev-parse', 'HEAD')
    assert migration.migrate(root, check_only=check_only, confirm=lambda _: answer)['status'] == status
    assert git(root, 'branch', '--show-current') == 'main'
    assert git(root, 'rev-parse', 'HEAD') == before
    assert snapshot(root) == original
    assert not (root / '.git/lds-migration-backups').exists()


@pytest.mark.parametrize('ignored', [True, False])
def test_untracked_collision_is_never_overwritten(installation, ignored):
    root, source = installation
    name = 'ignored.txt' if ignored else 'untracked.txt'
    (root / name).write_text('user content')
    (source / name).write_text('new app content')
    git(source, 'add', '-f', name)
    git(source, 'commit', '-qm', 'Add colliding file')
    original = snapshot(root)
    with pytest.raises(migration.MigrationError, match='Migration stopped'):
        migration.migrate(root, confirm=lambda _: 'V2')
    assert (root / name).read_text() == 'user content'
    assert git(root, 'branch', '--show-current') == 'main'
    assert snapshot(root) == original


@pytest.mark.parametrize('path', ['data/studio.db', 'config.json', '.venv/keep.txt'])
def test_rejects_target_that_tracks_user_state(installation, path):
    root, source = installation
    candidate = source / path
    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.write_text('bad source path')
    git(source, 'add', '-f', path)
    git(source, 'commit', '-qm', 'Track runtime data')
    original = snapshot(root)
    with pytest.raises(migration.MigrationError, match='overlaps'):
        migration.migrate(root, confirm=lambda _: 'V2')
    assert snapshot(root) == original
    assert git(root, 'branch', '--show-current') == 'main'


def test_external_data_directory_is_preserved_and_backed_up(installation, tmp_path):
    root, _ = installation
    external = tmp_path / 'external data'
    shutil.copytree(root / 'data', external)
    (root / '.env').write_text('LDS_DATA_DIR="' + external.as_posix() + '"\n')
    data = (external / 'studio.db').read_bytes()
    result = migration.migrate(root, confirm=lambda _: 'V2')
    assert (external / 'studio.db').read_bytes() == data
    record = json.loads((Path(result['backup']) / 'recovery.json').read_text())
    assert any(item['source'] == str(external / 'studio.db') for item in record['files'])


def test_existing_v2_fast_forwards(installation):
    root, source = installation
    git(root, 'branch', 'v2')
    result = migration.migrate(root, confirm=lambda _: 'V2')
    assert result['target'] == git(source, 'rev-parse', 'v2')


def test_backup_failure_prevents_branch_change(installation, monkeypatch):
    root, _ = installation
    def fail(*args, **kwargs):
        raise OSError('simulated disk failure')
    monkeypatch.setattr(migration.shutil, 'copy2', fail)
    with pytest.raises(OSError, match='simulated'):
        migration.migrate(root, confirm=lambda _: 'V2')
    assert git(root, 'branch', '--show-current') == 'main'


def test_missing_database_does_not_guess_user_data_location(installation):
    root, _ = installation
    (root / 'data/studio.db').rename(root / 'data/fixture-database-saved.db')
    with pytest.raises(migration.MigrationError, match='No studio.db'):
        migration.migrate(root, confirm=lambda _: 'V2')
    assert git(root, 'branch', '--show-current') == 'main'
    assert not (root / '.git/lds-migration-backups').exists()


def test_failure_after_switch_returns_to_original_branch(installation, monkeypatch):
    root, _ = installation
    original = snapshot(root)
    real_git = migration.git
    def fail_tracking(root, *args, **kwargs):
        if '--set-upstream-to=origin/v2' in args:
            raise migration.MigrationError('simulated tracking failure')
        return real_git(root, *args, **kwargs)
    monkeypatch.setattr(migration, 'git', fail_tracking)
    with pytest.raises(migration.MigrationError, match='Migration stopped'):
        migration.migrate(root, confirm=lambda _: 'V2')
    assert git(root, 'branch', '--show-current') == 'main'
    assert snapshot(root) == original
    record = next((root / '.git/lds-migration-backups').glob('*/recovery.json'))
    assert json.loads(record.read_text())['status'] == 'stopped_original_branch'


def test_changed_data_path_during_confirmation_is_rejected(installation, tmp_path):
    root, _ = installation
    def change_path(_):
        (root / '.env').write_text('LDS_DATA_DIR=' + (tmp_path / 'other').as_posix())
        return 'V2'
    with pytest.raises(migration.MigrationError, match='paths changed'):
        migration.migrate(root, confirm=change_path)
    assert git(root, 'branch', '--show-current') == 'main'


def test_concurrent_external_branch_switch_is_not_undone(installation, monkeypatch):
    root, _ = installation
    real_backup = migration.backup
    def backup_then_external_switch(*args):
        result = real_backup(*args)
        git(root, 'checkout', '-qb', 'other-work')
        return result
    monkeypatch.setattr(migration, 'backup', backup_then_external_switch)
    with pytest.raises(migration.MigrationError, match='checkout changed'):
        migration.migrate(root, confirm=lambda _: 'V2')
    assert git(root, 'branch', '--show-current') == 'other-work'


def test_concurrent_migration_is_refused(installation):
    root, _ = installation
    with migration.migration_lock(root):
        with pytest.raises(migration.MigrationError, match='Another migration'):
            migration.migrate(root, confirm=lambda _: 'V2')
    assert git(root, 'branch', '--show-current') == 'main'


def test_fetch_failure_does_not_create_backup_or_switch(installation):
    root, source = installation
    git(source, 'checkout', '-q', 'main')
    git(source, 'branch', '-D', 'v2')
    with pytest.raises(migration.MigrationError, match='fetch'):
        migration.migrate(root, confirm=lambda _: 'V2')
    assert git(root, 'branch', '--show-current') == 'main'
    assert not (root / '.git/lds-migration-backups').exists()


def test_running_process_is_detected_without_terminating_it(tmp_path):
    process = subprocess.Popen([os.sys.executable, '-c', 'import time; time.sleep(60)'])
    try:
        (tmp_path / 'server.lock').write_text(json.dumps({'pid': process.pid, 'port': 5050}))
        with pytest.raises(migration.MigrationError, match='running'):
            migration.ensure_stopped(tmp_path, 5050)
        assert process.poll() is None
    finally:
        process.terminate()
        process.wait(timeout=10)


def test_zip_install_is_guided_without_changes(installation):
    root, _ = installation
    # Move only the disposable fixture's Git metadata, never a real installation.
    (root / '.git').rename(root.parent / 'fixture-git-backup')
    original = snapshot(root)
    with pytest.raises(migration.MigrationError, match='ZIP installation'):
        migration.migrate(root, confirm=lambda _: 'V2')
    assert snapshot(root) == original


def test_official_remote_allowlist():
    assert migration.official_remote('https://github.com/perfectgf/lora-dataset-studio.git')
    ssh = 'ssh://git@github.com/perfectgf/lora-dataset-studio.git'
    assert migration.official_remote(ssh)
    assert migration.official_remote(ssh.removeprefix('ssh://').replace('.com/', '.com:'))
    for value in ('https://github.com/perfectgf/lora-dataset-studio-nightly.git',
                  'https://github.com/another-user/lora-dataset-studio.git',
                  'https://github.com.evil.invalid/perfectgf/lora-dataset-studio.git'):
        assert not migration.official_remote(value)


@pytest.mark.skipif(os.name != 'nt', reason='Windows launcher')
def test_windows_launcher_handles_spaces_and_shell_metacharacters(tmp_path):
    bundle = tmp_path / 'tool bundle'
    bundle.mkdir()
    launcher = bundle / 'migrate-to-v2.bat'
    shutil.copyfile(Path(__file__).parents[1] / 'migrate-to-v2.bat', launcher)
    (bundle / 'migrate_to_v2.py').write_text('import json, sys; print("ARGS=" + json.dumps(sys.argv[1:]))')
    root = tmp_path / 'LDS & datasets (local)'
    root.mkdir()
    result = subprocess.run([os.environ['COMSPEC'], '/d', '/c', str(launcher)],
                            input=str(root) + '\n\n', text=True, capture_output=True,
                            timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'ARGS=' + json.dumps(['--root', str(root)]) in result.stdout
