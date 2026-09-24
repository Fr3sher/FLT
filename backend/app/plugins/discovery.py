"""Select plugin source discovery without importing migration or installer code."""
import os


def development_bundles():
    return (os.environ.get('LDS_PLUGIN_DISTRIBUTION', 'store') == 'development'
            or bool(os.environ.get('LDS_BUNDLED_DIR')))
