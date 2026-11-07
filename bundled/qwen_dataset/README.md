# Dataset Forge

An independent LDS plugin that generates dataset variations locally with
**Qwen-Image 2.1**. Its engine card appears in **Generate variations**. Select
the dataset's shots, choose Dataset Forge and curate the generated images in
the existing dataset grid. Each shot uses its own normal LDS queue job, so
progress, cancellation and regeneration follow the dataset workflow.

## Preparation

Requires LDS plugin API **1.23** and a running ComfyUI with the native
`TextEncodeQwenImage21` and `QwenImage21Cache` nodes. Preparation checks the
actual loaded node classes and sampler choices. If they are absent, update
ComfyUI through its normal updater and restart it when no work is running,
then recheck. No custom node pack or extra LDS plugin is required.

Open **Plugins → Dataset Forge → Settings** to prepare the three model files:

| Component | Default file | Bytes |
| --- | --- | ---: |
| Diffusion model | `qwen_image_2.1_int8_convrot.safetensors` | 7,256,783,064 |
| Text encoder | `qwen3vl_8b_int8_convrot.safetensors` | 9,350,798,360 |
| VAE | `qwen_image_2.1_vae_bf16.safetensors` | 675,509,688 |

Files come from [Comfy-Org's model repository](https://huggingface.co/Comfy-Org/Qwen-Image-2.1).
The installer reuses these files and their BF16 alternatives across configured
ComfyUI model roots, including subfolders. Preparation downloads only the
missing assets. Existing valid files remain in place. The disk total is about
17.28 GB; this is not a VRAM requirement or a measured render memory budget.

An explicit model selection must resolve to an installed official INT8 or
BF16 file listed above (a subfolder is allowed). Renamed and custom checkpoints
are not supported in this initial version.
Clear a stale selection to restore automatic discovery. Qwen-Image-Edit 2511,
Qwen 2.5-VL and the older Qwen VAE are different architectures and are never
chosen by automatic discovery. A structurally invalid file blocks rendering
and appears as a repairable asset in preparation.

## References and settings

The primary reference and every selected extra reference describe the same
subject. One to ten references are accepted; extra or missing references are
reported before images are staged, never silently dropped. Try a front view
and a profile view first. The prompt wrapper follows the chosen subject type,
including animals, objects and illustrated characters.

Default sampling uses **25 steps, CFG 3, res_multistep / simple**, inspired by
the community dataset workflow. Reference images are resized around a
1024 × 1024 pixel budget, preserving their aspect ratio on multiples of 32.
The output uses the shared **variation megapixels** setting and each shot's
aspect ratio. This custom output framing can shift an edit relative to its
reference; review difficult profiles and full-body shots before training.
The model's official editing recipe uses different guidance defaults; these
community defaults are a starting point, not an image-quality guarantee.

The plugin owns `plugins.qwen_dataset`: model selections (`unet`,
`text_encoder`, `vae`), `steps` (1–100), `cfg` (0–30),
`reference_resolution` (256–2048, multiple of 32), `negative_prompt`,
`sampler_name`, `scheduler`, `cache_device` and `cache_dtype`.
The cache defaults to automatic device placement and default precision.
Reference editing is not exposed; this version supports dataset generation
and regeneration.

## License and credits

Plugin code uses the included PolyForm Noncommercial license. Model weights
are separately governed by the
[Qwen Research License](https://huggingface.co/Qwen/Qwen-Image-2.1/blob/main/LICENSE),
which permits noncommercial research and evaluation; commercial use requires
a separate license. Review its attribution conditions before distributing a
model trained or improved using generated images. Weights are downloaded from
the publisher and are not included in the plugin archive.

Inspired by **Jolanoff**'s
[Qwen 2.1 dataset generator](https://www.reddit.com/r/comfyui/comments/1wnlgko/qwen_21_dataset_generator/)
and **acekiube**'s original
[face dataset generation workflow](https://www.reddit.com/r/comfyui/comments/1o6xgqk/free_face_dataset_generation_workflow_for_lora/).
The plugin implements its own compact API graph using ComfyUI's native
[Qwen nodes](https://github.com/Comfy-Org/ComfyUI/blob/master/comfy_extras/nodes_qwen.py)
and [official editing template](https://github.com/Comfy-Org/workflow_templates/blob/main/templates/image_qwen_image_2_1_image_edit.json).
It does not embed the third-party workflow, custom prompt loops or custom node
dependencies.

## Authoring and validation

Follow the shared [plugin packaging guide](../../docs/plugins/packaging-guide.md).
The archive contains this Python package, the independently built frontend,
manifest, documentation and license. There are no Python worker dependencies
or bundled model files. CPU tests verify the graph, reference handling,
readiness and queue metadata. They do not establish GPU runtime, identity
fidelity, render speed or memory use; those require a subsequent image trial.
