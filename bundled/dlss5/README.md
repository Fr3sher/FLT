# DLSS 5 Neural Rendering

A complete LDS finishing plugin. Open **DLSS 5**, import a finished video,
render it, compare both versions and download the result. It includes its own
Python engine, settings and preparation.

Sources follow the [shared LDS plugin architecture](../../docs/plugins/README.md).
This source publication retains the PolyForm Noncommercial license in
[LICENSE](LICENSE). NVIDIA's model and the native bridge binaries are not
included in this repository.

## Preparation

In **Plugins → DLSS 5 → Settings**, install the managed Python engine
(NumPy and imageio-ffmpeg) and the pinned bridge. The host validates the bridge
release's size and SHA-256. Place your own `nvngx_dlssnr.dll` in the displayed
runtime folder. This plugin does not download NVIDIA's model.

Native rendering requires Windows x86-64, an NVIDIA display driver and a
compatible NVIDIA model. The preparation screen explains missing pieces.
The Python engine installs separately from the LDS application interpreter.

An advanced Python override is optional. The previous `video.python` setting
is preserved once on first registration; later Video changes cannot affect
DLSS. Clear the override to use the managed engine.

## Data and optional integration

- Existing `data/dlss5nr` bridge/model files are reused in place.
- Standalone imports, records and results live in DLSS's persistent plugin
  data directory. Originals are preserved and each render starts from them.
  **Open folder** below a selected video opens its directory in Windows Explorer
  on the computer running LDS, with the original and any rendered result.
- When Video is also enabled, DLSS supplies its render/compare dialogs and
  owns the historical dataset and Studio rendering routes. Video retains its
  own table adapters and `data/video_nr_backup` originals, without relocation.
- Disabling DLSS removes its actions from Video and refuses its API. Disabling
  Video leaves the standalone DLSS studio usable.

Requires LDS plugin API 1.21 or later in major version 1. Python integration
uses the versioned `lds_sdk.dlss5` and `lds_sdk.video_media` interfaces; there
are no direct imports from other plugin packages.

## Qualification

The package includes tests for standalone registration, imported media,
simulated render/cancel/recovery, original preservation, interpreter migration
and OFF admission. The existing rendering and Video dataset/Studio contracts
cover the migrated algorithms. These tests run without the NVIDIA model or
an inference job; they do not certify a GPU/driver combination.
