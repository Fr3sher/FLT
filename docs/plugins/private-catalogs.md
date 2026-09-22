# Private plugin update sources

An operator can connect a signed catalog for specific external plugins without
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

Only the exact listed `publisher.plugin` IDs are accepted from each source.
Sources cannot take over official LDS IDs or overlap one another. External
packages receive no first-party privileges. Update plugins from different
catalogs separately; each review and transaction belongs to one source.
An unavailable source does not prevent other sources from being used. Cached
listings are display-only: every installation requires fresh valid signatures,
expiry checks and archive hashes. Removing a source stops its update offers;
installed plugins and their data remain available.

Use `store/tools/repository.py` to publish immutable package versions. Keep
signing keys outside the served directory. Private sources and their packages
do not belong in the public LDS checkout. The ordinary app updater continues
to use the public LDS repository.
