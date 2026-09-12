# LDS plugin authoring

A plugin is a complete feature package: its Python backend, screens, settings,
help and runtime assets travel together. The host provides the plugin API,
shared UI runtime, installation workers and lifecycle. Installable archives
contain the built browser interface and the plugin's own Python package.

- [Package format and compatibility](package-format.md)
- [Build, validate and package](packaging-guide.md)
- [JSON Schema for editors](plugin.schema.json)
- [API 1.20: declared ComfyUI node preparation](../../sdk/python/API-1.20.md)
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
