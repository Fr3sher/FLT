"""The repo is public and the account behind it is pseudonymous.

CLAUDE.md forbids real names, machine paths, emails and tokens in code,
comments, commits and test fixtures. That rule was respected by intent and
broken by accretion: twelve comments had picked up the maintainer's first name
in ten days — several written the same night, by different agents and by me.
A rule nothing enforces is a rule that decays.

TWO KINDS OF CHECK, on purpose:

* PATTERNS always run and need no secret list — a Windows user path, an email,
  a bearer token or an API key shape has no business in this repo whoever you
  are. This is the half that protects a contributor who never read CLAUDE.md.

* NAMES are read from a list that is NOT in the repo, because writing the name
  down to forbid it would publish it. Point `LDS_PRIVACY_NAMES` at a file (one
  identifier per line) or drop `.privacy-names` next to the repo root — both are
  gitignored. With no list the name check SKIPS and says so: a silent pass would
  be worse than no test.

WHAT THIS FILE DOES NOT SEE — read `scripts/check_release_artifacts.py`:
it walks `git ls-files`, so untracked and ignored files are invisible to it,
and it skips the compiled bundle. The archive scan covers exactly that blind
spot by reading the published ZIP instead. Both import their patterns from
`scripts/privacy_patterns.py`; there is one table, not two.
"""
import os
import subprocess
import sys

import pytest

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Appended, not prepended: this must not shadow a backend module for the rest
# of the pytest session.
_SCRIPTS = os.path.join(_REPO, 'scripts')
if _SCRIPTS not in sys.path:
    sys.path.append(_SCRIPTS)

import privacy_patterns as privacy  # noqa: E402  (needs the path above)

# The built bundle and vendored docs stay out: dist is generated from sources
# this test already covers, and the archive scan reads the shipped bundle itself.
_SKIP_DIRS = ('frontend/dist/', 'docs/superpowers/', 'node_modules/')


def _tracked_files():
    out = subprocess.run(['git', 'ls-files'], cwd=_REPO,
                         capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        pytest.skip('not a git checkout')
    for rel in out.stdout.splitlines():
        if not privacy.is_scannable(rel):
            continue
        if any(rel.startswith(d) for d in _SKIP_DIRS):
            continue
        yield rel


def _read(rel):
    try:
        with open(os.path.join(_REPO, rel), encoding='utf-8', errors='replace') as fh:
            return fh.read()
    except OSError:
        return ''


def test_no_machine_path_email_or_token_in_tracked_files():
    r"""The half that needs no secret list — and would have caught a pasted
    diagnostic containing `C:\Users\<someone>` long before a human noticed."""
    hits = []
    for rel in _tracked_files():
        body = _read(rel)
        for line, label, found in privacy.scan_text(body):
            hits.append(f'{rel}:{line} — {label}: {found[:60]}')
    assert not hits, (
        'personal data in a PUBLIC repo:\n  ' + '\n  '.join(hits[:20]))


def _name_list():
    path = os.environ.get('LDS_PRIVACY_NAMES') or os.path.join(_REPO, '.privacy-names')
    return privacy.read_name_list(path)


def test_no_forbidden_name_in_tracked_files():
    """Names come from a list kept OUT of the repo — writing them here to forbid
    them would publish them, which is the whole problem."""
    rx = privacy.name_pattern(_name_list())
    if rx is None:
        pytest.skip('no name list — set LDS_PRIVACY_NAMES or add .privacy-names '
                    '(gitignored) to enable the name check')
    hits = []
    for rel in _tracked_files():
        body = _read(rel)
        for m in rx.finditer(body):
            line = body[:m.start()].count('\n') + 1
            hits.append(f'{rel}:{line} — {m.group(0)}')
    assert not hits, (
        'a forbidden identifier is in the PUBLIC repo:\n  ' + '\n  '.join(hits[:20]))
