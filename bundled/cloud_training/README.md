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

Training offers must satisfy the CUDA version advertised by the selected pod
image, as well as the configured memory, disk and host filters. Keep **Verified
hosts only** enabled for the recommended host pool. An excluded host address
is never silently reintroduced when offers are scarce.

Confirmed container startup faults and GPU initialization failures stop a broken
LoRA rental promptly, even when the remote job still says "Starting job". The
existing single-retry policy applies only after release is confirmed. A moving
download or an advancing training step is not treated as a startup failure.

Licensed under PolyForm Noncommercial 1.0.0; see `LICENSE`.
