"""Neutral package bytes for Store protocol proofs."""
import json
import zipfile


def contract(**over):
    value = {'id': 'camera_angles', 'name': 'Camera', 'version': '1.0.0', 'api': 1,
             'schema_version': 2, 'publisher': {'id': 'lds', 'name': 'LDS'},
             'compatibility': {'lds': '>=2026.9.4', 'api': '>=1.5,<2', 'python': '>=3.10,<4',
                               'os': ['windows', 'linux', 'darwin'], 'arch': ['x86_64', 'arm64']},
             'frontend': 'ui/index.js', 'frontend_styles': ['ui/styles.css']}
    value.update(over)
    return value


def archive(path, value, extra=None):
    with zipfile.ZipFile(path, 'w') as zf:
        for name, data in {'plugin.json': json.dumps(value), 'ui/index.js': '// UI',
                           'ui/styles.css': '.camera {color: red}', **(extra or {})}.items():
            zf.writestr(name, data)
    return path
