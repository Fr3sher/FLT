"""The publisher owns its mapped model; stored table identities stay stable."""
from lds_sdk.database import for_plugin

db = for_plugin('civitai_publish', tables=('civitai_link',))


class CivitaiLink(db.BaseMapped):
    __table__ = db.table('civitai_link')
