## FLT - Fresh LoRa Trainer

FLT tracks the maintained upstream V2 code while keeping `main` as this fork's branch. Existing FLT Git checkouts should stay on `main`; upstream's branch migration instructions apply to upstream checkouts.

### Install the core, then choose your plugins

Extract the Windows ZIP into a new folder and run `start.bat`. Complete Setup, then install the public plugins you need through Plugins → Store. External API engines and rented GPUs charge separately. Optional usage statistics are off by default. Upstream Patreon membership provides members-only plugins and early upstream builds; the installed public core keeps working without membership.

### Two ways to install and update

ZIP installations update to the next published FLT release, preserving data and local configuration. Git installations follow their configured branch with a fast-forward update. Plugins are installed and updated separately through the Store.

```text
git clone https://github.com/Fr3sher/FLT.git
cd FLT
start.bat
```
