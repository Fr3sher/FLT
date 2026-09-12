# Klein Improve

Klein Improve supplies prompt-based image improvement, its instruction and LoRA editors, settings, finishing and image actions across compatible LDS galleries. It requires LDS plug-in API 1.12 or newer (below API 2) and a configured ComfyUI with Klein models. Base Klein generation remains in LDS.

SeedVR2 is a separate optional plug-in. Neither product requires the other. Klein Improve owns the Klein improvement engine and its settings; SeedVR2 owns its restoration engine and settings.

Existing Klein settings, image identifiers and result metadata remain unchanged. `improve.engine` remains an LDS preference among active providers. Klein owns `improve.colour_match`, `improve.sharpen`, `improve.grain` and `improve.grain_saturation`; the last value also remains the historical Studio per-run grain colour fallback.
