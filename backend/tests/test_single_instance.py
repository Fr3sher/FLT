"""The one-data-folder-one-server guard, held to its own promises.

The incident: launching start.bat while the app was already running slid the
second server onto the next port — same database, private in-memory job
registries, a pass running in one process while the other swore the bank was
idle. The guard must refuse exactly that, and NOTHING else: worktree/proof
instances with their own LDS_DATA_DIR must boot untouched, crashes must not
wedge the app behind a stale lock, and the deliberate two-instance case keeps
an env override.
"""
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..')))
import single_instance as si  # noqa: E402


# ── the lock file itself ────────────────────────────────────────────────────

def test_no_lock_reads_as_no_instance(tmp_path):
    assert si.read_lock(tmp_path) is None
    assert si.live_instance(tmp_path, environ={}) is None


def test_write_then_read_round_trips(tmp_path):
    si.write_lock(tmp_path, '127.0.0.1', 5050)
    lock = si.read_lock(tmp_path)
    assert lock['pid'] == os.getpid()
    assert lock['port'] == 5050
    assert lock['host'] == '127.0.0.1'


@pytest.mark.parametrize('content', [
    '', 'not json', '{"pid": "nope", "port": 5050}', '{"port": 5050}',
    '{"pid": -4, "port": 5050}', '{"pid": 4242, "port": 0}',
    '{"pid": 4242, "port": 700000}',
])
def test_a_corrupt_or_implausible_lock_degrades_to_no_lock(tmp_path, content):
    # Refusing to boot over an unreadable file would wedge the app with no way
    # back short of deleting the file by hand.
    (tmp_path / si.LOCK_FILENAME).write_text(content, encoding='utf-8')
    assert si.read_lock(tmp_path) is None
    assert si.live_instance(tmp_path, environ={}) is None


def test_release_removes_only_our_own_lock(tmp_path):
    si.write_lock(tmp_path, '127.0.0.1', 5050)
    si.release_lock(tmp_path)
    assert si.read_lock(tmp_path) is None
    # A lock some OTHER process wrote survives our exit: deleting it would
    # disarm the guard for the server that still needs it.
    (tmp_path / si.LOCK_FILENAME).write_text(
        json.dumps({'pid': os.getpid() + 1, 'port': 5050}), encoding='utf-8')
    si.release_lock(tmp_path)
    assert si.read_lock(tmp_path) is not None


# ── pid liveness ────────────────────────────────────────────────────────────
# ⚠️ The naive probe — os.kill(pid, 0) — TERMINATES the target on Windows
# (CPython maps non-console signals onto TerminateProcess). These run against
# real pids to prove the platform branch actually answers, and answers without
# side effects: our own process must still be here afterwards.

def test_our_own_pid_is_alive():
    assert si.pid_alive(os.getpid()) is True


def test_a_finished_child_pid_is_dead():
    child = subprocess.Popen([sys.executable, '-c', 'pass'])
    child.wait()
    assert si.pid_alive(child.pid) is False


def test_nonsense_pids_are_dead():
    assert si.pid_alive(0) is False
    assert si.pid_alive(-1) is False


# ── the health probe ────────────────────────────────────────────────────────

class _Handler(BaseHTTPRequestHandler):
    body = b'{"ok": true}'
    status = 200

    def do_GET(self):  # noqa: N802 — http.server's spelling
        self.send_response(self.status)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(self.body)

    def log_message(self, *args):
        pass


@pytest.fixture
def health_server():
    server = HTTPServer(('127.0.0.1', 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()


def test_health_answers_on_a_real_ok_server(health_server):
    _Handler.body, _Handler.status = b'{"ok": true}', 200
    assert si.health_answers('127.0.0.1', health_server.server_port) is True


def test_an_open_port_that_is_not_the_app_does_not_count(health_server):
    # Port reuse is real: the pid may be alive and something ELSE may be
    # serving there. Only an app-shaped answer may refuse a boot.
    _Handler.body, _Handler.status = b'<html>hello</html>', 200
    assert si.health_answers('127.0.0.1', health_server.server_port) is False
    _Handler.body, _Handler.status = b'{"ok": true}', 503
    assert si.health_answers('127.0.0.1', health_server.server_port) is False


def test_a_closed_port_does_not_count():
    probe = HTTPServer(('127.0.0.1', 0), _Handler)
    port = probe.server_port
    probe.server_close()
    assert si.health_answers('127.0.0.1', port, timeout=0.5) is False


def test_wildcard_bind_hosts_are_probed_on_loopback():
    assert si._probe_host('0.0.0.0') == '127.0.0.1'
    assert si._probe_host('') == '127.0.0.1'
    assert si._probe_host('::') == '::1'
    assert si._probe_host('192.168.1.20') == '192.168.1.20'


# ── the decision ────────────────────────────────────────────────────────────

def _foreign_lock(tmp_path, port=5050):
    (tmp_path / si.LOCK_FILENAME).write_text(
        json.dumps({'pid': os.getpid() + 1, 'port': port,
                    'host': '127.0.0.1'}), encoding='utf-8')


def test_alive_pid_with_an_answering_port_refuses_the_boot(tmp_path):
    _foreign_lock(tmp_path)
    info = si.live_instance(tmp_path, environ={},
                            _pid_alive=lambda pid: True,
                            _health=lambda host, port: True)
    assert info and info['port'] == 5050


def test_a_dead_pid_is_a_stale_lock_and_boots(tmp_path):
    # Crashes leave lock files behind; a dead pid must never block a start.
    _foreign_lock(tmp_path)
    assert si.live_instance(tmp_path, environ={},
                            _pid_alive=lambda pid: False,
                            _health=lambda host, port: True) is None


def test_an_alive_pid_whose_port_stopped_answering_boots(tmp_path):
    # The pid may have been reused by an unrelated process — the port is the
    # tie-breaker, and it must be app-shaped (see the health tests).
    _foreign_lock(tmp_path)
    assert si.live_instance(tmp_path, environ={},
                            _pid_alive=lambda pid: True,
                            _health=lambda host, port: False) is None


def test_our_own_lock_never_refuses_us(tmp_path):
    # The venv re-exec keeps the pid; a boot must not trip over its own file.
    si.write_lock(tmp_path, '127.0.0.1', 5050)
    assert si.live_instance(tmp_path, environ={},
                            _pid_alive=lambda pid: True,
                            _health=lambda host, port: True) is None


def test_the_env_override_lets_a_second_instance_through(tmp_path):
    # Two-or-more instances are a FEATURE on separate data folders (worktree
    # verification, proof instances) — those never see this lock at all. The
    # override is for running two on the SAME folder deliberately.
    _foreign_lock(tmp_path)
    assert si.live_instance(tmp_path, environ={si.BYPASS_ENV: '1'},
                            _pid_alive=lambda pid: True,
                            _health=lambda host, port: True) is None


def test_the_refusal_names_the_address_the_pid_and_the_override(tmp_path):
    msg = si.refusal_message({'pid': 4242, 'port': 5050, 'host': '0.0.0.0'})
    assert 'http://127.0.0.1:5050/' in msg
    assert '4242' in msg
    assert si.BYPASS_ENV in msg
