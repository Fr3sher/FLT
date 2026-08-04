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
    # CLAUDE.md forbids IPs, but nothing enforced it: two addresses from a real
    # tailnet reached main and fifteen published releases, one of them under a
    # comment that said "real tailnet IP" out loud. A tailnet address is a stable
    # node identity, which is exactly what makes it worth catching — ordinary
    # RFC1918 LAN addresses stay allowed, they identify nobody.
    'a tailnet address': re.compile(r'\b100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d{1,3}\.\d{1,3}\b'),
}
# The block's edges and Tailscale's own documented service address are the only
# in-block literals a test may name. Anything else is somebody's machine.
_ALLOWED_TAILNET = ('100.64.0.0', '100.64.0.1', '100.127.255.254', '100.100.100.100')
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
    """Every file this repo would publish — tracked OR merely written.

    NOT `git ls-files`, which lists the tracked set only. A file that has been
    written and not yet `git add`ed would be invisible, so the guard would scan
    zero bytes of it and pass; it would become visible only once staged, which is
    after the moment most people run their tests. That blind spot let a first
    name reach a commit in August 2026, past a guard that was fully armed — see
    the note above the tests at the foot of this file.

    `--others --exclude-standard` adds the untracked files WITHOUT the ignored
    ones, and that exclusion is load-bearing rather than tidy: `.privacy-names`
    is gitignored and contains the very identifiers this guard forbids, so
    reading it would make the check fail on the file that arms it.

    The name is kept for its callers and its meaning widened on purpose — the
    thing worth scanning was never "what git tracks", it was "what is here".
    """
    out = subprocess.run(
        ['git', 'ls-files', '--cached', '--others', '--exclude-standard'],
        cwd=_REPO, capture_output=True, text=True, timeout=60)
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
                if label == 'a tailnet address' and found in _ALLOWED_TAILNET:
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


# --- the FOURTH leak, and the blind spot behind it ------------------------------
# The three leaks above were the name half skipping in silence. The fourth (a
# first name in a test docstring, August 2026) had a different cause and got past
# a guard that was fully armed: `_tracked_files()` enumerated with plain
# `git ls-files`, which lists TRACKED files only.
#
# So a file that has just been WRITTEN and not yet `git add`ed is invisible: the
# guard scans zero bytes of it and passes, honestly. It becomes visible only once
# it is staged — which is after the moment most people run their tests. The guard
# was therefore blind at exactly the point where new content enters the repo, and
# every new file was invisible on its first run, the only run that matters.
#
# That also made "run the suite on the FINAL tree" necessary but NOT sufficient:
# run it last and still before `git add`, and it passed. The workaround was an
# ordering rule nobody could be relied on to remember — `git add` → guard →
# commit — so the fix removes the need for it instead: the guard stops asking
# git for the TRACKED set and asks for the WORKING set. Run it whenever you like;
# it now sees what is on disk, staged or not.
#
# The cost of widening it, stated so it is not a surprise: a scratch file left in
# the tree is scanned too. That is the correct trade — an unstaged scratch file
# holding a machine path is one `git add .` away from being published, and this
# is the only check standing between the two.

def _init_repo(root, monkeypatch):
    """A throwaway git repo with one tracked file, one untracked file and one
    gitignored file — the three states whose treatment this pins."""
    root.mkdir(parents=True, exist_ok=True)
    run = lambda *a: subprocess.run(a, cwd=str(root), capture_output=True, text=True)
    run('git', 'init', '-q')
    (root / '.gitignore').write_text('secret.txt\n', encoding='utf-8')
    (root / 'tracked.py').write_text('# nothing to see\n', encoding='utf-8')
    run('git', 'add', '.gitignore', 'tracked.py')
    run('git', '-c', 'user.email=t@t', '-c', 'user.name=t', 'commit', '-qm', 'init')
    # Written but NEVER staged — the state the fourth leak was in.
    (root / 'brand_new.py').write_text('# Nemo wrote this\n', encoding='utf-8')
    # Gitignored, and holding a forbidden name on purpose: `.privacy-names`
    # itself lives like this, and scanning it would make the guard fail on the
    # very file that arms it.
    (root / 'secret.txt').write_text('Nemo\n', encoding='utf-8')
    monkeypatch.setattr(tnpd, '_REPO', str(root))
    return root


def test_a_file_that_is_written_but_not_staged_is_still_scanned(tmp_path, monkeypatch):
    """THE fourth leak, as a test. A brand-new file carrying a forbidden name has
    to be seen BEFORE it is staged — otherwise the guard's green light means
    "nothing wrong with what you committed last time"."""
    _init_repo(tmp_path / 'repo', monkeypatch)

    scanned = set(tnpd._tracked_files())

    assert 'brand_new.py' in scanned, (
        'a new, unstaged file is invisible to the guard — which is exactly when '
        'new content enters the repo')
    assert 'tracked.py' in scanned


def test_a_gitignored_file_is_never_scanned(tmp_path, monkeypatch):
    """The other half of the same change, and it is load-bearing: widening the
    enumeration must NOT start reading ignored files. `.privacy-names` is
    gitignored and holds the very names this guard forbids — scanning it would
    make the guard fail on the file that arms it, on every machine that has one."""
    _init_repo(tmp_path / 'repo', monkeypatch)

    scanned = set(tnpd._tracked_files())

    assert 'secret.txt' not in scanned


def test_the_name_check_actually_flags_a_new_unstaged_file(tmp_path, monkeypatch):
    """End to end over the seam, with a fake list: the mechanism above only
    matters because it changes the VERDICT. Written as the fourth leak would have
    been caught."""
    _init_repo(tmp_path / 'repo', monkeypatch)
    monkeypatch.setattr(tnpd, '_name_list', lambda: ['Nemo'])

    hits = []
    rx = re.compile(r'\b(Nemo)\b', re.I)
    for rel in tnpd._tracked_files():
        for m in rx.finditer(tnpd._read(rel)):
            hits.append(f'{rel} — {m.group(0)}')

    assert any(h.startswith('brand_new.py') for h in hits)
    assert not any(h.startswith('secret.txt') for h in hits)
