"""TUF verifies remote metadata and bytes; the app owns the initial trust root.

Configuration is installed by the operator, never accepted from the catalog or
an uploaded ZIP. Each root/origin pair has its own rollback-protected metadata
cache. Expiration can stop new downloads, never the installed application.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import requests
from filelock import FileLock
from tuf.api.exceptions import DownloadHTTPError
from tuf.ngclient import Updater
from tuf.ngclient.fetcher import FetcherInterface

from ... import config as cfg
from ..install import MAX_TOTAL_BYTES, _entry_relpath
from ..official import OFFICIAL_IDS
from ..storage import managed_path

_LOCK = threading.RLock()
CATALOG_TARGET = 'catalog.json'
MAX_CATALOG_BYTES = 2 * 1024 * 1024


class StoreError(ValueError):
    """A public, path- and credential-free reason to stop an operation."""


class StoreNotConfigured(StoreError):
    pass


def _base_url(value):
    if not isinstance(value, str):
        raise StoreError('The store URL is invalid.')
    try:
        parsed = urlsplit(value)
        _ = parsed.port  # Validate malformed/out-of-range ports before opening a connection.
    except ValueError as exc:
        raise StoreError('The store URL is invalid.') from exc
    if (not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment
            or '%' in parsed.path or '\\' in value or any(ord(c) < 33 for c in value)
            or '..' in parsed.path.split('/')):
        raise StoreError('The store URL is invalid.')
    local = False
    try:
        local = ipaddress.ip_address(parsed.hostname).is_loopback
    except ValueError:
        pass
    if parsed.scheme != 'https' and not (parsed.scheme == 'http' and local):
        raise StoreError('A store requires HTTPS. Only loopback test servers may use HTTP.')
    return value.rstrip('/') + '/'


@dataclass(frozen=True)
class StoreConfig:
    metadata_url: str
    target_url: str
    root: bytes
    official_ids: frozenset

    def __post_init__(self):
        object.__setattr__(self, 'metadata_url', _base_url(self.metadata_url))
        object.__setattr__(self, 'target_url', _base_url(self.target_url))
        if (not isinstance(self.root, bytes) or not 0 < len(self.root) <= 512000
                or not isinstance(self.official_ids, (set, frozenset))
                or any(pid not in OFFICIAL_IDS for pid in self.official_ids)):
            raise StoreError('The store trust configuration cannot be verified.')
        object.__setattr__(self, 'official_ids', frozenset(self.official_ids))

    @property
    def identity(self):
        return hashlib.sha256(self.root + self.metadata_url.encode() + b'\0' + self.target_url.encode()).hexdigest()


def load_config():
    path = Path(os.environ.get('LDS_STORE_CONFIG') or cfg.REPO_ROOT / 'store' / 'bootstrap.json')
    if not path.is_file():
        raise StoreNotConfigured('The store has not been connected to a trusted catalog yet.')
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        root_path = Path(data['root_path'])
        if not root_path.is_absolute():
            root_path = path.parent / root_path
        root = root_path.read_bytes()
        ids = data.get('official_ids', [])
        if (not root or len(root) > 512000 or not isinstance(ids, list)
                or any(not isinstance(pid, str) or pid not in OFFICIAL_IDS for pid in ids)):
            raise ValueError('invalid trust configuration')
        return StoreConfig(_base_url(data['metadata_url']), _base_url(data['target_url']), root, frozenset(ids))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise StoreError('The store trust configuration cannot be verified.') from exc


class _Fetcher(FetcherInterface):
    """Public TUF transport: no redirects, credentials or paid download grants."""
    def __init__(self, config):
        self.config = config

    def _fetch(self, url):
        # TUF generates metadata URLs and validated target paths. Enforce the
        # same portable path profile here before requests can normalize a URL.
        normalized = _base_url(url).rstrip('/')
        if normalized != url.rstrip('/'):
            raise StoreError('A store download contains an invalid URL.')
        if not any(url.startswith(base) for base in (self.config.metadata_url, self.config.target_url)):
            raise StoreError('A store download left its configured origin.')
        headers = {'User-Agent': 'LDS-Plugin-Store/1', 'Accept-Encoding': 'identity'}
        with requests.Session() as session:
            # Public metadata/archives must never inherit NETRC credentials,
            # authenticated proxies, cookies or custom CA settings from the host.
            session.trust_env = False
            with session.get(url, headers=headers, stream=True, timeout=(10, 30), allow_redirects=False) as response:
                if response.status_code != 200:
                    raise DownloadHTTPError('The store download failed.', response.status_code)
                for chunk in response.iter_content(chunk_size=65536):
                    if chunk:
                        yield chunk


class StoreSession:
    """One fresh TUF update under the cache lock, never shared across requests."""
    def __init__(self, config=None):
        self.config = config or load_config()
        self.updater = None
        self.cache_lock = None

    def __enter__(self):
        _LOCK.acquire()
        try:
            self.folder = managed_path(cfg.data_dir(), 'plugin-store', 'catalogs', self.config.identity)
            metadata = managed_path(self.folder, 'metadata')
            metadata.mkdir(parents=True, exist_ok=True)
            self.cache_lock = FileLock(str(managed_path(self.folder, 'update.lock')), timeout=30)
            self.cache_lock.acquire()
            self.updater = Updater(str(metadata), self.config.metadata_url,
                                   target_base_url=self.config.target_url,
                                   bootstrap=self.config.root, fetcher=_Fetcher(self.config))
            self.updater.refresh()
            return self
        except Exception as exc:
            if self.cache_lock is not None:
                self.cache_lock.release()
            _LOCK.release()
            raise StoreError('The catalog could not be authenticated or is unavailable. Installed plugins are unaffected.') from exc

    def __exit__(self, *args):
        self.cache_lock.release()
        _LOCK.release()

    def target_info(self, name, *, maximum=MAX_TOTAL_BYTES):
        if (not isinstance(name, str) or _entry_relpath(name) != name
                or any(c in name for c in ('%', '?', '#', '\\'))):
            raise StoreError('The catalog contains an invalid target path.')
        info = self.updater.get_targetinfo(name)
        if info is None or not 0 < info.length <= maximum or 'sha256' not in info.hashes:
            raise StoreError('This release is unavailable or exceeds the supported package size.')
        return info

    def target_destination(self, info):
        # Hash filenames avoid both target path traversal and cache aliasing.
        return managed_path(self.folder, 'targets', info.hashes['sha256'])

    def target(self, name, *, maximum=MAX_TOTAL_BYTES):
        info = self.target_info(name, maximum=maximum)
        dest = self.target_destination(info)
        try:
            if not self.updater.find_cached_target(info, str(dest)):
                self.updater.download_target(info, str(dest))
            return dest, info
        except Exception as exc:
            raise StoreError('The package download failed verification. No installed plugin was changed.') from exc

    def catalog(self):
        path, _ = self.target(CATALOG_TARGET, maximum=MAX_CATALOG_BYTES)
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError) as exc:
            raise StoreError('The authenticated catalog is not valid JSON.') from exc
