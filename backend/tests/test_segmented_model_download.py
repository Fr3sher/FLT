"""Real HTTP transfers: exact assembly, bounded retries and safe fallback."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading

import pytest
import requests

from app.services import model_download as dl

PAYLOAD = bytes(range(256)) * 32


@contextmanager
def server(mode='ranges'):
    calls = []
    barrier = threading.Barrier(4) if mode == 'ranges' else None

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            range_header = self.headers.get('Range')
            calls.append(dict(self.headers))
            if mode == 'fallback-denied' and len(calls) > 1:
                self.send_response(403)
                self.end_headers()
                return
            if not range_header or mode == 'ignore':
                self.send_response(200)
                self.send_header('Content-Length', str(len(PAYLOAD)))
                if mode != 'no-ranges':
                    self.send_header('Accept-Ranges', 'bytes')
                if mode != 'no-etag':
                    self.send_header('ETag', 'W/"model"' if mode == 'weak-etag' else '"model"')
                self.end_headers()
                self.wfile.write(PAYLOAD)
                return
            start, end = map(int, range_header.removeprefix('bytes=').split('-'))
            if barrier:
                barrier.wait(timeout=5)
            if mode == 'denied':
                self.send_response(403)
                self.end_headers()
                return
            body = PAYLOAD[start:end + 1]
            retry_cut = mode == 'retry' and start == 0
            if mode == 'oversized':
                body += b'extra'
            if retry_cut:
                body = body[:256]
            self.send_response(206)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Content-Range', f'bytes {start + (mode == "bad-range")}-{end}/{len(PAYLOAD)}')
            self.send_header('ETag', '"changed"' if mode == 'changed' else '"model"')
            self.end_headers()
            self.wfile.write(body)

    httpd = ThreadingHTTPServer(('localhost', 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://localhost:{httpd.server_port}/model', calls
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join()


@pytest.mark.parametrize('mode', [
    'ranges', 'retry', 'ignore', 'bad-range', 'changed', 'oversized', 'denied',
    'no-ranges', 'no-etag', 'weak-etag',
])
def test_exact_bytes_and_fallback(tmp_path, monkeypatch, mode):
    monkeypatch.setattr(dl, 'SEGMENT_THRESHOLD', 1024)
    monkeypatch.setattr(dl, '_CHUNK', 128)
    progress, logs = [], []
    part = tmp_path / 'model.part'
    with server(mode) as (url, calls):
        with requests.get(url, stream=True, timeout=5) as response:
            done, total = dl.stream_model(
                response, url, part, headers={}, timeout=5,
                progress=lambda d, t: progress.append((d, t)), log=logs.append,
            )
    assert part.read_bytes() == PAYLOAD
    assert done == total == len(PAYLOAD)
    assert progress[-1] == (len(PAYLOAD), len(PAYLOAD))
    ranges = [c for c in calls if 'Range' in c]
    if mode in ('no-ranges', 'no-etag', 'weak-etag'):
        assert len(calls) == 1
        assert not logs
    elif mode in ('ranges', 'retry'):
        assert len(ranges) == (5 if mode == 'retry' else 4)
        assert all(c['If-Range'] == '"model"' for c in ranges)
        assert all(c['Accept-Encoding'] == 'identity' for c in ranges)
        assert [p[0] for p in progress] == sorted(p[0] for p in progress)
        if mode == 'retry':
            assert any(c['Range'] == 'bytes=256-2047' for c in ranges)
    else:
        assert ranges
        assert 'single connection' in logs[-1]
        assert sum('Range' not in c for c in calls) == 2


def test_small_file_keeps_single_connection(tmp_path, monkeypatch):
    monkeypatch.setattr(dl, 'SEGMENT_THRESHOLD', len(PAYLOAD) + 1)
    with server() as (url, calls):
        with requests.get(url, stream=True, timeout=5) as response:
            dl.stream_model(response, url, tmp_path / 'model.part', headers={},
                            timeout=5, progress=lambda *a: None, log=lambda *a: None)
    assert len(calls) == 1


@pytest.mark.parametrize('mode', ['ranges', 'fallback-denied'])
def test_installers_use_segmented_transfer_and_validate_before_replace(app, tmp_path, monkeypatch, mode):
    from app import setup_installer as si

    monkeypatch.setattr(dl, 'SEGMENT_THRESHOLD', 1024)
    monkeypatch.setattr(si, '_download_auth', lambda spec: ({}, 'hf'))
    monkeypatch.setattr(si, '_variant_already_present', lambda *a: None)
    monkeypatch.setattr(si, '_download_present_in_extra', lambda *a: False)
    monkeypatch.setattr(si, '_krea_asset_already_installed', lambda *a: False)
    monkeypatch.setattr(si, '_unloadable_reason', lambda *a: 'old model')
    monkeypatch.setattr(si, '_companion_unusable_reason', lambda *a: 'old model')
    monkeypatch.setattr(si, '_drop_condemned', lambda *a, **kw: None)
    for companion in (False, True):
        dest = tmp_path / ('companion' if companion else 'primary')
        dest.write_bytes(b'old')
        monkeypatch.setattr(si, '_download_dest_path', lambda *a: str(dest))
        monkeypatch.setattr(si, '_companion_dest_path', lambda *a: str(dest))

        def verify(action, part, spec, provider):
            assert dest.read_bytes() == b'old'
            assert open(part, 'rb').read() == PAYLOAD
            return True

        monkeypatch.setattr(si, '_verify_downloaded_model', verify)
        with app.app_context(), server(mode) as (url, calls):
            spec = {'url': url, 'companions': ({'url': url},)}
            monkeypatch.setattr(si, 'model_download_spec', lambda *a: spec)
            si._runs['segment-test'] = si._new_run()
            try:
                result = (si._fetch_companions('segment-test', spec, spec['companions'])
                          if companion else si._run_primary_download('segment-test'))
                assert result == (0 if mode == 'ranges' else 1)
                if mode == 'ranges':
                    assert si._runs['segment-test']['progress']['pct'] == 100
            finally:
                si._runs.pop('segment-test', None)
        assert dest.read_bytes() == (PAYLOAD if mode == 'ranges' else b'old')
        assert any('Range' in c for c in calls)
        assert not dest.with_name(dest.name + '.part').exists()
