"""One data folder, one server — the guard behind it.

THE INCIDENT THIS PREVENTS. ``run.py`` slides to the next free port when the
configured one is taken (``find_available_port``) — the right behaviour when
the neighbour is some other app, and the wrong one when the neighbour is
ANOTHER COPY OF THIS APP on the same ``data/`` folder: launching ``start.bat``
while the app is already running produced a second server on :5051, sharing
the first one's SQLite database. Every in-memory contract silently halved —
the "one job per bank" registry, the progress the UI polls, the update lock —
because each process owned a private copy. A pass ran for half an hour in one
process while the other swore the bank was idle.

Two instances are a FEATURE when they own different data folders (worktree
verification, throwaway proof instances with their own ``LDS_DATA_DIR``);
this module never refuses those. It only refuses a second server on the SAME
data folder, and even that yields to ``LDS_ALLOW_SECOND_INSTANCE=1``.

HOW IT DECIDES. A ``server.lock`` JSON file in the data folder records the
serving pid and port. A lock alone proves nothing — crashes leave lock files
behind — so a boot only steps aside when BOTH hold: the recorded pid is still
alive, and ``/api/health`` answers on the recorded port. A stale lock (dead
pid, or a pid whose port no longer answers) is simply replaced. The in-app
restart survives this by construction: its detached helper waits for the old
process to release the port, so by relaunch time the old pid is dead and the
lock reads as stale.

Best-effort by design: two boots racing within the same probe window can both
pass. The guard exists for the human double-launch, minutes or days apart —
not as a mutex.

Plain module beside ``run.py`` (no app import) so the boot can use it before
anything heavy loads, and so pytest can exercise it without an app context.
"""
import ctypes
import json
import os
import time
import urllib.request

LOCK_FILENAME = 'server.lock'
BYPASS_ENV = 'LDS_ALLOW_SECOND_INSTANCE'

# How long the health probe may hold up a boot with a stale lock. Short on
# purpose: the probe only runs when a lock names a live pid, and a firewalled
# or hijacked port must cost a moment, not a hang.
HEALTH_TIMEOUT = 1.5


def lock_path(data_dir) -> str:
    return os.path.join(str(data_dir), LOCK_FILENAME)


def read_lock(data_dir) -> dict | None:
    """The recorded lock, or None for missing/corrupt/implausible content.
    Corruption degrades to "no lock": refusing to boot over an unreadable file
    would wedge the app with no way back short of manual surgery."""
    try:
        with open(lock_path(data_dir), encoding='utf-8') as fh:
            raw = json.load(fh)
        pid = int(raw['pid'])
        port = int(raw['port'])
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None
    if pid <= 0 or not (0 < port < 65536):
        return None
    return {'pid': pid, 'port': port, 'host': str(raw.get('host') or ''),
            'started_at': raw.get('started_at')}


if os.name == 'nt':
    # ⚠️ NEVER probe liveness with os.kill(pid, 0) on Windows: CPython maps any
    # signal other than CTRL_C/CTRL_BREAK onto TerminateProcess(handle, sig) —
    # "checking" a pid would KILL the running server with exit code 0. Ask the
    # process for its exit code instead; STILL_ACTIVE (259) means running.
    _PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    _STILL_ACTIVE = 259
    _ERROR_ACCESS_DENIED = 5

    def pid_alive(pid) -> bool:
        if pid <= 0:
            return False
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(
            _PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not handle:
            # No such process — or a process we may not open, which exists.
            return kernel32.GetLastError() == _ERROR_ACCESS_DENIED
        try:
            code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return code.value == _STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
else:
    def pid_alive(pid) -> bool:
        if pid <= 0:
            return False
        try:
            os.kill(int(pid), 0)     # signal 0: existence check only (POSIX)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True              # exists, owned by someone else
        except OSError:
            return False
        return True


def _probe_host(recorded_host) -> str:
    """Where to aim the health probe. The lock records the BIND host, and the
    wildcard binds are not connectable addresses."""
    return {'0.0.0.0': '127.0.0.1', '::': '::1', '': '127.0.0.1'}.get(
        str(recorded_host or ''), str(recorded_host))


def health_answers(host, port, timeout=HEALTH_TIMEOUT) -> bool:
    """Does an app-shaped server answer on that address? ``/api/health`` must
    return 200 with ``{"ok": true}`` — a port merely being open (reused by some
    other program) must not read as "the app is already running"."""
    probe = _probe_host(host)
    if ':' in probe and not probe.startswith('['):
        probe = f'[{probe}]'
    try:
        with urllib.request.urlopen(
                f'http://{probe}:{int(port)}/api/health', timeout=timeout) as res:
            if res.status != 200:
                return False
            body = json.loads(res.read().decode('utf-8', 'replace'))
    except Exception:
        return False
    return isinstance(body, dict) and body.get('ok') is True


def live_instance(data_dir, *, environ=os.environ,
                  _pid_alive=None, _health=None) -> dict | None:
    """The other server currently holding this data folder, or None.

    None when: bypassed via LDS_ALLOW_SECOND_INSTANCE=1, no/corrupt lock, the
    lock is OURS (same pid — the venv re-exec keeps the pid, so a restart never
    trips over its own file), the recorded pid is dead, or nothing app-shaped
    answers on the recorded port. The probes are injectable for tests.
    """
    if environ.get(BYPASS_ENV) == '1':
        return None
    lock = read_lock(data_dir)
    if not lock or lock['pid'] == os.getpid():
        return None
    alive = (_pid_alive or pid_alive)(lock['pid'])
    if not alive:
        return None
    answers = (_health or health_answers)(lock['host'], lock['port'])
    return lock if answers else None


def write_lock(data_dir, host, port) -> None:
    """Record this process as the folder's server. Replace-in-place via a temp
    file so a reader never sees a half-written JSON. Failures are swallowed —
    the lock is a guard for the next boot, never worth failing THIS one."""
    payload = {'pid': os.getpid(), 'host': str(host), 'port': int(port),
               'started_at': time.time()}
    path = lock_path(data_dir)
    tmp = f'{path}.tmp'
    try:
        with open(tmp, 'w', encoding='utf-8') as fh:
            json.dump(payload, fh)
        os.replace(tmp, path)
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass


def release_lock(data_dir) -> None:
    """Remove the lock — only when it is still OURS. A newer server may already
    have replaced it (we crashed earlier and were superseded); deleting its
    lock on our way out would disarm the guard for the process that needs it."""
    lock = read_lock(data_dir)
    if lock and lock['pid'] == os.getpid():
        try:
            os.remove(lock_path(data_dir))
        except OSError:
            pass


def refusal_message(info) -> str:
    """What the second launch prints before stepping aside. Names the address —
    the person who double-launched wanted the app, so point at where it is —
    and the way to override on purpose."""
    url = f"http://{_probe_host(info.get('host'))}:{info['port']}/"
    return (
        f"[LDS] LoRA Dataset Studio is already running on {url} "
        f"(PID {info['pid']}) using this same data folder.\n"
        "[LDS] A second server on the same data folder would run its own jobs "
        "over the same database — not starting this one.\n"
        "[LDS] Use the running app (address above), close it first, or set "
        f"{BYPASS_ENV}=1 to run two on purpose."
    )
