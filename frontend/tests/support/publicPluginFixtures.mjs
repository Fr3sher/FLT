import { resetRegistry, setEnabled } from '../../src/plugins/registry.js'
import { registerBundledDescriptor } from './bundledDescriptors.mjs'
import { readFileSync, readdirSync } from 'node:fs'
import { createHash } from 'node:crypto'
import apiEngines from '../../../bundled/api_engines/frontend/index.js'
import cameraAngles from '../../../bundled/camera_angles/frontend/index.js'
import canvas from '../../../bundled/canvas/frontend/index.js'
import civitaiPublish from '../../../bundled/civitai_publish/frontend/index.js'
import cloudTraining from '../../../bundled/cloud_training/frontend/index.js'
import hfPublish from '../../../bundled/hf_publish/frontend/index.js'
import imageUpscale from '../../../bundled/image_upscale/frontend/index.js'
import live from '../../../bundled/live/frontend/index.js'
import modelTools from '../../../bundled/model_tools/frontend/index.js'
import resourceMonitor from '../../../bundled/resource_monitor/frontend/index.js'
import scrape from '../../../bundled/scrape/frontend/index.js'
import seedvr2 from '../../../bundled/seedvr2/frontend/index.js'
import video from '../../../bundled/video/frontend/index.js'

export const PUBLIC_DESCRIPTORS = [apiEngines, cameraAngles, canvas, civitaiPublish,
  cloudTraining, hfPublish, imageUpscale, live, modelTools, resourceMonitor, scrape, seedvr2, video]
export const PUBLIC_PLUGIN_IDS = PUBLIC_DESCRIPTORS.map(descriptor => descriptor.id)

export function mountPublicPlugins(enabled = PUBLIC_PLUGIN_IDS) {
  resetRegistry()
  for (const descriptor of PUBLIC_DESCRIPTORS) {
    if (!registerBundledDescriptor(descriptor)) throw new Error(`Invalid public descriptor: ${descriptor.id}`)
  }
  setEnabled(enabled)
}

const REPO = new URL('../../../', import.meta.url)
export const imageDigest = url => createHash('sha256').update(readFileSync(url)).digest('hex')
export function publicNewsImage(entry) {
  const url = new URL(entry.image, REPO)
  const anchor = entry.plugin
    ? new URL(`bundled/${entry.plugin}/frontend/assets/news/`, REPO)
    : new URL('docs/screenshots/', REPO)
  if (!url.href.startsWith(anchor.href)) throw new Error(`Screenshot leaves its public owner: ${entry.id}`)
  return url
}

export function curatedImageDigests() {
  const root = new URL('docs/screenshots/', REPO)
  return new Set(readdirSync(root, { recursive: true }).filter(name => /\.(png|jpe?g|gif|webp)$/i.test(name))
    .map(name => imageDigest(new URL(name.replaceAll('\\', '/'), root))))
}
