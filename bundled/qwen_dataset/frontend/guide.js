export const GUIDE = { chapters: [], sections: [{
  chapter: 'settings-reference', anchor: 'dataset-forge-qwen-image-2-1',
  markdown: `## Dataset Forge: Qwen-Image 2.1

Dataset Forge adds **Qwen-Image 2.1 · local** beside Klein and Krea in a dataset’s **Generate variations** panel. Select the shots and framing you already use, then generate and curate the results in the normal dataset grid. Retry keeps the image’s original engine. This engine does not appear in the separate reference-photo editor.

### Prepare Dataset Forge

Open **Plugins → Dataset Forge → Settings**. Connect your local ComfyUI folder in Local tools, then prepare the Qwen-Image 2.1 model, Qwen3-VL text encoder and VAE. Compatible installed files are reused; the default files total about 17.3 GB. Each preparation action reports its download progress and errors. Re-check preparation afterwards. If native nodes are missing, update ComfyUI with its normal updater and restart it when idle. No extra custom node pack is needed. The engine becomes selectable only when its live capability probe succeeds and it is enabled in Dataset Forge settings.

The [Qwen Research licence](https://huggingface.co/Qwen/Qwen-Image-2.1/blob/main/LICENSE) applies to the model weights and limits them to non-commercial use. Running locally does not change that licence.

### Qwen generation settings

The recommended recipe is **25 sampling steps**, **CFG 3**, **res_multistep / simple**. Sampling steps accept 1–100; CFG accepts 0–30. More steps cost more GPU time. Guidance changes how strongly the text conditions the image. The sampler can also use euler or dpmpp_2m; the scheduler can use normal or karras. Those alternatives change the denoising trajectory. **Restore recommended sampling** resets those four values; press Save to apply your changes.

**Reference resolution** defaults to 1024 and accepts 256–2048 in multiples of 32. It controls reference encoding and memory use, not the output size. **Output size (MP)** stays in Generate variations and is shared by local engines; each shot keeps its selected aspect ratio. Start with a small set to check likeness before a long run.

The primary reference and additional dataset reference views guide the same subject, up to ten photos total. Add a useful side or profile view when the main photo hides those features. **Negative prompt** is optional text describing unwanted traits. Dataset prompt suffixes and the selected shot still supply the positive direction.

**Model filenames** may stay empty for automatic selection. To choose an installed official INT8 or BF16 build, enter its original filename for the diffusion model, Qwen3-VL text encoder or VAE; an optional subfolder is accepted. Renamed files and custom builds are not supported. A filename does not download a model; use Preparation for the default files. Save, then re-check preparation after changing a filename.

Inspired by [Jolanoff’s Qwen dataset workflow](https://www.reddit.com/r/comfyui/comments/1wnlgko/qwen_21_dataset_generator/), based on acekiube’s face dataset workflow. LDS uses its own shot selection, reference management and generation queue.
`,
}] }
