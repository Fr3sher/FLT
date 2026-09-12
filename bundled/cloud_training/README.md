# Cloud training

Image and video training on rented GPUs, including full-model training, manual
continuation, checkpoint recovery, Hugging Face storage and model delivery.

The training SDK is qualified with the existing public database schema. Training
rentals persist a random ASCII identity before creation, retain their account
credentials in memory, and preserve ambiguous or unrecorded pods. Credentials
are never stored in rental metadata. After a restart, restore the original API
key to supervise a rental associated with that key.

An interrupted CREATE remains pending until its uniquely identified pod is
observed. An empty listing cannot authorize another paid rental. A pending
DELETE can be retried for the same recorded instance on the same account.

Video's cloud mutations dispatch to this product only while it is active. Run
history deletion preserves unconfirmed rentals. Local checkpoint history stays
readable when Cloud is disabled.

**Do not activate this snapshot against a live cloud account yet.** The separate
cloud-quantization rental lifecycle still needs qualification. Loading plugins
in a minimal test host does not qualify a production application startup.

All validation of this snapshot uses mocked provider responses and blocked
network sockets. No GPU rental or provider connection was used.

Licensed under PolyForm Noncommercial 1.0.0; see `LICENSE`.
