const e=`# Getting started\r
\r
FLT - Fresh LoRa Trainer turns one reference photo into a trained, ranked LoRA —\r
curation, captioning, face-scoring and training behind a single browser tab, on\r
your own machine. The useful part of LoRA training isn't the training; it's\r
building a clean, balanced, well-captioned image set. This app puts that whole\r
pipeline behind one UI.\r
\r
> **In a hurry?** Launch the app, let the **Setup** wizard scan your machine,\r
> and create your first dataset from your own photos — no API key, no GPU, no\r
> external tool required for that first step.\r
\r
---\r
\r
## Two ways to run it\r
\r
| | API-only | Full local |\r
|---|---|---|\r
| **What works** | Create datasets, generate via Gemini/ChatGPT, curate, caption via API, export ZIP | Everything — plus local (Klein) generation, JoyCaption, face scoring, masks, training, Test Studio |\r
| **Needs** | Python 3.11–3.12, an API key | ComfyUI and/or ai-toolkit + an NVIDIA GPU (12 GB+ for local generation) |\r
| **Good for** | Laptops, first try, cloud training | The full pipeline on a training rig |\r
\r
You can start API-only and add the local tools later — features light up\r
automatically when their tool is detected.\r
\r
## First launch\r
\r
**Windows (one command):** download \`LoRA-Dataset-Studio-windows.zip\` from the\r
[latest release](https://github.com/Fr3sher/FLT/releases/latest),\r
extract it, then double-click \`start.bat\`. Releases contain an archive/source, not\r
a prebuilt executable launcher. \`start.bat\` finds or downloads a compatible Python\r
(3.11–3.12), creates \`.venv\`, installs the requirements, and opens the app at\r
\`http://127.0.0.1:5050/\`.\r
\r
**Any OS (manual venv):**\r
\r
\`\`\`\r
python -m venv .venv\r
source .venv/bin/activate        # Windows: .venv\\Scripts\\activate\r
pip install -r backend/requirements.txt\r
python backend/run.py\r
\`\`\`\r
\r
**Pinokio (one click, any OS):** in [Pinokio](https://pinokio.computer), use\r
**Discover → Download from URL** with\r
\`https://github.com/Fr3sher/FLT.git\`, then **Install** and\r
**Start**. Pinokio creates the environment (\`env/\`), installs the core\r
requirements and opens Studio on the port it really bound. Two things to know:\r
the optional tools are still connected from **Setup**, and updates go through\r
Pinokio's **Update** tab — it runs the same \`git pull --ff-only\` as the in-app\r
updater. You do not have to remember that last part: the app recognises a\r
Pinokio launch and its Updates card shows *Stop → Update → Start* (with how many\r
commits behind you are) instead of the **Update & restart** button, which would\r
relaunch the server in a window Pinokio no longer tracks.\r
\r
**Docker (API-only):** \`cp .env.example .env\`, then \`docker compose up --build\`.\r
\r
**Docker (GPU, with ComfyUI inside):** \`cp .env.example .env\`, then\r
\`mkdir -p run basedir data-docker-gpu bank-images\` — create those yourself, or Docker creates\r
them as \`root\` and the app cannot write to them — then\r
\`docker compose -f docker-compose.gpu.yml up --build\`. Needs an NVIDIA GPU and the\r
NVIDIA Container Toolkit; this is the only Docker option that can do Klein/Z-Image\r
generation and the Test Studio.\r
\r
The CUDA 12.x compatibility minimum is driver **525.60.13 on Linux** or **528.33\r
on Windows/WSL**; for the default CUDA 12.9 image, use at least **575.51.03 on\r
Linux** or **576.02 on Windows**. The optional CUDA 13 image needs **R580+**.\r
If you reuse an existing ComfyUI tree, \`LDS_COMFY_BASEDIR\` must name the parent\r
that directly contains \`models/\`, \`input/\`, \`output/\` and \`custom_nodes/\`, not\r
the \`models/\` folder itself. Compose actively defaults DNS to \`1.1.1.1\`; set\r
\`LDS_DNS\` to your router or Pi-hole when internal hostnames matter.\r
\r
Both ports are published on the host and remain reachable from the LAN. A\r
Settings restart is handled by the container supervisor and keeps the fixed\r
container bind. To update this Docker flavour, update and rebuild the image rather\r
than trying to replace \`/app\` in place:\r
\r
\`\`\`\r
git pull\r
docker compose -f docker-compose.gpu.yml up -d --build\r
\`\`\`\r
\r
If \`/data\` or existing contents beneath it are not writable, \`LDS_FORCE_CHOWN=true\`\r
is the last resort: it recursively changes ownership only for the \`LDS_DATA\` mount,\r
never the ComfyUI or bank mounts.\r
\r
See [Installation](installation.md) for all launchers, updates and external tools,\r
and [Requirements](requirements.md) for hardware and dependencies.\r
\r
## What is running on your machine {#architecture}\r
\r
A full-local install is **three separate programs**, in **two folders**, on\r
**two ports**, with **two Python environments**. Nothing in the app used to say\r
so, and the cost of guessing is real: a user spent hours patching ai-toolkit's\r
own web UI — a component this app never talks to — while the actual problem was\r
one line of \`config.json\` (reported by strouder, GitHub #19).\r
\r
| Component | Where | What it does | Port |\r
|---|---|---|---|\r
| **FLT - Fresh LoRa Trainer** (Flask) | the folder you extracted, **its own \`.venv\`** | The UI you are reading this in. Curation, captioning, and the thing that **starts and stops training**. | **5050** |\r
| **ai-toolkit** (\`run.py\`) | the folder you point at in Settings, **its own venv — the one with \`torch\`** | The training **engine**. It is run as a command-line process; it has no UI of its own. | — |\r
| ai-toolkit's Next.js UI (\`ui/\`) | inside the ai-toolkit folder | An **unrelated** web interface that ships with ai-toolkit. This app never launches it, never reads it, and never writes to it. | 8675 |\r
\r
Two consequences worth remembering:\r
\r
- **The Studio reads \`config.json\` and drives training.** That file belongs to\r
  this app (it sits in its data folder, and every key in it has a field in\r
  **Settings**). Editing anything inside ai-toolkit's \`ui/\` folder changes\r
  nothing here — if you ever find yourself editing \`ui/dist/…\`, you are in the\r
  wrong project.\r
- **The two Python environments are not interchangeable.** The Studio's \`.venv\`\r
  runs the web app; ai-toolkit's venv is the one that must have \`torch\` and the\r
  training dependencies. Settings ▸ Local tools ▸ **Python interpreter** is how\r
  you tell the app which interpreter is ai-toolkit's — and its **Test** button\r
  now checks that the interpreter can really \`import torch\`, not just that the\r
  file exists.\r
\r
There is no process stacking to worry about on our side: the Studio is a single\r
Flask process, and starting a second one on the same port fails loudly instead\r
of running invisibly alongside the first.\r
\r
### Supported Python versions {#python-versions}\r
\r
- **FLT - Fresh LoRa Trainer: Python 3.11 – 3.12.** \`start.bat\` finds or downloads\r
  one for you; the core needs 3.11 or newer (Pillow 13), and the optional ML\r
  extras (insightface, onnxruntime, \`numpy<2\`) publish no wheels after 3.12.\r
  An installation still on Python 3.10 stops with a message after updating:\r
  running \`start.bat\` again rebuilds \`.venv\` on 3.12 and keeps your data.\r
- **ai-toolkit: Python 3.11 is the safe choice.** On **3.13** its pinned\r
  \`scipy==1.12.0\` has no wheel, pip falls back to building from source and dies\r
  on a missing Fortran compiler (measured and reported by strouder, GitHub #19).\r
  On Windows, install **3.11.9** — it is the last 3.11 with a binary installer;\r
  later 3.11.x are source-only security releases.\r
- **Or hand that whole job to ai-toolkit.** Run \`python -m manager install\` from\r
  the ai-toolkit folder and its own installer provisions a Python it supports,\r
  reads your NVIDIA driver, installs the CUDA build of PyTorch that matches it\r
  and creates the venv next to \`run.py\` — all inside that folder, nothing\r
  system-wide. The Studio then detects that interpreter on its own. This is the\r
  step worth not improvising: a plain \`pip install torch\` on Windows installs a\r
  **CPU-only** wheel, ai-toolkit trains on the CPU without a word, and the run\r
  looks alive for hundreds of hours (see [The card never fills at all: the run\r
  is on the CPU](troubleshooting.md#the-card-never-fills-at-all-the-run-is-on-the-cpu)).\r
  Use the \`install\` subcommand rather than \`run_windows.bat\`, which finishes by\r
  starting ai-toolkit's own web UI — the one this app never talks to.\r
- The two do **not** have to match. They are separate environments on purpose.\r
\r
### If Hugging Face downloads fail {#hf-downloads}\r
\r
If a base-model download dies with something that reads like a network error,\r
check whether \`HF_HUB_ENABLE_HF_TRANSFER=1\` is set in your environment. That\r
turns on an optional fast-download accelerator which needs the \`hf_xet\` (or\r
\`hf_transfer\`) package installed **in the environment doing the downloading**;\r
without it, transfers abort with a misleading message. This app never sets that\r
variable — it comes from your shell, ai-toolkit's \`.env\`, or a ComfyUI launcher.\r
Either fix works: set \`HF_HUB_ENABLE_HF_TRANSFER=0\`, or \`pip install hf_xet\`.\r
The training failure panel now recognises this case and says so.\r
*(Reported by bobba84, GitHub #18.)*\r
\r
## The Setup wizard\r
\r
On first launch, **Open LDS** opens the dataset workspace. You can create a\r
dataset, import your images, edit captions and export it without installing a\r
plugin or downloading a model. Completing this step saves the setup state so\r
later visits return to the application.\r
\r
Choose an optional goal when you need more: captioning prepares the shared\r
vision tools; local generation prepares ComfyUI and its selected models;\r
**Plugins** opens one list for browsing and managing plugins, with **All**,\r
**Installed** and **Updates** filters. Nothing is downloaded by choosing a goal\r
or visiting a plugin page.\r
\r
To install several plugins, tick them in **Plugins**, choose **Review\r
selected**, and confirm the shared plan. All selected packages are checked before\r
any changes are staged; one LDS restart applies the whole selection.\r
\r
To update installed plugins, choose **Update all** and review the available\r
updates together. **Update all and restart** downloads and verifies the complete\r
selection, prepares one transaction and restarts LDS once. The page reloads when\r
the new server is ready. Disabled plugins stay disabled; connected private\r
catalogs keep their own signature checks. If your launcher requires a manual\r
restart, LDS shows its restart instructions after preparing the updates. Active\r
local work can postpone the restart; the prepared updates remain available to\r
apply when it finishes. A retained cloud pod does not block a restart that keeps\r
its plugin enabled.\r
\r
Each plugin's card offers **Install**, or its controls once installed: open the\r
plugin, **Settings**, turn it on or off, and update it when available. **More\r
actions** contains **Remove plugin**. Installed plugins remain listed even if\r
they are absent from the catalog or the store is offline. **Purchases** remains\r
a separate tab for your licenses.\r
\r
For preparation, open **Settings** on the plugin's card. Select the components\r
you want, then prepare that selection. The server checks the whole plan before\r
starting and displays progress and any failures. A completed\r
download means the component is prepared; **Re-check** verifies availability.\r
New custom nodes may need a ComfyUI restart before they appear.\r
\r
Shared tools remain available from **Setup**. Their installers use managed\r
environments and show the prerequisites for each component. Optional tools do\r
not prevent you from opening the dataset workspace.\r
\r
If something that worked stops working, the setup notice names it and links to\r
the relevant check. A tool that was never installed is not a regression, and a\r
stopped ComfyUI or Ollama can be started only when you need it.\r
\r
## Around the app\r
\r
- **Datasets** — the home tab and your **library**: photo tiles of every\r
  dataset, grouped by model family, with a search box and a badge for each\r
  family you've already trained. Create one and work it through the guided\r
  flow (source → curate → caption → train).\r
- **🏋️ Runs** — every training in one place, cloud *and* local: live progress,\r
  the settings each launch used, retry a failed run (↻), continue a finished\r
  one (▶), and download the LoRA (appears once ai-toolkit or a [vast.ai](https://cloud.vast.ai/?ref_id=683073) key is set).\r
- **Test Studio** — grid-test a trained LoRA across checkpoints and strengths,\r
  vote, and rank (appears once ComfyUI is reachable).\r
- **Guide** — this manual.\r
- **Setup** — the guided wizard, re-runnable anytime.\r
- **Settings** — everything the wizard configures, plus server, updates,\r
  maintenance and the diagnostic report.\r
\r
Next chapter: **Using the app** — the full walkthrough, dataset type by dataset\r
type.\r
`;export{e as default};
