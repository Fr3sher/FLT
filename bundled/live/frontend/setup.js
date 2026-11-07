export const labels = {
  live_encoder: 'Live — stream encoder (ffmpeg)',
  live_h3_base: 'Live — H3 model', live_h3_text_encoder: 'Live — prompt encoder',
  live_h3_video_vae: 'Live — video decoder', live_h3_audio_vae: 'Live — audio decoder',
  live_h3_turbo_lora: 'Live — Turbo LoRA (optional)',
}
export function setupRows(caps) {
  const live = caps?.live || {}
  const waiting = !live.ready && caps?.comfyui?.dir_valid && !caps.comfyui.reachable
    && Array.isArray(live.missing) && live.missing.length === 0
    ? { pending: true, note: 'launch ComfyUI to enable', waitingTopic: 'comfyui.api_url' } : {}
  return [
    { label: 'Live — stream encoder', what: 'Encodes browser and VLC playback', ok: live.encoder === true, topic: 'setup-live', ...(live.encoder === false ? { note: 'needs ffmpeg — prepare the Live stream encoder' } : {}) },
    { label: 'Live — local generation', what: 'H3 files and a reachable ComfyUI', ok: live.ready === true, topic: 'setup-live', ...waiting },
  ]
}
export function catalog(caps) {
  const live = caps?.live || {}, missing = new Set((live.missing || []).map(row => row.action))
  return Object.entries(labels).map(([action, label]) => ({
    action, label, present: action === 'live_encoder' ? live.encoder === true : !missing.has(action) && !!caps?.live,
    available: action === 'live_encoder' || caps?.comfyui?.dir_valid === true,
    hint: action === 'live_encoder' ? 'A bundled ffmpeg binary, verified after installation.' : 'Reuses the same H3 file if already installed.',
  }))
}
