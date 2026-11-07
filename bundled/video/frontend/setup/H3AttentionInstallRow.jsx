import { useEffect, useRef, useState } from 'react'
import { apiFetch, postJson } from '@lds/plugin-sdk'
import { useToast } from '@lds/plugin-sdk'

const ACTION = 'h3_attention_nodes'
const POLL_MS = 1200

/* 🔴 The MiniMax H3 block-attention switch — jacokon's FastH3 Live node,
   carried by the app (backend/comfy_nodes/lds_h3_attention) and copied into
   the user's ComfyUI at this click, exactly like the Krea preset sampler.
 *
 * WHY IT IS NOT IN THE VIDEO GROUP
 * -------------------------------
 * The video lane renders without it; this is a speed lever, not a missing
 * piece — attention is ~64 % of an H3 step and ComfyUI never switches its
 * backend by itself. Listing it with the weights would put a ✗ on an engine
 * that works. The live channel uses it when the target ComfyUI lists it, and
 * the rented pod installs it on itself; on THIS computer, this is the button.
 *
 * Three states, no download: copied / not copied / copied-but-ComfyUI-has-
 * not-restarted (nodes are registered at startup). */
export default function H3AttentionInstallRow({ caps, onDone }) {
  const toast = useToast()
  const [state, setState] = useState(null)
  const timer = useRef(null)
  const mounted = useRef(true)

  const cu = caps?.comfyui || {}
  const installed = !!cu.h3_attention_nodes_installed
  const missing = (cu.h3_attention_nodes_missing || []).length > 0

  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false; clearTimeout(timer.current) }
  }, [])

  const poll = () => {
    apiFetch(`/api/setup/install/${ACTION}/status`).then((s) => {
      if (!mounted.current) return
      setState(s)
      if (s.state === 'success' || s.state === 'error') {
        onDone?.()
        if (s.state === 'success') {
          toast.success('Attention switch installed. Restart ComfyUI to load it.')
        } else {
          toast.error((s.log || []).slice(-1)[0] || 'The attention switch could not be installed.')
        }
      } else {
        timer.current = setTimeout(poll, POLL_MS)
      }
    }).catch(() => {
      if (mounted.current) timer.current = setTimeout(poll, POLL_MS)
    })
  }

  const start = async () => {
    setState({ state: 'running' })
    try {
      setState(await postJson(`/api/setup/install/${ACTION}`, {}))
      poll()
    } catch (e) {
      setState(null)
      toast.error(e.message || 'Could not start the install.')
    }
  }

  const running = state?.state === 'running' || state?.state === 'queued'
  const justInstalled = state?.state === 'success'

  return (
    <div className="mt-4 border-t border-border pt-3" data-testid="h3-attention-install-row">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm font-semibold">Block attention switch (speed lever)</p>
          <p className="text-[0.75rem] text-content-muted">
            Runs the middle of the H3 stack on sage or int8 attention, the ends on full precision —
            the live channel&apos;s largest single speed lever on one card (after jacokon&apos;s FastH3 Live, Apache-2.0).
            Optional: the video lane renders without it.
          </p>
        </div>
        {installed && !missing && !justInstalled ? (
          <span className="text-[0.75rem] text-emerald-300">✓ installed</span>
        ) : installed || justInstalled ? (
          <span className="text-[0.75rem] text-amber-200">copied — restart ComfyUI to load it</span>
        ) : (
          <button type="button" onClick={start} disabled={running}
            className="rounded-lg bg-primary px-3 py-1.5 text-sm font-semibold text-white disabled:opacity-50 min-h-10 lg:min-h-0">
            {running ? 'Copying…' : 'Install into ComfyUI'}
          </button>
        )}
      </div>
    </div>
  )
}
