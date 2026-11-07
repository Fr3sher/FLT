import { MIGRATED_NEWS } from './migratedNews.js'
import { GUIDE, guideHelp } from './guide.js'
// 🧰 Model tools — the frontend descriptor of the bundled `model_tools`
// plugin. Plain JS on purpose: node --test imports it (the parity, help and
// slot contracts), Vite globs it at build time (src/plugins/bundled.js). The
// React panels are lazy imports, so each is its own chunk and only loads where
// a surface mounts it.
//
// Two tools, four doors the core lends:
//   - `training.tool` (the dataset's Checkpoints & LoRAs panel) — the LoRA
//     merge disclosure: always reachable, collapsed, its open state persisted.
//   - `dense.model.tool` (each delivered full model's card) — the ✨ Quantize
//     and 🧬 Merge buttons and the tools they open, drawn from the core's
//     verdict on what THIS entry allows (`actions`).
//   - `dense.recipe.tool` (under the full-model recipe card) — the fp8 tool
//     aimed at the model this dataset's run delivered.
//   - `settings.group` on the Model tools product page — the quantize card for a model
//     downloaded by hand, with no dataset at all: the findable door.
// No `lucide-react` import here: node resolves a bare package from the
// importing file's folder, and bundled/ has no node_modules — the tests that
// load this descriptor would die on it. The panels may (they load through Vite).
export default {
  guide: GUIDE,
  id: 'model_tools',
  nav: [],
  routes: [],
  slots: {
    'training.tool': [
      { id: 'lora-merge', panel: () => import('./panels/TrainingMergeTool.jsx') },
    ],
    'dense.model.tool': [
      { id: 'model-tools', panel: () => import('./panels/DenseModelTools.jsx') },
    ],
    'dense.recipe.tool': [
      { id: 'fp8-quantize', panel: () => import('./panels/Fp8QuantizeTool.jsx') },
    ],
    'settings.group': [
      { id: 'model-tools', section: 'storage', after: 'models',
        title: 'Model tools',
        blurb: 'Quantize a full-precision model to the fp8 file ComfyUI loads — no dataset or training run needed.',
        // The words the Settings sidebar search matches the section on, in
        // addition to the core's own.
        keywords: ['quantize', 'quantise', 'fp8', 'shrink', 'smaller', 'convert', 'safetensors',
          'full model', 'checkpoint', '26 gb', '10 gb', 'merge', 'model tools'],
        panel: () => import('./panels/StorageQuantizeGroup.jsx') },
    ],
  },
  hosts: [],
  help: ([
    { id: 'training.fp8_deliver', kind: 'action',
    title: 'Quantize to fp8 in one click (and where the file lands)',
    keywords: ['quantize', 'quantise', 'fp8', 'one click', 'button', 'download',
      'hugging face', 'hf', 'repository', 'master', 'bf16', 'comfyui', 'comfy',
      'diffusion_models', 'checkpoints folder', 'full model', 'dense', 'krea',
      'disk space', 'not enough disk space', 'another folder', 'junction',
      'resume', 'cancel', 'stop', 'keep master', 'delete master',
      'torch', 'safetensors', 'no module named', 'quantize.python', 'interpreter'],
    guide: { chapter: 'dataset-guide', anchor: 'quantizing-a-model-you-already-have' },
    app: { route: '/datasets?section=training' },
    tip: { trigger: 'fp8-deliver-one-click',
      text: 'New: “✨ Quantize to fp8” on a delivered full model does the whole thing — it fetches the master from your private Hugging Face repo, converts it, and leaves the fp8 file in ComfyUI’s own models folder. It tells you which checkpoint it takes and where the file lands before it starts, refuses if the disk is too small, and can be stopped and resumed.' } },
    // The fp8 tool's SECOND door, and the findable one. Its first
    // (training.fp8_quantize_local, below) sits inside a dense dataset's recipe
    // card — which the person this helps most, someone who downloaded a 26 GB
    // full model from Hugging Face and has no dataset, never opens. Same
    // component, same refusals; only the address differs, so it gets its own
    // topic rather than stealing the other one's.
    { id: 'storage.fp8_quantize', kind: 'action',
      title: 'Quantize a model to fp8 (no dataset or training run needed)',
      keywords: ['quantize', 'quantise', 'fp8', 'shrink', 'smaller', 'convert', 'comfyui',
        'comfy', 'safetensors', 'hugging face', 'downloaded', 'disk', 'space', 'storage',
        '26 gb', '10 gb', 'checkpoint', 'full model', 'load diffusion model', 'cpu'],
      guide: { chapter: 'settings-reference', anchor: 'storage' },
      app: { route: '/settings/storage', focus: 'storage-fp8-quantize' } },
    { id: 'training.fp8_quantize_local', kind: 'action',
      title: 'Quantize a model to fp8 (the manual path field)',
      keywords: ['quantize', 'quantise', 'fp8', 'convert', 'shrink', 'comfyui', 'comfy',
        'local', 'path', 'safetensors', '26 gb', '10 gb', 'checkpoint', 'full model', 'cpu',
        'ai-toolkit quantize', 'memory'],
      guide: { chapter: 'dataset-guide', anchor: '10-full-model-recipe-what-you-can-change' },
      app: { route: '/datasets?section=training' },
      tip: { trigger: 'fp8-quantize-local',
        text: 'New: the fp8 tool no longer needs a path for the model your run delivered — it aims at it by itself. The path field is still there for a file nothing in the app points at, and it pre-fills with your custom training base.' } },
    // Its own topic, not a line under "Full models": a merge is how most published
    // checkpoints are actually made, and someone searching "turbo", "bake",
    // "finetune" or "publish a checkpoint" is asking for THIS, not for the
    // quantize button or the LoRA deploy instructions.
    { id: 'workspace-lora-merge', kind: 'action', title: 'Merge a LoRA into a base',
      keywords: ['merge', 'merge lora', 'bake', 'bake in', 'fold', 'full model from lora',
        'checkpoint from lora', 'finetune', 'turbo', 'transplant', 're-distillation',
        'distill', 'publish a checkpoint', 'civitai', 'base plus lora', 'stack loras',
        'merged model', 'speed back', 'few-step'],
      guide: { chapter: 'using-the-app', anchor: 'merge-a-lora-into-a-base-checkpoint' },
      app: { route: '/datasets?section=checkpoints' } },
  ]).map(guideHelp),
  whatsNew: MIGRATED_NEWS,
  paritySkip: [],
}
