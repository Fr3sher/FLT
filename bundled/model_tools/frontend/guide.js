// Help belongs to this product version and follows its local/optional-cloud contracts.
export const GUIDE = {
  "chapters": [],
  "sections": [
    {
      "chapter": "settings-reference",
      "anchor": "model-tools-configuration-keys",
      "markdown": "## Model tools configuration keys\n\nOpen **Plugins ▸ Model tools ▸ Settings** and click **Install CPU engine**. The installer creates a Python environment owned by Model tools and installs CPU PyTorch there. Quantization and merging use the same engine; the LDS application environment and other plugins are unchanged.\n\nWait for installation to finish. **Check again** imports PyTorch and performs a small CPU calculation in that environment. The engine is ready only when this check succeeds. Return to the page to follow an installation already in progress. **Repair CPU engine** repairs its managed dependencies.\n\nThe optional **Advanced Python override** selects an existing Python that can run PyTorch. Save changes before checking or starting work. The override is exclusive: LDS does not silently switch interpreters if it fails. Clear and save it to return to the managed engine. Installation never modifies an override environment.\n\n| Key | Meaning |\n|---|---|\n| `quantize.python` | Optional existing Python override shared by quantization and LoRA merging. Blank selects the managed Model tools CPU engine. |\n"
    },
    {
      "chapter": "settings-reference",
      "anchor": "quantize-a-delivered-checkpoint",
      "markdown": "## Quantize a delivered checkpoint\n\n**This workflow also uses the optional Cloud training plugin.** Model tools provides the CPU conversion; Cloud training owns fetching the checkpoint and placing the result for ComfyUI. Without Cloud training, download the model by your normal method and use a local file in Model tools settings.\n\nOn a delivered full-model card, click **Quantize to fp8** to review the selected checkpoint, download size, destination, output size and required disk space. A final save is preferred over step snapshots; otherwise the highest step is selected. Confirm the plan to start.\n\nCloud delivery shows download and conversion progress and offers **Stop**. Downloaded bytes can be resumed. The master stays by default; deletion is an explicit choice after successful conversion and verification. The result states its actual ComfyUI folder or fallback destination.\n"
    },
    {
      "chapter": "using-the-app",
      "anchor": "merge-a-lora-into-a-base-checkpoint",
      "markdown": "## Merge a LoRA into a base checkpoint\n\nOpen **Checkpoints & LoRAs**, then **Merge a LoRA into a base checkpoint**. Choose a full-precision base and one or more compatible LoRAs. A weight of `1.0` applies a LoRA as trained; negative weights subtract it. A weight of zero is refused because it contributes nothing.\n\nReview the plan before starting: it checks tensor keys and shapes, file readability, available space and the shared Model tools CPU engine. Already quantized bases, incompatible LoRAs and duplicate entries are refused. Merge into a full-precision model first, then quantize the result if needed.\n\nThe output uses a new name beside the base by default. It is written through a temporary file and verified before completion. The source and LoRAs remain unchanged. Progress can be followed after returning to the page, and **Stop** requests cancellation.\n\nOutput metadata records the base and LoRAs used: this is a merged model, not a model trained as a whole. Check the generated model in its intended image workflow before publishing it.\n\nOpen **Plugins ▸ Model tools ▸ Settings** and click **Install CPU engine**. The installer creates a Python environment owned by Model tools and installs CPU PyTorch there. Quantization and merging use the same engine; the LDS application environment and other plugins are unchanged.\n\nWait for installation to finish. **Check again** imports PyTorch and performs a small CPU calculation in that environment. The engine is ready only when this check succeeds. Return to the page to follow an installation already in progress. **Repair CPU engine** repairs its managed dependencies.\n\nThe optional **Advanced Python override** selects an existing Python that can run PyTorch. Save changes before checking or starting work. The override is exclusive: LDS does not silently switch interpreters if it fails. Clear and save it to return to the managed engine. Installation never modifies an override environment.\n"
    },
    {
      "chapter": "settings-reference",
      "anchor": "quantize-an-existing-model-to-fp8",
      "markdown": "## Quantize an existing model to fp8\n\nOpen **Plugins ▸ Model tools ▸ Settings** and click **Install CPU engine**. The installer creates a Python environment owned by Model tools and installs CPU PyTorch there. Quantization and merging use the same engine; the LDS application environment and other plugins are unchanged.\n\nWait for installation to finish. **Check again** imports PyTorch and performs a small CPU calculation in that environment. The engine is ready only when this check succeeds. Return to the page to follow an installation already in progress. **Repair CPU engine** repairs its managed dependencies.\n\nThe optional **Advanced Python override** selects an existing Python that can run PyTorch. Save changes before checking or starting work. The override is exclusive: LDS does not silently switch interpreters if it fails. Clear and save it to return to the managed engine. Installation never modifies an override environment.\n\nUse **Plugins ▸ Model tools ▸ Settings** without creating a dataset. Choose the full path to a full-precision `.safetensors` file on this computer, then click **Quantize to fp8** to review the plan. Conversion starts only after confirming that plan.\n\nWith Model tools alone, `<name>_fp8.safetensors` is written beside the original. The plan and result show the actual destination. The original stays unchanged, and an existing output is refused unless an overwrite was explicitly requested.\n\nThe plan checks the file header, large weight matrices, available disk space and CPU engine. It refuses a LoRA or adapter, an already quantized file and insufficient space. The disk budget is the estimated output plus 2 GB of working headroom. Conversion streams one tensor at a time and reopens the result to verify it.\n\nfp8 is an inference export: keep the full-precision source for later training, merging or re-quantization. This differs from a training memory option, which changes how a model is loaded and produces no converted file.\n\n**Cloud training is optional.** When it is active, the same tool can use its delivery service and ComfyUI destination handling. Always read the displayed plan. A remote repository requires Cloud training; local files work with Model tools alone.\n"
    },
    {
      "chapter": "dataset-guide",
      "anchor": "quantizing-a-model-you-already-have",
      "markdown": "## Quantizing a model you already have\n\nUse **Plugins ▸ Model tools ▸ Settings** without creating a dataset. Choose the full path to a full-precision `.safetensors` file on this computer, then click **Quantize to fp8** to review the plan. Conversion starts only after confirming that plan.\n\nWith Model tools alone, `<name>_fp8.safetensors` is written beside the original. The plan and result show the actual destination. The original stays unchanged, and an existing output is refused unless an overwrite was explicitly requested.\n\nThe plan checks the file header, large weight matrices, available disk space and CPU engine. It refuses a LoRA or adapter, an already quantized file and insufficient space. The disk budget is the estimated output plus 2 GB of working headroom. Conversion streams one tensor at a time and reopens the result to verify it.\n\nfp8 is an inference export: keep the full-precision source for later training, merging or re-quantization. This differs from a training memory option, which changes how a model is loaded and produces no converted file.\n\n**Cloud training is optional.** When it is active, the same tool can use its delivery service and ComfyUI destination handling. Always read the displayed plan. A remote repository requires Cloud training; local files work with Model tools alone.\n"
    },
    {
      "chapter": "dataset-guide",
      "anchor": "quantize-to-fp8-one-click-no-path-to-find",
      "markdown": "## ✨ Quantize to fp8 — one click, no path to find\n\n**This workflow also uses the optional Cloud training plugin.** Model tools provides the CPU conversion; Cloud training owns fetching the checkpoint and placing the result for ComfyUI. Without Cloud training, download the model by your normal method and use a local file in Model tools settings.\n\nOn a delivered full-model card, click **Quantize to fp8** to review the selected checkpoint, download size, destination, output size and required disk space. A final save is preferred over step snapshots; otherwise the highest step is selected. Confirm the plan to start.\n\nCloud delivery shows download and conversion progress and offers **Stop**. Downloaded bytes can be resumed. The master stays by default; deletion is an explicit choice after successful conversion and verification. The result states its actual ComfyUI folder or fallback destination.\n"
    }
  ]
}

const HELP_SECTIONS = {
  "storage.fp8_quantize": [
    "settings-reference",
    "quantize-an-existing-model-to-fp8"
  ],
  "training.fp8_quantize_local": [
    "dataset-guide",
    "quantizing-a-model-you-already-have"
  ]
}
export function guideHelp(topic) {
  if (topic.app?.route?.startsWith('/settings/') || topic.app?.route?.startsWith('/setup')) {
    const { route, ...app } = topic.app
    topic = { ...topic, app: { ...app, route: '/plugins/model_tools/settings',
      ...(route.startsWith('/settings/') ? { legacyRoute: route } : {}) } }
  }
  const target = HELP_SECTIONS[topic.id]
  return { ...topic, ...(target ? { guide: { chapter: target[0], anchor: target[1] } } : {}) }
}
