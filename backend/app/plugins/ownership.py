"""Manifest claims shared by boot and installation planning; no plugin imports."""
from .manifest import GUIDE_OWNS, OWNS_LISTS


def claims(manifest):
    result = {(kind, name) for kind in OWNS_LISTS + GUIDE_OWNS for name in manifest.owned(kind)}
    result.update(('config_key', f'{section}.{key}')
                  for section, keys in manifest.owns.get('config_keys_in_shared_sections', {}).items()
                  for key in keys)
    return result


def conflict(manifests):
    owners = {}
    for manifest in manifests:
        for claim in sorted(claims(manifest)):
            owner = owners.get(claim)
            if owner is not None and owner != manifest.id:
                return {'kind': claim[0], 'name': claim[1], 'owners': (owner, manifest.id)}
            owners[claim] = manifest.id
    return None
