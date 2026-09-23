"""Bounded private evidence for rejected writer answers; never exposed by an API."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import re
import secrets
import threading

from lds_sdk.video_host import config as cfg
from lds_sdk.media import redact_tokens

_LOCK = threading.Lock()
_RECORD_NAME = re.compile(r'[0-9a-f]{32}\.json')
_URL = re.compile(r'(?i)\b[a-z][a-z0-9+.-]*://[^\s<>"\']+')
_PATH = re.compile(r'(?:[A-Za-z]:[\\/]|/|\\\\)[^\s<>"\']*[\\/][^\s<>"\']+')
_FILE = re.compile(r'(?i)\b[\w.-]+\.(?:png|jpe?g|webp|gif|mp4|webm|mov|wav|mp3|safetensors)\b')
_CREDENTIAL = re.compile(
    r'(?i)\b(?:password|passwd|secret|api[_-]?key|access[_-]?token|token)'
    r'(?:\\?["\'])?\s*[=:]\s*(?:\\?["\'])?[^\s,"\'<>]+')


def _bounded(value, limit, names):
    text = str(value or '')
    for name in names:
        text = text.replace(name, '[file]').replace(json.dumps(name)[1:-1], '[file]')
    text = _URL.sub('[url]', text)
    text = _PATH.sub('[path]', text)
    text = _FILE.sub('[file]', text)
    text = _CREDENTIAL.sub('[credential]', redact_tokens(text))
    return text.encode('utf-8')[:limit].decode('utf-8', errors='ignore')


def save(*, candidate, error, request, model, provider, references, attempt) -> dict:
    """Record sanitized answer/request text, not input file IDs or runner credentials.

    Request and candidate byte limits are independent. Truncation is detectable
    from their original character counts. Disk failures never own the writer result.
    """
    try:
        names = sorted({str(ref['name']) for ref in references if ref.get('name')},
                       key=len, reverse=True)
        clean = lambda value, limit: _bounded(value, limit, names)
        record = {
            'version': 1, 'created_at': datetime.now(timezone.utc).isoformat(),
            'attempt': int(attempt), 'provider': clean(provider, 100), 'model': clean(model, 300),
            'error': clean(error, 2000),
            'candidate': clean(candidate, 16000), 'candidate_chars': len(str(candidate or '')),
            'request': clean(request, 32000), 'request_chars': len(str(request or '')),
            'references': [{'tag': clean(ref.get('tag'), 100), 'role': clean(ref.get('role'), 1000)}
                           for ref in references[:18]],
        }
        payload = json.dumps(record, ensure_ascii=False, indent=2).encode('utf-8')
        identifier = secrets.token_hex(16)
        with _LOCK:
            root = cfg.data_dir().resolve()
            folder = root / 'reference-writer-traces'
            folder.mkdir(exist_ok=True)
            if folder.is_symlink() or folder.resolve() != folder:
                return {}
            # Prune only our own regular records. Unrelated operator files stay.
            prior = [p for p in folder.iterdir() if _RECORD_NAME.fullmatch(p.name)
                     and not p.is_symlink() and p.is_file()]
            for path in sorted(prior, key=lambda p: (p.stat().st_mtime_ns, p.name))[:-19]:
                path.unlink()
            # Exclusive creation: never follow an existing path or overwrite it.
            with (folder / f'{identifier}.json').open('xb') as output:
                output.write(payload)
        return {'id': identifier, 'sha256': hashlib.sha256(payload).hexdigest()}
    except (OSError, ValueError, TypeError):
        return {}
