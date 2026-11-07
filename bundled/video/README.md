# Video lane

Create a video training set directly from **Datasets → New dataset → Video**. Choose its model, clip length and size, then add local files in **Add videos**. The optional web source panel can send selected videos to the same import endpoint. Imports report progress and skips, can be stopped, and avoid duplicating an already imported clip.

Video Bank also turns rushes into shots for review, captioning and dataset creation. Training sets include local training, checkpoint history and identity-reference support. The H3 Test Studio generates image- or text-to-video clips, compares LoRAs, continues clips manually and interpolates frames.

Preparation installs CPU video decoding and encoding tools. Direct imports accept the selected videos, with 200 MB per file and 1 GB per upload; splitting keeps every complete clip from each source. Files too short for the requested frame count are skipped. The first source can set the dataset size, fitted to the model; subsequent imports use that size. Add captions before training.

The Render performance panel supports an existing H3 Fused Turbo weight, H3 SageAttention, Spectrum, INT8 video VAE and synchronous fast H.264 saving. Optional nodes and the INT8 VAE can be prepared from the panel. Fused has acceleration built in; Sage/Spectrum exclude Sparse and VDN. Reuse restores the effective settings. Playback can recover old clips that accidentally recorded the input-video filename, using the exact successful ComfyUI job.

INT8 preparation uses the official optimized 2.81 GB H3 video VAE. Update LDS before preparing it from the Render panel: the host detects the previous experimental file and replaces it only after the new download passes its size and SHA-256 checks.
