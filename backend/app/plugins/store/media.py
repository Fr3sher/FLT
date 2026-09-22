"""Presentation downloads never consult purchase grants or installed code."""
from .catalog import parse_catalog
from .client import StoreError, StoreSession, config_for_plugins
from .media_contract import MAX_MEDIA_BYTES, validate_image


def read_image(plugin_id, version, image_id, filename):
    with StoreSession(config_for_plugins(plugin_id)) as session:
        catalog = parse_catalog(session.catalog(), session.config)
        release = next((entry for entry in catalog.get(plugin_id, ())
                        if entry.manifest.version == version), None)
        item = next((entry for entry in release.images
                     if entry['id'] == image_id and entry['target'].rsplit('/', 1)[-1] == filename), None) if release else None
        if item is None:
            raise StoreError('This presentation image is not available.')
        path, _ = session.target(item['target'], maximum=MAX_MEDIA_BYTES)
        data = path.read_bytes()
        try:
            content_type = validate_image(data, item)
        except ValueError as exc:
            raise StoreError('This presentation image could not be verified.') from exc
        return data, content_type
