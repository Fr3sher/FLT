# API 1.23 — local dataset engines

An autonomous plugin can contribute a local engine to Generate variations and
regeneration through `ctx.register_engine`. Declare its id in `owns.engines`,
`kind='local'`, and compatibility `>=1.23,<2`.

Two callbacks are required together:

- `local_preflight(*, reference_count=1, subject_type='human', **optional)`
  returns `{'ok': bool, 'detail': str}`. Check models, loaded ComfyUI nodes and
  supported reference count before any image rows or mixed paid jobs start.
- `local_enqueue(*, user_id, source_filename, source_path, edit_prompt,
  extra_ref_paths=(), aspect_ratio=None, extra_metadata=None, seed=None,
  subject_type='human', framing=None)` stages references and admits a workflow
  through `lds_sdk.comfy.queue.add_job`, returning its job id. Preserve the host
  metadata, especially `dataset_engine_plugin`, `is_dataset`, `dataset_id`,
  `engine_label` and `variation_label`. The durable owner marker rechecks plugin
  availability before execution and routes completion to the core dataset row,
  including failures/cancellations after the plugin is disabled. No hardcoded
  job name or plugin completion handler is necessary.

The host handles ownership, rows, status, stop, retry and prompt suffixes. The
plugin owns model selection, graph construction, identity instructions and
preparation. Recheck availability before each admission; plugins must not bypass
the host GPU queue. The host stores the raw creative prompt so retries do not
duplicate suffixes. Honor the supplied seed when present and the shot's aspect
ratio, with the shared `variations.output_megapixels` output budget.

Frontend `engine.spec` contributions with `kind: 'local'` can provide the same
`card` and `note` panels as API engines. Use `referenceEdit: false` for a dataset
engine: these callbacks do not implement the reference-edit dialog. The Python
entry must leave `extra.supports_reference_edit` false or absent. Keep settings,
help and installation in the owning plugin.

`lds_sdk.local_render.fetch_object_info_enums(timeout=None)` exposes the host's
cached native node choices. A missing response is unknown readiness, not proof
that a required sampler is supported.
