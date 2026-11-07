// Historical IDs and dates are preserved when ownership moves out of the core feed.
export const MIGRATED_NEWS = [
  {
    id: '2026-09-09-model-tools-managed-cpu-engine',
    date: '2026-09-09',
    title: 'Install the Model tools CPU engine from its own settings',
    blurb: 'Quantization and LoRA merging share a managed Python and PyTorch environment owned by Model tools. Install or repair it from the plugin page, check CPU readiness, and keep an existing Python override if you need one. The LDS core environment stays unchanged.',
  },
{
    id: '2026-09-09-model-tools-local-without-cloud',
    date: '2026-09-09',
    title: 'Local quantization works with Model tools alone',
    blurb: 'The local model form uses its own CPU conversion service when Cloud training is not installed. It checks the source and available Python environment before any write, and saves the fp8 file beside the original. Cloud delivery remains available when its plugin is active.',
  },
{
    id: '2026-08-04-quantizing-no-longer-fails-on-the-paging-file',
    date: '2026-08-04',
    title: 'Quantizing a big model no longer dies on a “paging file” error',
    blurb:
      'If you tried to turn a full-precision model into its fp8 file and got “the paging file is too small to complete this operation”, nothing was wrong with your disk, your memory or your model — and adding disk space would not have helped. Opening the checkpoint reserved its entire size, 26 GB of it, before reading a single number. The app now reads big checkpoints one tensor at a time instead, so the size of the file no longer has anything to do with whether it opens: a 25.6 GB model that could not be opened at all now quantizes in about a minute, and the read-back check at the end works the same way, so it can no longer fail on the last step after twenty minutes of work.',
  },
{
    id: '2026-08-04-merge-a-lora-into-a-base-checkpoint',
    date: '2026-08-04',
    title: 'Turn your LoRA into a full model you can publish',
    blurb:
      'Most of the checkpoints you download were not trained — they were merged: a LoRA folded into somebody’s base, quantized, uploaded. LDS could train the LoRA and could quantize the result, and could not do the step in between, so you could not reproduce what everyone else was doing. Now you can: pick a base, add one or more LoRAs with a weight each, and get a complete checkpoint. It also unlocks the speed problem — a full model trained here targets Raw, which is slow, and merging in the re-distillation LoRA Krea publishes for Turbo is the published route to getting few-step generation back (we have not tested that one ourselves, and the screen says so). Nothing starts on one click: the plan tells you how many tensors change, exactly how big the output is, which drive it lands on and how long it takes — about two minutes on a 26 GB base — and nothing is ever overwritten. And it calls the result what it is. A merged model is not a trained model, however often the model sites say “finetune” for it, so the file records the base, every LoRA and its weight, and the date, in its own metadata — which is what still identifies it in six months, after the name has changed.',
  },
{
    id: '2026-08-04-fp8-quantize-runs-where-torch-lives',
    date: '2026-08-04',
    title: 'Quantizing to fp8 now actually runs — it uses an environment that has torch, and says so before you click if none does',
    blurb:
      'On a real install the conversion could not run at all: it ended on “No module named ‘safetensors’”, because it tried to do the work inside the app’s own Python — which ships without torch on purpose, since torch is gigabytes and nothing else here needs it. It now runs the conversion in a separate interpreter that has the dependencies, exactly like ✨ Score and the masking passes already do: the one ✨ Score uses, ai-toolkit’s, or whichever you set as `quantize.python`. And because “can this machine do it at all” is something you should learn before committing, it is checked while the plan is drawn: an environment without torch disables the button and tells you which environments would work and what to install, instead of failing thirty seconds in — or, worse, after a 26 GB download.',
  },
{
    id: '2026-08-04-quantize-to-fp8-in-one-click',
    date: '2026-08-04',
    title: 'One click turns your full model into the fp8 file ComfyUI loads — nothing to type, and it works on a model that is only on Hugging Face',
    blurb:
      'The fp8 quantizer asked for an absolute path to a file on this machine, and the model most people want to shrink has no such path: a full-model run delivers its 26 GB master into your private Hugging Face repository and never downloads it. So the one full model you own was the one thing the tool could not touch. Now “✨ Quantize to fp8” sits right there in the full-model recipe, already aimed at the model your run delivered, and does the whole chain: fetches the master, converts it, and leaves the fp8 file in ComfyUI’s own models folder, ready to load. Before it starts it tells you which checkpoint it takes (a repository often holds the final save AND several 26 GB step snapshots whose names differ by a number — one rule now decides, and it is the same one that names the file on the card), which folder the file lands in, and what it costs in disk. The download reports its gigabytes, can be stopped, and resumes where it left off. Afterwards the master is kept by default, because it is the only copy you can train from again; deleting it is one radio button away with its size on it. The path field is still there for a file nothing in the app points at — and it now pre-fills itself with your custom training base.',
  },
{
    id: '2026-08-04-quantize-to-fp8-from-settings-storage',
    date: '2026-08-04',
    title: 'Shrink a model to fp8 from Settings ▸ Storage — no dataset, no training run',
    blurb:
      'The fp8 quantizer that shipped yesterday had exactly one door: the full-model recipe card, which only exists inside a dense dataset. So the person it was written for — someone who downloaded a 26 GB full-precision model from Hugging Face and cannot load it — had no dataset, and never found it. It is now also in Settings ▸ Storage, beside the folder sizes and the trash, because “this file is too big” is a disk question. It is the same tool, not a second copy: point it at any full-precision .safetensors on this machine and it writes the ~10 GB version ComfyUI loads directly, next to the original. Same refusals before you click (a file that is already quantized, a LoRA/adapter), same promise that your source file is never modified and never overwritten, same read-back of the result before it reports success. It runs on the CPU, one at a time, so it never takes VRAM from ComfyUI or a training run. One correction landed on the same tab: the Hugging Face storage card counts the fp8 export in what a full-model run needs, but did not name it, so a ~60 GB forecast explained itself as 46 GB — the breakdown now lists every term it adds up.',
  },
{
    id: '2026-08-03-quantize-an-existing-model-to-fp8',
    date: '2026-08-03',
    title: 'Turn any full-precision model you already have into its ~10 GB ComfyUI version',
    blurb:
      'The same conversion the cloud runs at the end of a full-model training is now available by hand, on this machine: give it the path to any full-precision .safetensors — a 26 GB model downloaded from Hugging Face, a checkpoint from an earlier run — and it writes the fp8 version next to it. The source file is never modified and an existing output is never silently overwritten. It runs on the CPU, so nothing competes with ComfyUI or a training run, and when it finishes it re-opens the file it wrote to check the scales and dtypes are what ComfyUI expects. It refuses a file that is already quantized, and it refuses a LoRA — neither has anything to gain. Worth saying plainly, because it is constantly confused: this is NOT the “quantize” option in Advanced training, which only shrinks the model in memory while it trains and writes no file at all.',
  },
]
