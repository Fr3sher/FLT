import { VIDEO_INSTALL_LABELS } from './videoInstallLabels.js'
export { VIDEO_INSTALL_LABELS as INSTALL_ALL_ACTION_LABELS } from './videoInstallLabels.js'

export const VIDEO_STUDIO_INSTALL_ORDER = ["h3_base", "h3_text_encoder", "h3_video_vae", "h3_audio_vae", "h3_turbo_lora", "h3_parasyte_lora", "h3_dareties_lora"]
export function videoStudioInstallPlan(caps) {
  const cu = caps?.comfyui || {}
  if (!cu.dir_valid) return []
  const missing = (Array.isArray(cu.video_studio_missing) ? cu.video_studio_missing : [])
    .map(m => m?.action).filter(Boolean)
  return VIDEO_STUDIO_INSTALL_ORDER.filter(action => missing.includes(action))
}

export function videoSetupRows(caps) {
  const c = caps || {}, cu = c.comfyui || {}
  const weightsThere = !(Array.isArray(cu.video_studio_missing) && cu.video_studio_missing.length)
  const waiting = cu.dir_valid && !cu.reachable && weightsThere
    ? { pending: true, note: 'launch ComfyUI to enable', waitingTopic: 'comfyui.api_url' } : {}
  const smoothReady = !!cu.video_studio_ready && cu.video_studio_options?.vfi?.available === true
  return [
    { label: 'Video Test Studio', what: 'Local H3 image- and text-to-video', ok: !!cu.video_studio_ready, topic: 'setup-video-studio', ...(!cu.video_studio_ready ? waiting : {}) },
    { label: 'Video tools in LDS', ok: !!c.video_host_ready, topic: 'setup-quality' },
    { label: 'Video reading', ok: !!c.video_decode, topic: 'setup-quality' },
    { label: 'Shot detection', ok: !!c.video_detect, topic: 'setup-quality' },
    { label: 'Clip encoding', ok: !!c.video_encode, topic: 'setup-quality' },
    { label: 'Smooth (frame interpolation)', ok: smoothReady, topic: 'setup-video-studio', ...(!smoothReady ? waiting : {}) },
    { label: 'DLSS 5 neural rendering', ok: !!c.dlss5nr?.ready, topic: 'setup-dlss5-install' },
  ]
}
export function videoInstallCatalog(caps) {
  const c = caps || {}, cu = c.comfyui || {}
  const missing = videoStudioInstallPlan(c)
  return [
    ...[['video', c.video_decode && c.video_encode], ['video_host', c.video_host_ready], ['shot_detect', c.video_detect], ['video_text', c.video_text]]
      .map(([action, present]) => ({ action, label: VIDEO_INSTALL_LABELS[action] || action, present: !!present, available: true, hint: '' })),
    ...VIDEO_STUDIO_INSTALL_ORDER.map(action => ({ action, label: VIDEO_INSTALL_LABELS[action],
      present: !!cu.dir_valid && !missing.includes(action), available: !!cu.dir_valid,
      hint: cu.dir_valid ? '' : 'Choose a valid ComfyUI folder first.' })),
  ]
}
export const VIDEO_ML_CARDS = [
  { before: 'video_text', action: 'video', cap: ['video_decode', 'video_encode'], icon: '🎬', title: 'Video decoding', body: 'Prepare video reading and clip encoding.' },
  { before: 'video_text', action: 'video_host', cap: 'video_host_ready', icon: '🎬', title: 'Video tools in LDS', body: 'Prepare the tools used inside LDS for reading and analysis.' },
  { before: 'video_text', action: 'shot_detect', cap: 'video_detect', icon: '🎞️', title: 'Shot detection', body: 'Prepare TransNetV2 in the managed worker environment. Whole-file triage works without this optional analysis.' },
]
