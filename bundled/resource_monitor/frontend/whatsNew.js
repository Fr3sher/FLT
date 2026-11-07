export const WHATS_NEW = [
  {
    // Same-day ids sort the feed (date, then id): 'zzzzz' keeps this one above
    // the day's earlier entries, so the badge counts it (2026-09-06).
    id: '2026-09-06-zzzzz-comfyui-interrupt-second-press',
    date: '2026-09-06',
    title: 'Cancel stops the render, and 🧹 Free memory has a second press instead of a wall',
    blurb:
      'Cancelling a clip ComfyUI is already rendering now asks ComfyUI to stop it, '
      + 'instead of waiting for the render to end on its own — a render that pages '
      + 'can take a minute or two to notice. Free memory still refuses while a render '
      + 'of LDS’s own is on the card, but it says so and the same button pressed again '
      + 'within a minute interrupts that render (it is dropped) and frees the memory. '
      + 'A training and a job that is not LDS’s keep their protection.',
    to: '/datasets',
  },
  {
    id: '2026-09-02-free-memory-button',
    date: '2026-09-02',
    title: 'A 🧹 button beside the machine-load numbers gives the RAM back',
    blurb:
      'ComfyUI keeps every model of the day cached in RAM after it leaves the '
      + 'card (measured: 34 GB on an idle ComfyUI), and the vision model stays '
      + 'warm for captioning — neither returns it by itself. 🧹 next to the '
      + 'CPU · GPU · VRAM · RAM readout (top bar and Canvas toolbar) unloads '
      + 'both and re-reads the machine; the toast says what actually came back. '
      + 'Refused while something is rendering or training, and a model another '
      + 'tool loaded is never touched.',
    to: '/datasets',
  },
  {
    id: '2026-08-28-header-machine-load',
    date: '2026-08-28',
    title: 'A resource monitor on every page — now with GPU temperature',
    blurb:
      'The 📊 machine-load readout is no longer Canvas-only: click 📊 in the '
      + 'header and every page — the Test Studio above all — shows live '
      + 'CPU · GPU · VRAM · RAM numbers, now joined by the GPU temperature, '
      + 'so you can watch a generation or a training work without keeping '
      + 'Task Manager or a ComfyUI monitor open. It polls only while the tab '
      + 'is visible, folds away with ▾, and remembers your choice. '
      + 'Suggested by Sam Exit (Discord).',
  },
  {
    id: '2026-08-09-canvas-machine-load',
    date: '2026-08-09',
    title: 'See how hard the machine is working, without leaving the board',
    blurb:
      'The Canvas toolbar now carries a small CPU · GPU · VRAM · RAM readout of the machine running LDS, so you can tell a run that is working from one that is stuck without opening Task Manager. It turns amber past 50% and red past 80%, refreshes only while the tab is open, and folds away with ▾ if you would rather not see it. No NVIDIA card: it simply shows no GPU numbers.',
  },
]
