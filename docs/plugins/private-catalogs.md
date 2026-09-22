# Private plugin update sources

An operator can connect a signed catalog for specific private plugins without
replacing the public catalog. Its updates use the usual Plugins review and
apply flow. Plugin code and archives stay on the configured server.

Create `plugin-store/sources.json` in the LDS data directory:

```json
{
  "sources": [{
    "metadata_url": "https://plugins.example.org/metadata/",
    "target_url": "https://plugins.example.org/targets/",
    "root_path": "private-root.json",
    "plugin_ids": ["studio.depth"]
  }]
}
```

Supply the independently verified TUF bootstrap root alongside this file.
Root paths are relative to `sources.json`. Sources must use HTTPS, except for
a server bound to a literal loopback address on the same machine. The client
does not send account credentials, follow redirects or accept trust settings
from a downloaded package. A private server must restrict access to its files;
signatures authenticate downloads, they do not hide publicly served files.

Only the exact listed plugin IDs are accepted from each source. External IDs
use `publisher.plugin` and receive no first-party privileges. Sources cannot
overlap one another or replace first-party products authorized by the primary
catalog. Update plugins from different
catalogs separately; each review and transaction belongs to one source.
An unavailable source does not prevent other sources from being used. Cached
listings are display-only: every installation requires fresh valid signatures,
expiry checks and archive hashes. Removing a source stops its update offers;
installed plugins and their data remain available.

For a private first-party product using a historical LDS identifier, the operator
must additionally authorize that exact identifier in `official_ids`:

```json
{
  "sources": [{
    "metadata_url": "https://plugins.example.org/metadata/",
    "target_url": "https://plugins.example.org/targets/",
    "root_path": "private-root.json",
    "plugin_ids": ["manga", "studio.depth"],
    "official_ids": ["manga"]
  }]
}
```

This permission belongs in the locally installed source configuration, never
in an archive or downloaded catalog. It grants the selected root first-party
rights for that product: verify the root independently before authorizing it.
Every historical identifier in `plugin_ids` must be explicitly authorized, and
`official_ids` cannot include any unselected identifier or a primary-catalog
product. The signed archive still goes through the normal review, provenance
receipt and installation transaction. Existing projects retain their identifier
and data. These sources load during normal startup/browsing; no alternate
launcher or `LDS_STORE_CONFIG` override is needed.

Use `store/tools/repository.py` to publish immutable package versions. Keep
signing keys outside the served directory. Private sources and their packages
do not belong in the public LDS checkout. The ordinary app updater continues
to use the public LDS repository.
