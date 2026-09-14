## LoRA Dataset Studio V2

**V2 is now the main LDS release.** Existing V1 installations can upgrade from **Settings → Maintenance → Update & restart**. Your datasets, media and history stay in place. Optional features are now plugins: open **Plugins → Store** after updating, install the ones you use and review their settings before the first run.

### Install the core, then choose your plugins

Download **`LoRA-Dataset-Studio-windows.zip`** below, extract it into a new folder and double-click **`start.bat`**. The launcher prepares a compatible Python environment. Complete the core Setup, then open **Plugins → Store** to install the features you want. Each plugin has its own settings and preparation steps, including required ComfyUI custom nodes. Importing and organising datasets does not require a plugin.

**13 free public plugins are available:** API image engines, Camera angles, Canvas, Publish to Civitai, Cloud training, Publish to Hugging Face, Klein Improve, Live channels, Model tools, Resource monitor, Web scraping, SeedVR2 and Video lane. Paid API engines and rented GPUs still charge separately when you choose to use them.

The core and these public plugins are available at no charge, with their source published under the project's PolyForm Noncommercial license. Additional optional paid plugins may be offered later.

### Two ways to install and update

**ZIP installations:** **Update & restart** installs the next published release, preserving your data and local configuration. The ZIP below contains the core; plugins are installed and updated separately through the Store.

**Git installations:** the default `main` branch now carries V2. **Update & restart** follows the commits of your checkout's configured branch. A checkout on another branch stays on that branch.

```text
git clone https://github.com/perfectgf/lora-dataset-studio.git
cd lora-dataset-studio
start.bat
```
