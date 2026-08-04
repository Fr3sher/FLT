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
"""
import os
import re
import subprocess

import pytest

import tests.test_no_personal_data as tnpd  # noqa: E402  (self-import for the seams below)

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Suffixes worth scanning. Binaries, lockfiles and the built bundle are excluded:
# dist is generated from sources this test already covers.
_SCANNED = ('.py', '.js', '.jsx', '.mjs', '.md', '.json', '.yml', '.yaml',
            '.html', '.css', '.bat', '.ps1', '.txt')
_SKIP_DIRS = ('frontend/dist/', 'docs/superpowers/', 'node_modules/')

_PATTERNS = {
    'a Windows user path': re.compile(r'[A-Za-z]:[\/]+Users[\/]+(?!<)[A-Za-z0-9._-]+', re.I),
    'an email address': re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b'),
    'an OpenAI-shaped key': re.compile(r'\bsk-[A-Za-z0-9]{20,}'),
    'a bearer token': re.compile(r'\bBearer\s+[A-Za-z0-9._-]{20,}'),
}
# Windows paths are only personal when the account name is one. A documented
# placeholder is what we WANT contributors to write.
_PLACEHOLDER_USERS = ('user', 'users', 'username', 'youruser', 'yourname',
                      'somebody', 'someone', 'me', 'you', 'public', 'default',
                      'all users', 'test', 'example')
# RFC 2606 / 6761 reserve these for documentation and tests; a fixture that
# uses one cannot belong to a person.
_RESERVED_DOMAINS = ('.example', '.test', '.invalid', '.localhost',
                     'example.com', 'example.net', 'example.org')
_ALLOWED_EMAILS = ('noreply@lora-dataset-studio.dev',)


def _is_personal_email(found, before):
    """`before` is the text immediately preceding the match.

    Three ways a match is NOT someone's address, each hit by a real fixture in
    this repo — the test is worthless if it cries wolf on all of them:
      * URL userinfo (`https://pexels.com@evil.example/`) — the domain-spoofing
        tests need exactly this shape;
      * a reserved documentation domain;
      * a stub too short to be anyone (`u@x.io`): a one-letter local part or a
        one-letter domain label is a placeholder, never a real mailbox.
    """
    if found in _ALLOWED_EMAILS:
        return False
    token = re.split(r'''[\s'"(\[<]''', before)[-1]    # the run glued to the match
    if '://' in token and '/' not in token.split('://', 1)[1]:
        return False                                   # userinfo inside a URL
    local, _, domain = found.rpartition('@')
    if any(domain.endswith(d) or domain == d for d in _RESERVED_DOMAINS):
        return False
    if len(local) < 3 or len(domain.split('.')[0]) < 3:
        return False
    return True


def _tracked_files():
    out = subprocess.run(['git', 'ls-files'], cwd=_REPO,
                         capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        pytest.skip('not a git checkout')
    for rel in out.stdout.splitlines():
        if not rel.endswith(_SCANNED):
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
        # This file necessarily contains the patterns it forbids.
        if rel.endswith('test_no_personal_data.py'):
            continue
        body = _read(rel)
        for label, rx in _PATTERNS.items():
            for m in rx.finditer(body):
                found = m.group(0)
                if label == 'an email address' and not _is_personal_email(
                        found, body[max(0, m.start() - 80):m.start()]):
                    continue
                if label == 'a Windows user path':
                    account = re.split(r'[\\/]+', found)[-1]
                    if account.lower() in _PLACEHOLDER_USERS:
                        continue
                line = body[:m.start()].count('\n') + 1
                hits.append(f'{rel}:{line} — {label}: {found[:60]}')
    assert not hits, (
        'personal data in a PUBLIC repo:\n  ' + '\n  '.join(hits[:20]))


def _git_common_dir():
    """The MAIN checkout's .git, seen from anywhere — including a linked worktree,
    where `.git` is a file pointing back here. Seam, so the resolution below can
    be tested without a real worktree."""
    out = subprocess.run(['git', 'rev-parse', '--git-common-dir'], cwd=_REPO,
                         capture_output=True, text=True, timeout=30)
    return out.stdout.strip() if out.returncode == 0 else ''


def _name_list():
    """The forbidden names, or None when no list can be found.

    THE ORDER MATTERS, AND THE THIRD ENTRY IS THE ONE THAT WAS MISSING. The list
    is gitignored on purpose — writing the names into the repository to forbid
    them would publish them, which is the whole problem. But gitignored also means
    ABSENT FROM EVERY WORKTREE, and worktrees are where the work happens. So this
    check disabled itself precisely where it was needed, skipping in silence, and
    three names reached the public repository in one week behind that skip.

    git knows where the main checkout is from anywhere, so the guard can too.
    """
    candidates = [os.environ.get('LDS_PRIVACY_NAMES'),
                  os.path.join(_REPO, '.privacy-names')]
    common = _git_common_dir()
    if common:
        # `--git-common-dir` is the MAIN checkout's .git, even from a worktree.
        candidates.append(os.path.join(os.path.dirname(os.path.abspath(common)),
                                       '.privacy-names'))
    for path in candidates:
        if path and os.path.isfile(path):
            with open(path, encoding='utf-8') as fh:
                return [w.strip() for w in fh
                        if w.strip() and not w.startswith('#')]
    return None


def _unpushed_range():
    """`origin/main..HEAD`, or '' when there is nothing to check (no remote yet,
    or everything already pushed). These commits are the last ones that can still
    be fixed for free: once a name is on the public remote, removing it means
    rewriting history, which breaks `pull --ff-only` for every install."""
    out = subprocess.run(['git', 'rev-list', '--count', 'origin/main..HEAD'],
                         cwd=_REPO, capture_output=True, text=True, timeout=60)
    if out.returncode != 0 or out.stdout.strip() in ('', '0'):
        return ''
    return 'origin/main..HEAD'


def _unpushed_text(rev_range):
    """(kind, text) for everything a reviewer would never re-read: the commit
    MESSAGES and the DIFFS. A name hides in either, and the message is the half
    that no file-content scan will ever see."""
    msgs = subprocess.run(['git', 'log', '--format=%B', rev_range], cwd=_REPO,
                          capture_output=True, text=True, timeout=120,
                          encoding='utf-8', errors='replace')
    if msgs.returncode == 0 and msgs.stdout:
        yield ('commit message', msgs.stdout)
    diff = subprocess.run(['git', 'diff', rev_range, '--', '.',
                           ':!frontend/dist'], cwd=_REPO, capture_output=True,
                          text=True, timeout=180, encoding='utf-8',
                          errors='replace')
    if diff.returncode == 0 and diff.stdout:
        yield ('diff', diff.stdout)


def test_no_forbidden_name_in_tracked_files():
    """Names come from a list kept OUT of the repo — writing them here to forbid
    them would publish them, which is the whole problem."""
    names = _name_list()
    if not names:
        pytest.skip('no name list — set LDS_PRIVACY_NAMES or add .privacy-names '
                    '(gitignored) to enable the name check')
    rx = re.compile(r'\b(' + '|'.join(re.escape(n) for n in names) + r')\b', re.I)
    hits = []
    for rel in _tracked_files():
        body = _read(rel)
        for m in rx.finditer(body):
            line = body[:m.start()].count('\n') + 1
            hits.append(f'{rel}:{line} — {m.group(0)}')
    assert not hits, (
        'a forbidden identifier is in the PUBLIC repo:\n  ' + '\n  '.join(hits[:20]))


# --- the guard's own blind spots ----------------------------------------------
# Three leaks reached the public repository in one week, and all three shared a
# cause that is NOT carelessness: the name half of this file skips in SILENCE when
# it cannot find its list, and the list is gitignored — so it is absent from every
# worktree, which is where the work happens. A guard that disables itself where it
# is needed protects only the places that never needed it.

def test_the_name_list_is_found_from_a_linked_worktree(monkeypatch, tmp_path):
    """A worktree has no `.privacy-names` of its own and never will: the file is
    gitignored on purpose. But git knows where the main checkout is, so the guard
    can too — `--git-common-dir` points at it from anywhere."""
    main = tmp_path / 'main'
    (main / '.git').mkdir(parents=True)
    (main / '.privacy-names').write_text('Nemo\n', encoding='utf-8')
    monkeypatch.delenv('LDS_PRIVACY_NAMES', raising=False)
    monkeypatch.setattr(tnpd, '_REPO', str(tmp_path / 'worktree'))
    monkeypatch.setattr(tnpd, '_git_common_dir', lambda: str(main / '.git'))

    assert tnpd._name_list() == ['Nemo']


def test_an_explicit_list_still_wins_over_the_discovered_one(monkeypatch, tmp_path):
    explicit = tmp_path / 'names.txt'
    explicit.write_text('Given\n', encoding='utf-8')
    monkeypatch.setenv('LDS_PRIVACY_NAMES', str(explicit))

    assert tnpd._name_list() == ['Given']


def test_no_forbidden_name_in_commits_that_have_not_been_pushed():
    """The last cheap moment. Correcting a name in the working tree does nothing
    for the copy already in a commit — and once that commit is on the public
    remote, removing it means rewriting history, which breaks `pull --ff-only` for
    every install that clones this repository.

    So the commits that are still LOCAL are the only ones that can still be fixed
    for free, and they are exactly the ones this checks: their messages AND their
    diffs, because a name can hide in either."""
    names = tnpd._name_list()
    if not names:
        pytest.skip('no name list available — see _name_list')
    unpushed = tnpd._unpushed_range()
    if not unpushed:
        pytest.skip('nothing unpushed to check')
    rx = re.compile(r'\b(' + '|'.join(re.escape(n) for n in names) + r')\b', re.I)

    hits = []
    for kind, body in tnpd._unpushed_text(unpushed):
        for m in rx.finditer(body):
            hits.append(f'{kind}: {m.group(0)}')
    assert not hits, (
        'a forbidden identifier is in a commit that has NOT been pushed yet — fix '
        'it now, while it is still free:\n  ' + '\n  '.join(sorted(set(hits))[:20]))
