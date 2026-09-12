# Cloud training

Image and video training on rented GPUs, including full-model training, manual
continuation, checkpoint recovery, Hugging Face storage and model delivery.

This source extraction awaits host SDK integration and cloud-cleanup safety
qualification. **Do not activate this snapshot against a live cloud account.**
The inherited orphan sweep can treat another installation's `lds-<number>` pod
as its own. The offline regression in `tests/test_projection_guards.py` records
that limitation so the next safety patch can prove that it preserves such pods.

All validation of this snapshot uses mocked provider responses and blocked
network sockets. No GPU rental or provider connection was used.

Licensed under PolyForm Noncommercial 1.0.0; see `LICENSE`.
