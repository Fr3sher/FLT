# LDS plugin package format

`plugin.json` belongs at the package root. New distributable packages use
`schema_version: 2`. The [JSON Schema](plugin.schema.json) describes the shape;
the host's manifest and package-contract validators additionally check semantic
rules such as PEP 440 ranges, portable paths and ownership before import.

```json
{
  "schema_version": 2,
  "id": "example.preview",
  "name": "Preview",
  "version": "1.0.0",
  "api": 1,
  "publisher": {"id": "example", "name": "Example tools"},
  "compatibility": {
    "lds": ">=2026.9,<2027",
    "api": ">=1.20,<2",
    "python": ">=3.10,<4",
    "os": ["windows", "linux", "darwin"],
    "arch": ["x86_64", "arm64"]
  },
  "python_package": "example_preview",
  "frontend": "frontend/index.js",
  "frontend_styles": ["frontend/styles.css"],
  "requires": [],
  "dependency_versions": {},
  "data_schema": 1,
  "owns": {},
  "permissions": []
}
```

Declare the platforms actually supported by the product. `api` is the API major;
`compatibility.api` constrains the full API version. `version` and version ranges
follow Python packaging rules. Unknown schema versions, boolean versions, empty
ranges and npm-style ranges are refused. Prerelease compatibility requires an
explicit prerelease bound in the relevant range.

`publisher.id` and `publisher.name` are declarations, not verified provenance.
An ordinary external plugin uses a namespaced ID. Reserved LDS product IDs need
separate installation provenance; a manifest cannot grant itself trust with a
`bundled`, `official`, receipt or publisher field.

`requires` lists actual plugin dependencies. Every `dependency_versions` key
must also occur there. A shared host service or ComfyUI node does not require a
dependency on another product that happens to use it.

All frontend, CSS, requirements and runtime asset paths are relative to the
package root. Declare built ESM JavaScript, all generated CSS and, when used,
the builder's worker entries/loaders. Each declared asset must be included and
nonempty. The Python entry is `<python_package>/__init__.py`; the runtime also
supports a separately validated native-backend profile for API 1.19 or newer.

The host rejects absolute/traversing paths, links, alternate data streams,
portable-name collisions and missing assets. The publisher tool applies a
strict portable source profile before taking its immutable byte snapshot.
`data_schema` describes persistent plugin data; it does not run a migration or
promise that a plugin-code rollback also rolls back shared environments.

## Node installations require API 1.20

A `node_packs` entry without `installation` remains informational. An executable
recipe requires schema 2, an explicit API floor of 1.20, `comfyui` and
`filesystem` permissions, and an action owned by this plugin. The recipe pins
its archive URL, SHA-256, version, destination folder and expected node classes.
Dependencies use exact versions. ComfyUI's Python range is declared separately
from the plugin backend's Python compatibility.

Author-supplied wheels name an included relative `wheelhouse` and exact
filename/hash pairs. Both the packaging CLI and archive inspection require
every declared wheel to be present, no larger than 64 MiB and equal to its
declared SHA-256. The preparation worker additionally validates wheel metadata,
destinations and compatibility with the existing environment. It never builds
a source distribution on the user's machine.

See [API 1.20](../../sdk/python/API-1.20.md) for the full recipe, registration,
sharing and restart contract. See [packaging](packaging-guide.md) for staging
and the local CLI.
