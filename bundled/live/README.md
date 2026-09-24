# Live channels

An experimental local H3 channel: write scenes, choose a LoRA, render clips continuously and watch them in the browser or VLC. Playback adapts to the measured generation rate.

Live owns its studio, setup, API and ephemeral stream files. No other LDS plugin is required. H3 files and the stream encoder are prepared from the plugin settings; existing compatible files are reused. Stop the channel before disabling Live or restarting ComfyUI.

Requires LDS plugin API 1.16 or newer and a compatible local ComfyUI installation. The source package uses the shared H3 and queue interfaces supplied by LDS. Model and node licences remain their authors’ licences.

This source projection needs the corresponding public LDS SDK and host registration before it can run; the test fixtures do not prove a GPU render.
