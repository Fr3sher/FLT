"""Bounded HTTP range transfers into an installer's temporary file.

Only segment an unencoded representation with a strong ETag. If a host does
not honour ranges or the representation changes, discard the partial transfer
and fetch one complete representation. Callers own validation and publication.
"""
from concurrent.futures import ThreadPoolExecutor
import re
import threading

import requests

SEGMENT_THRESHOLD = 256 * 1024 * 1024
SEGMENT_WORKERS = 4
_CHUNK = 1024 * 1024
_SLOTS = threading.BoundedSemaphore(8)


class _RangeRefused(requests.RequestException):
    pass


def _plain(response, part, progress):
    if response.status_code != 200:
        response.raise_for_status()
        raise requests.RequestException('Expected a complete model response')
    total = int(response.headers.get('content-length') or 0)
    done = 0
    progress(0, total)
    with open(part, 'wb') as output:
        for chunk in response.iter_content(chunk_size=_CHUNK):
            if chunk:
                output.write(chunk)
                done += len(chunk)
                progress(done, total)
    if total and done != total:
        raise requests.RequestException('Incomplete model download')
    return done, total


def stream_model(response, url, part, *, headers, timeout, progress, log):
    """Consume an open, status-checked response; return (bytes written, total).

    Resolve timeout/configuration before starting workers: they do not inherit
    the Flask context. Always restart from the original URL so requests applies
    its normal cross-host credential stripping to every redirect.
    """
    total = int(response.headers.get('content-length') or 0)
    etag = response.headers.get('etag', '')
    can_segment = (
        response.status_code == 200 and total >= SEGMENT_THRESHOLD
        and response.headers.get('accept-ranges', '').lower() == 'bytes'
        and response.headers.get('content-encoding', 'identity').lower() == 'identity'
        and re.fullmatch(r'"[^"\r\n]+"', etag) is not None
    )
    if not can_segment:
        return _plain(response, part, progress)

    response.close()
    log(f'downloading with {SEGMENT_WORKERS} parallel segments')
    progress(0, total)
    # Each worker opens its own handle and writes only its assigned interval.
    with open(part, 'wb') as output:
        output.truncate(total)
    lock = threading.Lock()
    stopped = threading.Event()
    completed = 0

    def segment(start, end):
        nonlocal completed
        position = start
        try:
            with _SLOTS, open(part, 'r+b') as output:
                for attempt in range(3):
                    if stopped.is_set():
                        return
                    segment_headers = {**headers, 'Accept-Encoding': 'identity',
                                       'Range': f'bytes={position}-{end}', 'If-Range': etag}
                    try:
                        with requests.get(url, headers=segment_headers, stream=True,
                                          allow_redirects=True, timeout=timeout) as reply:
                            expected = f'bytes {position}-{end}/{total}'
                            if (reply.status_code != 206
                                    or reply.headers.get('content-range') != expected
                                    or reply.headers.get('etag') != etag
                                    or reply.headers.get('content-encoding', 'identity').lower() != 'identity'):
                                raise _RangeRefused('Server did not return the requested model segment')
                            output.seek(position)
                            for chunk in reply.iter_content(chunk_size=_CHUNK):
                                if stopped.is_set():
                                    return
                                if not chunk:
                                    continue
                                if position + len(chunk) > end + 1:
                                    raise _RangeRefused('Model segment exceeded its declared range')
                                output.write(chunk)
                                position += len(chunk)
                                with lock:
                                    completed += len(chunk)
                                    progress(completed, total)
                            if position != end + 1:
                                raise requests.ConnectionError('Incomplete model segment')
                            return
                    except _RangeRefused:
                        raise
                    except requests.RequestException:
                        if attempt == 2 or position == end + 1:
                            raise
        except Exception:
            stopped.set()
            raise

    try:
        # The executor joins ALL writers before fallback truncates the file.
        with ThreadPoolExecutor(max_workers=SEGMENT_WORKERS,
                                thread_name_prefix='model-download') as pool:
            futures = [pool.submit(segment, total * i // SEGMENT_WORKERS,
                                   total * (i + 1) // SEGMENT_WORKERS - 1)
                       for i in range(SEGMENT_WORKERS)]
            for future in futures:
                future.result()
        return completed, total
    except requests.RequestException:
        log('segmented transfer unavailable; restarting with a single connection')
        with requests.get(url, headers={**headers, 'Accept-Encoding': 'identity'},
                          stream=True, allow_redirects=True, timeout=timeout) as reply:
            return _plain(reply, part, progress)
