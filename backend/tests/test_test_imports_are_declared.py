"""A test module may not import a third-party package nobody declared.

THREE releases have now failed on the same shape, each time a different package:

* pytest-flask — present on a dev box, absent from CI, so nine tests that forgot
  `with app.app_context():` passed locally and came back red on the tag;
* safetensors — `test_zimage_convert_streaming.py` guarded on Torch with
  `importorskip` and then imported safetensors unguarded, which only bites on a
  machine that HAS Torch. That machine is CI;
* instaloader — `test_instagram_scan.py` imports it at module level. It ships in
  the OPTIONAL `requirements-scrape.txt`, so a contributor who ran the scraper
  once carries it transitively and stays green, while CI installs
  `requirements-dev.txt` and nothing else and cannot even COLLECT the module.

Each was found by a red release tag, which is the most expensive place to find it:
the suite is green on every machine that has the package, so nothing points at the
declaration until the release job runs. This test moves that discovery to the
commit that introduces it.

It is a PURE TEXT + AST check. It does not import anything, does not touch the
network, and does not care whether the package is installed HERE — being installed
here is precisely the illusion that let all three through.

WHAT IT DOES NOT COVER, on purpose: imports inside a function or a `try`. Those are
the shapes `pytest.importorskip` and lazy seams take, and both are legitimate — a
suite that runs a subset when an optional extra is absent is the intended design.
Only a MODULE-LEVEL import is a hard collection dependency.
"""
import ast
import json
import os
import re
import sys
import subprocess
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_BACKEND = _ROOT / 'backend'
_TESTS = _BACKEND / 'tests'

# Every file CI installs. requirements-dev.txt pulls requirements.txt with `-r`;
# the Torch overlay is separate and release always installs it.
_REQ_FILES = ('requirements.txt', 'requirements-dev.txt', 'requirements-torch-tests.txt')

# Distribution name -> import name, where they differ. Kept short and explicit
# rather than resolved through importlib.metadata: that would read the CURRENT
# environment, which is the very thing this test refuses to trust.
_IMPORT_NAME = {
    'opencv_python_headless': 'cv2',
    'opencv_python': 'cv2',
    'pillow': 'pil',
    'pyyaml': 'yaml',
    'python_dateutil': 'dateutil',
    'beautifulsoup4': 'bs4',
    'flask_sqlalchemy': 'flask_sqlalchemy',
}


def _declared() -> set:
    out = set()
    for name in _REQ_FILES:
        path = _BACKEND / name
        if not path.exists():
            continue
        for line in path.read_text(encoding='utf-8').splitlines():
            line = line.split('#')[0].strip()
            if not line or line.startswith('-'):
                continue
            dist = re.split(r'[<>=!\[;]', line)[0].strip().lower().replace('-', '_')
            out.add(dist)
            out.add(_IMPORT_NAME.get(dist, dist))
    return out


def _repo_local() -> set:
    """Tracked Python modules and explicit public plugin package roots only.

    A temporary virtualenv or fixture folder is not evidence of a local package.
    Product names come from their tracked manifest plus real package files, never
    from an unrestricted lds_* prefix.
    """
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith('GIT_')}
    env['GIT_ALLOW_PROTOCOL'] = ''
    result = subprocess.run(['git', '-C', str(_ROOT), 'ls-files', '-z', '--', 'backend', 'scripts', 'bundled'],
                            capture_output=True, check=True, env=env)
    tracked = {Path(name) for name in result.stdout.decode('utf-8').split('\0') if name}
    out = set()
    module_roots = {Path('backend'), Path('backend/tests'), Path('backend/infer'), Path('scripts')}
    for path in tracked:
        if path.suffix != '.py' or path.parts[0] not in ('backend', 'scripts'):
            continue
        if path.parent in module_roots:
            out.add(path.stem)
        if len(path.parts) > 2:
            out.add(path.parts[1])
        if path.parts[0] == 'scripts':
            out.add('scripts')
    for path in tracked:
        if len(path.parts) != 3 or path.parts[0] != 'bundled' or path.name != 'plugin.json':
            continue
        manifest = json.loads((_ROOT / path).read_text(encoding='utf-8'))
        package = manifest.get('python_package')
        if not isinstance(package, str) or not package.isidentifier():
            continue
        package_root = path.parent / package
        if any(candidate.suffix == '.py' and candidate.is_relative_to(package_root) for candidate in tracked):
            out.add(package)
    return out


def _module_level_imports(tree):
    """Only `tree.body` — an import nested in a function or a try is a deliberate
    soft dependency, not a collection requirement."""
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name.split('.')[0]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.module.split('.')[0]


def test_every_module_level_test_import_is_declared_or_repo_local():
    declared = _declared()
    local = _repo_local()
    stdlib = set(sys.stdlib_module_names)
    offenders = {}
    for path in sorted(_TESTS.glob('test_*.py')):
        try:
            tree = ast.parse(path.read_text(encoding='utf-8'))
        except SyntaxError:                      # a broken file fails elsewhere, loudly
            continue
        for name in _module_level_imports(tree):
            key = name.lower().replace('-', '_')
            if key in stdlib or key in local or key in declared or key == 'pytest':
                continue
            offenders.setdefault(path.name, set()).add(name)

    assert not offenders, (
        'a test module imports a package CI does not install — this is a collection '
        'ERROR on the release tag, not a skipped test:\n  '
        + '\n  '.join(f'{f}: {sorted(m)}' for f, m in sorted(offenders.items()))
        + '\nEither declare it in backend/requirements-dev.txt (if the test should '
          'really run in CI) or move the import inside the test behind '
          'pytest.importorskip (if the suite should shrink when the extra is absent).')


def test_the_guard_would_catch_the_three_packages_that_broke_a_release():
    """Proof the check discriminates, without mutating the repo: the three names
    that each cost a release must be classified as third-party — i.e. neither
    stdlib nor repo-local. Two of them are declared today, which is the fix; what
    this pins is that the CLASSIFIER would not wave them through as something
    else."""
    local = _repo_local()
    stdlib = set(sys.stdlib_module_names)
    assert 'lds_api_engines' in local  # a tracked, manifested package
    assert 'lds_unregistered_fixture' not in local  # no prefix exemption
    for name in ('safetensors', 'instaloader', 'pytest_flask'):
        assert name not in stdlib, f'{name} misread as stdlib'
        assert name not in local, f'{name} misread as a repo module'
