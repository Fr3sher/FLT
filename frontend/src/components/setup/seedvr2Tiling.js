/* The OPTIONAL high-resolution lane for SeedVR2, and how the UI talks about it.

   Contributed by SurpassHR (GitHub #32): upscaling a whole frame at once runs
   out of VRAM past a certain size — he hit a real CUDA OOM on an 11.6 GB card —
   and cutting the frame into overlapping tiles, upscaling each and blending
   them back gets past it on the same hardware.

   Two things this module exists to keep honest:

   * The lane is OPTIONAL and its absence is not a fault. Without the tiling node
     pack the ordinary lane still upscales; it is only capped. So the wording
     must never read like something is broken.
   * The cap must be said BEFORE a run, not discovered in a traceback. When the
     card's ceiling is unknown we say nothing at all rather than invent a number.

   Pure — `node --test` cannot parse JSX and this is the part with the cases. */

export const TTP_PACK = 'Comfyui_TTP_Toolset'
export const TTP_URL = 'https://github.com/TTPlanetPig/Comfyui_TTP_Toolset'

/** `{state, text}` for the tiling row on the Setup card.
    state: 'ready' | 'restart' | 'absent' | 'unknown'. */
export function tilingStatus(caps) {
  const c = (caps && caps.comfyui) || {}
  if (!c.reachable) {
    // The probe fails CLOSED for this lane, so an unreachable ComfyUI is
    // genuinely "we cannot tell" — not "you are missing something".
    return { state: 'unknown',
      text: 'Start ComfyUI and this page will tell you whether the tiling pack is there.' }
  }
  if (c.seedvr2_tiling_ready) {
    return { state: 'ready',
      text: 'Ready — large upscales are cut into tiles automatically, so they no longer '
        + 'have to fit on the card in one piece.' }
  }
  const missing = Array.isArray(c.seedvr2_tiling_nodes_missing)
    ? c.seedvr2_tiling_nodes_missing : []
  if (missing.length && missing.length < 2) {
    // Half the classes present = an old build of the pack, not an absent one.
    return { state: 'restart',
      text: `The ${TTP_PACK} pack is there but does not expose ${missing.join(', ')} — `
        + 'update it in ComfyUI-Manager and restart ComfyUI.' }
  }
  return { state: 'absent',
    text: `Optional. Without it, upscales still run — they are just limited to what this `
      + `GPU can hold in one pass. Install ${TTP_PACK} in ComfyUI-Manager and restart `
      + 'ComfyUI to lift that limit.' }
}

/** The sentence naming this machine's full-frame ceiling, or null when the card
    is unknown. Never invents a number: an unseen GPU gets silence. */
export function ceilingLine(caps) {
  const mp = ((caps && caps.comfyui) || {}).seedvr2_ceiling_mp
  if (typeof mp !== 'number' || !(mp > 0)) return null
  const ready = ((caps && caps.comfyui) || {}).seedvr2_tiling_ready
  return ready
    ? `This GPU is good for roughly ${mp} MP in a single pass; anything larger is tiled.`
    : `This GPU is good for roughly ${mp} MP in a single pass. Past that an upscale may `
      + 'run out of memory — that is what the tiling pack below is for.'
}
