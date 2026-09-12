# app/scrape/sources/gdl_source.py
"""Base paramétrable des sources gérées par gallery-dl (P4). Une nouvelle source =
sous-classe ~10 lignes : platform_enum + name/priority/capabilities + gdl_opts +
cookies_key. match() = host (via validators.detect_platform) ; scan/download
délèguent au moteur gdl.py."""
import os

from .base import Source, Match
from . import gdl
# The credentials folder is the core's (app/utils/credentials.py): the same
# resolver serves the Civitai key to the Studio's browser and to Setup. Kept
# under its historical name here for the sources that import it.
from lds_sdk.credentials import resolve_credential_file as resolve_cookies  # noqa: F401 — re-export


class GalleryDlSource(Source):
    """Source gallery-dl générique. Les sous-classes définissent :
       platform_enum, name, priority, capabilities, gdl_opts (list|None), cookies_key (str|None)."""
    platform_enum = None
    gdl_opts = None
    cookies_key = None

    def _cookies(self):
        return resolve_cookies(self.cookies_key)

    def match(self, url):
        from ..validators import url_validator
        if url_validator.detect_platform(url) == self.platform_enum:
            return Match(url=url, validation=None)
        return None

    def scan(self, match):
        return gdl.enumerate(match.url, platform=self.name,
                             cookies=self._cookies(), extra_opts=self.gdl_opts)

    def download(self, url, dest_base):
        dest_dir = os.path.dirname(dest_base)
        filename = os.path.basename(dest_base)
        ok, abs_path, err = gdl.download(url, dest_dir, filename,
                                         cookies=self._cookies(), extra_opts=self.gdl_opts)
        if not ok or not abs_path:
            return False, None, err or f'{self.name} download failed.'
        return True, os.path.basename(abs_path), None
