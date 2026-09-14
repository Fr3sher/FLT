## LoRA Dataset Studio V2 — Preview

This is an **opt-in preview on the `v2` branch**. The stable V1 release remains available. Updating an existing V1 installation does **not** switch it to V2.

### Install the core, then choose your plugins

Download **`LoRA-Dataset-Studio-windows.zip`** below, extract it into a new folder and double-click **`start.bat`**. The launcher prepares a compatible Python environment. Complete the core Setup, then open **Plugins → Store** to install the features you want. Each plugin has its own settings and preparation steps, including required ComfyUI custom nodes. Importing and organising datasets does not require a plugin.

**13 free public plugins are available:** API image engines, Camera angles, Canvas, Publish to Civitai, Cloud training, Publish to Hugging Face, Klein Improve, Live channels, Model tools, Resource monitor, Web scraping, SeedVR2 and Video lane. Paid API engines and rented GPUs still charge separately when you choose to use them.

The core and these public plugins are available at no charge, with their source published under the project's PolyForm Noncommercial license. Additional optional paid plugins may be offered later.

### Updates during the preview

**ZIP installations:** download later V2 preview releases manually. The in-app ZIP updater follows stable releases; a V2 preview update channel is not implemented yet. Keep your existing data safe and follow the instructions for the release you install.

**Git installations:** explicitly clone `v2`. Once on that branch, **Update & restart** follows its commits.

```text
git clone --branch v2 https://github.com/perfectgf/lora-dataset-studio.git lora-dataset-studio-v2
cd lora-dataset-studio-v2
start.bat
```
