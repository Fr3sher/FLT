"""backend/extensions/ is a local-only drop-in dir. Three independent locks
keep it out of anything published: .gitignore (repo), runtime selection (bundle
build), check_release_artifacts (final ZIP). Each lock gets its own test so a
regression names the layer that broke.
"""
import importlib.util
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_backend_extensions_is_gitignored():
    proc = subprocess.run(
        ['git', 'check-ignore', '-q', 'backend/extensions/anything/__init__.py'],
        cwd=REPO_ROOT,
    )
    assert proc.returncode == 0, 'backend/extensions/ must be gitignored'


def test_release_zip_build_excludes_the_extensions_dir():
    spec = importlib.util.spec_from_file_location(
        'release_bundle', REPO_ROOT / 'packaging/release_bundle.py')
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    assert not builder.runtime_member('backend/extensions/private_plugin/__init__.py')
    assert builder.runtime_member('backend/app/plugins/loader.py')
