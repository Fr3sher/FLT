export const NEWS = [
  {
    "id": "2026-09-10-seedvr2-node-discovery-retry",
    "date": "2026-09-10",
    "title": "A failed tiling check asks you to re-check",
    "blurb": "If ComfyUI is reachable but its node list cannot be read, SeedVR2 asks you to re-check instead of claiming components are missing. Tiling stays unavailable until its nodes are confirmed. Update or installation advice is reserved for components actually found to be missing.",
    "to": "/plugins/seedvr2/settings?focus=seedvr2-engine"
  },
  {
    "id": "2026-09-10-seedvr2-overlapping-tile-joins",
    "date": "2026-09-10",
    "title": "Tiled upscales blend their shared edges",
    "blurb": "Targets that previously put restored tile borders side by side now use real overlap and blend rows before joining them. Tile size stays within your memory setting; a 2048 × 2048 target with 1024 px tiles now uses nine passes instead of four. Extra overlap costs time and image-buffer memory. Source images and previous results stay unchanged.",
    "to": "/plugins/seedvr2/settings?focus=seedvr2-tiling"
  },
  {
    "id": "2026-09-10-seedvr2-complete-tiles-and-finishing",
    "date": "2026-09-10",
    "title": "Tiled upscales keep the whole image",
    "blurb": "A 2048 × 2048 upscale with 1024 px tiles now keeps all four quarters instead of returning only the first. The tile count matches the work submitted, without increasing the tile size. Sharpening and film grain also work on a fresh LDS installation, with their CPU dependency included in the app runtime. Existing source images and previous results are preserved.",
    "to": "/plugins/seedvr2/settings?focus=seedvr2-engine"
  },
  {
    "id": "2026-09-07-seedvr2-standalone",
    "date": "2026-09-07",
    "title": "SeedVR2 is its own restoration plug-in",
    "blurb": "Install faithful upscaling, tiling, preparation and independent finishing without Klein Improve. Existing SeedVR2 settings, weights and results are preserved.",
    "to": "/plugins/seedvr2/settings?focus=seedvr2-engine"
  },
  {
    "id": "2026-08-03-seedvr2-tile-and-vae-settings",
    "date": "2026-08-03",
    "title": "SeedVR2 upscaling now fits smaller cards — tile size is a setting",
    "blurb": "The fidelity upscaler used to hold one 1024 px tile at a time whatever your GPU, which is where a large upscale ran out of memory on an 8 GB card. Settings ▸ Image engines now has a Tile size: lower it to 768 or 512 and the same 4K upscale fits, at the cost of a few more seams. It also sizes the model's own tiled encode/decode, so it lowers memory use even without the optional tiling node pack. Two more dials came with it — where automatic tiling switches over, and which VAE file to load when yours is named something the automatic search cannot recognise. Defaults are unchanged, so nothing moves unless you touch it. Thanks to SurpassHR (GitHub) for asking for these knobs alongside the engine itself."
  },
  {
    "id": "2026-08-03-seedvr2-tiling-is-a-choice",
    "date": "2026-08-03",
    "title": "Tiled upscaling is now the default — it keeps more detail, not just less VRAM",
    "blurb": "Yesterday tiling only kicked in when a frame would not fit on your card. SurpassHR (GitHub #32) re-tested it and sent the source renders: side by side, the full-frame result does not just soften fine texture, it rewrites it — short dense stubble comes back as long smeared strands. A tile is upscaled at the size the model works well at, while a whole 4K frame spreads its capacity over four times the surface. That made the old rule backwards: the bigger your GPU, the less often you got the better picture. So with the tiling node pack installed, large upscales are now tiled by default, and Settings ▸ Image engines lets you choose — tile when it helps (recommended), always tile large frames, or never. Nothing is tiled below roughly 1536 px on the short edge, where the model already works at a good size and a grid would only add seams."
  },
  {
    "id": "2026-08-03-seedvr2-tiled-highres",
    "date": "2026-08-03",
    "title": "Big SeedVR2 upscales no longer have to fit on your card in one piece",
    "blurb": "Upscaling a whole frame at once needs the whole frame in VRAM, and past a certain size that simply fails — with a CUDA out-of-memory error in a log, which is a terrible way to find out. Two things change. The app now tells you, before it starts, roughly how many megapixels your GPU is good for in one pass. And if you install the Comfyui_TTP_Toolset node pack in ComfyUI, anything bigger is automatically cut into overlapping tiles, upscaled tile by tile and blended back together — so a 4K result works on a card that could not hold it whole. Without the pack nothing breaks: upscales still run, they are just capped. Tiled workflow and the measurement behind it contributed by SurpassHR (GitHub #32)."
  },
  {
    "id": "2026-08-02-seedvr2-in-the-lightbox",
    "date": "2026-08-02",
    "title": "Pick your upscaler while you are looking at the image",
    "blurb": "The full-screen inspector only ever offered the Klein pass. That is the one place where the choice matters most: on a drawn dataset the panel already warns you that Klein’s instruction pulls anime skin towards realism, and the pass that does not do that was two screens away in the selection toolbar. Both engines are now side by side in the inspector, each saying what it does to the original — and that warning stays under Klein alone, because SeedVR2 sends no instruction at all."
  },
  {
    "id": "2026-08-02-seedvr2-results-come-back",
    "date": "2026-08-02",
    "title": "SeedVR2 upscales now actually appear — and the ones you already ran are recovered",
    "blurb": "The first SeedVR2 build rendered correctly and then dropped the result on the floor: ComfyUI finished the image, the job was marked done, and the candidate stayed blank forever with nothing in the log, because nothing had failed. The finished image is now attached to its tile. Any upscale you already ran and never saw is picked up automatically the next time the app starts — the image is still there, it just never made it home. Caught on a real run the day it shipped."
  },
  {
    "id": "2026-08-02-seedvr2-upscaling",
    "date": "2026-08-02",
    "title": "A second way to upscale — one that does not repaint your images",
    "blurb": "Klein’s ✨ Upscale & improve re-renders detail from a prompt: it rescues a soft photo, and it can move skin tone and colour along the way — which is the wrong trade when the exact look is what you are training on. SeedVR2 is now the other option: it resolves detail at a higher resolution and leaves the content alone. Pick either one straight from the bulk actions on a selection (each button says what it does to the original), or set your default for the single-image pass in Settings ▸ Image engines. Setup ▸ ComfyUI downloads the two models (~3.9 GB) on a click and tells you how to add the node pack. Requested by SurpassHR (GitHub #32)."
  },
  {
    "id": "2026-08-04-seedvr2-settings-say-which-lane-your-target-takes",
    "date": "2026-08-04",
    "title": "SeedVR2 settings tell you whether your target will be tiled",
    "blurb": "Tiling starts strictly above the crossover, and the crossover is 1.5× your tile size — so it lands exactly on the round numbers people type. Ask for 1536 px with the default 1024 px tile (or 768 px with a 512 px tile) and the upscale ran whole, with nothing anywhere saying why: no tiles, no warning, no line in the panel. The SeedVR2 card now names the lane your configured target will actually take, and when it sits on the crossover it says so and gives you the three ways to change it."
  }
]
