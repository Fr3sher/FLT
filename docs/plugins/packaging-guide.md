# Build a distributable LDS plugin

The frontend builder compiles a plugin's browser source. The Python CLI then
validates a staged directory and writes a reproducible ZIP. Validation never
imports plugin code, starts LDS, installs runtime dependencies or contacts a
Store. Its JavaScript audit parses source with Acorn without evaluating it.

## Developer tools

Use Python 3.10 or newer with `packaging`, and the Node version declared by the
frontend SDK. Install the locked developer dependencies in a development
checkout:

```sh
npm ci --prefix sdk/frontend --ignore-scripts
npm ci --prefix sdk/python --ignore-scripts
```

`--lds-source` selects a trusted checkout containing the public SDK, version
constants, manifest rules and backend requirements. It defaults to the CLI's
checkout. The adapter reads literal SDK/API version declarations without
executing the SDK. `--js-tools DIRECTORY` or `LDS_PLUGIN_JS_TOOLS` can select an
existing trusted directory containing `node_modules/acorn`; the default is
`sdk/python`. Missing parser tooling is an error, not a skipped check.

Public Python exports come from a literal `__all__` list or the lazy-adapter
form `__all__ = list(_EXPORTS)` with a literal mapping. An explicitly exported
compatibility name can begin with an underscore; undeclared names and private
attributes remain refused. The adapter never executes an export expression.

## Stage, build, validate, pack

Create a new staging directory outside the source. Copy the manifest, licence,
Python package and required runtime assets into it. Compile the frontend into
its empty `frontend/` subdirectory:

```sh
node sdk/frontend/build.mjs --plugin /work/plugin-source --out /work/plugin-stage/frontend
```

In the staged manifest set `frontend` to `frontend/index.js` and
`frontend_styles` to `["frontend/styles.css"]`. For a plugin with declared
workers, also translate the generated `build-report.json` worker entries and
loader paths relative to the staging root. Keep generated chunks and notices
with the entry. Do not include the unbuilt JSX/TypeScript tree in the stage.

```sh
python scripts/plugin_package.py validate /work/plugin-stage --lds-source /work/lds
python scripts/plugin_package.py pack /work/plugin-stage --lds-source /work/lds --output /work/releases/plugin.ldsplugin
```

Create the output parent directory first. Output must be outside the staged
tree; an existing archive requires explicit `--overwrite`. Both commands print
JSON; success exits 0 and a validation/filesystem error exits 2. The report
includes normalized metadata, included file hashes, excluded paths and observed
dependency declarations. `pack` adds the final archive path and SHA-256.

For a registered LDS product being converted from its own bundled source, add
`--official-lds`. This explicit authoring mode verifies its ID against the
selected source registry and normalizes `bundled` to false. It grants no
installation or Store trust and cannot relabel another publisher.

## Included bytes and exclusions

Keep maintainer build tools in `authoring/`. The CLI excludes that directory,
tests, hidden directories, environments, caches, `node_modules`, data, logs,
credentials, model weights and build-only manifests/reports. Runtime code
cannot depend on excluded files. Prebuilt wheels, licences and provenance
belong in runtime resources, with their exact declarations in `node_packs`.
The [API 1.20 contract](../../sdk/python/API-1.20.md) defines their installation.

The validator checks all declared frontend/styles and node-wheel bytes before
creating an archive. The resulting ZIP has sorted paths, fixed timestamps and
permissions and no compression; identical validated bytes produce identical
archives. Publication uses a temporary snapshot and preserves an existing
destination unless replacement was requested.

## Imports and dependencies

Python can use its own package, the standard library and public `lds_sdk`
exports. The checker rejects private host imports, undeclared backend imports,
common dynamic-loading mechanisms and import-path manipulation. A bounded set
of host libraries is permitted only when actually present as unconditional
backend requirements in the selected checkout; used constraints are recorded
in `host_dependencies`. They do not instruct the installer to alter the host.

A plugin virtual environment does not extend the backend process import path.
Isolated worker scripts require an explicit build-only `lds-package.json`
profile with `python_scripts` and `python_dependencies`, plus an included
versioned requirements file. Optional first-party in-process dependencies have
their own explicit reviewed profile. These static profiles do not prove the
worker's runtime behavior or sandbox a plugin.

JavaScript imports must resolve inside the staged package. Bundle external
browser dependencies first; source JSX/TypeScript/CommonJS, undeclared worker
loaders and CSS imports are refused. Keep browser assets referenced by CSS in
the package: the current audit checks declared CSS and JavaScript import edges,
not every CSS URL or runtime network request.

Before distribution, inspect the report and validate the archive with the
target host's normal archive checks. A package check does not certify loaded
ComfyUI nodes, image quality, GPU execution or the trust of a distribution
channel. The CLI only creates a local artifact; publication is a separate step.
