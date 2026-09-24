# Resource monitor

An independently installable LDS product containing its header and Canvas
readout, polling preferences, help and historical announcements. Canvas is
optional; the header works on a core-only installation.

The public `lds_sdk.hardware.machine_stats()` returns a cached snapshot. Core
training and maintenance still use the shared hardware probe and retain their
job guards. Installing this product grants no bypass of those guards.

Requires LDS API 1.9 or later in major version 1. No model download is needed.
