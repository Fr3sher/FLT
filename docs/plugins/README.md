# LDS plugin authoring

A plugin is a complete feature package: its Python backend, screens, settings,
help and runtime assets travel together. The host provides the plugin API,
shared UI runtime, installation workers and lifecycle. Installable archives
contain the built browser interface and the plugin's own Python package.

## Shared source layout

Public first-party plugin sources live together under `bundled/<plugin-id>/`,
including [DLSS 5 Neural Rendering](../../bundled/dlss5/README.md). Each plugin
uses the same package contract:

| Path | Purpose |
| --- | --- |
| `plugin.json` | Identity, compatibility, permissions and owned capabilities |
| `lds_<plugin-id>/` | Python package with `register(ctx)` |
| `frontend/` | Screens, settings, help and contributions through the frontend SDK |
| `package.json` | Frontend entry point and declared dependencies |
| `lds-package.json` | Python packaging declarations when needed |
| `requirements-*.txt`, `infer/`, `resources/` | Plugin-owned dependencies, workers and assets when needed |
| `tests/`, `README.md`, `LICENSE` | Verification, usage and license |

Each plugin owns its preparation and persistent data and works without a
mandatory dependency on another LDS plugin. Optional integrations use the
documented SDK. The source directory does not auto-install or enable a plugin:
normal installations use the reviewed packages offered through Plugins.

## Authoring contract

- [Package format and compatibility](package-format.md)
- [Build, validate and package](packaging-guide.md)
- [JSON Schema for editors](plugin.schema.json)
- [API 1.20: declared ComfyUI node preparation](../../sdk/python/API-1.20.md)
- [API 1.21: protect active work during memory release](../../sdk/python/API-1.21.md)
- [Independent frontend SDK](../../sdk/frontend/README.md)

Plugin Python imports its own package, standard-library modules and documented
exports of `lds_sdk`. It must not import `app` or other host implementation
modules. The packaging tool checks the actual exports in the selected trusted
LDS checkout without starting the application. Frontend source imports
`@lds/plugin-sdk`; the independent builder keeps React and routing in the shared
host runtime and packages the plugin's styles separately.

Declare every owned installation action and node recipe in the manifest.
Register them through `ctx` during `register(ctx)`, without installing packages,
downloading models or starting rendering at plugin import. Preparation begins
only through an explicit user action, with the normal ownership and lifecycle
checks. A prepared node still needs a safe ComfyUI restart and a check of its
loaded classes before the feature can be shown as ready.

The manifest describes compatibility and permissions; it does not establish
publisher identity or sandbox plugin code. Packaging and installation trust are
separate checks. The developer tools described here create local artifacts and
do not publish them to a Store.

`lds_sdk.database.for_plugin(id, tables=...)` supplies the plugin's mapped base
and owned session. Its `func` and `or_` helpers construct SQLAlchemy expressions
for aggregates and boolean filters; querying or chaining a filter still checks
the complete statement against the plugin's tables. Use the named media SDKs,
such as `GalleryImages(user_id)` and `GalleryExports(user_id)`, to read host
gallery records and confined file paths instead of passing host models to the
plugin's session.
