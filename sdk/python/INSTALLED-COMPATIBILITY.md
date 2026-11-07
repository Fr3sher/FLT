# Installed package compatibility

The public V2 host provides the API 1.21 interfaces used by current Store
packages. No separate application fork is required for separately distributed
plugins. An official product identifier alone does not authorize an archive:
the existing signed-catalog and receipt checks still apply.

Shared interfaces cover H3 reference conditioning, model download specifications,
media snapshots, training provenance, and owned queue admission. Rendering policy,
screens, workflows specific to a product, and distribution archives remain in
their owning packages. The original public SDK names remain available for older
packages.

Persistent Video and publication fields are registered before database creation.
Existing databases receive additive columns; existing ORM mappings are retained.
An update preserves the installed packages and receipts under the configured data
directory. It does not reinstall models or fetch optional node packs. Model and
node preparation remains the package's registered installer responsibility.
