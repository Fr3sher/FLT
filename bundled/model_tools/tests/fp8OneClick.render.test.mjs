/**
 * One button, on the model, naming the file it will take — the fp8 tool's
 * states, MOUNTED (a `useEffect` never runs in this harness, so the
 * plan / progress / outcome branches are separate components precisely so a
 * test can render each one). The census that keeps the cloud button gone and
 * the recipe hand-off pins stayed with the core
 * (frontend/tests/fp8-one-click-contract.test.mjs); what renders lives here,
 * with the component.
 */
import assert from 'node:assert/strict'
import test from 'node:test'

import { createElement, renderToStaticMarkup } from '../../../frontend/tests/support/mountJsx.mjs'

const Fp8Deliver = await import('../frontend/panels/Fp8QuantizeTool.jsx')

const render = (Component, props) => renderToStaticMarkup(createElement(Component, props))

const JOB = 'Krea_lds146_subject_Krea-2-Raw'
const PLAN = {
  ok: true,
  source_kind: 'huggingface',
  weight_basename: `${JOB}.safetensors`,
  source_bytes: 25_600_000_000,
  destination_dir: 'D:\\ComfyUI\\models\\diffusion_models',
  destination_dir_kind: 'comfyui',
  destination_dir_note: 'ComfyUI ▸ models/diffusion_models',
  destination_name: `${JOB}_fp8.safetensors`,
  estimated_bytes: 10_240_000_000,
  download_bytes: 25_600_000_000,
  free_bytes: 400_000_000_000,
  required_bytes: 49_000_000_000,
  enough_space: true,
  choice: { total: 3, is_final: true, step: null, pinned: false },
}

// ---- the plan says where the file goes, before anything moves ---------------

test('the plan names the checkpoint, the folder and the disk cost', () => {
  const html = render(Fp8Deliver.Fp8DeliverPlan, { plan: PLAN })
  assert.match(html, /Krea_lds146_subject_Krea-2-Raw\.safetensors/)
  assert.match(html, /the final save, chosen over 2 other checkpoints/)
  assert.match(html, /Krea_lds146_subject_Krea-2-Raw_fp8\.safetensors/)
  assert.match(html, /ComfyUI\\models\\diffusion_models/)
  assert.match(html, /ComfyUI lists it after a refresh/)
  assert.match(html, /25\.6 GB still has to come down/)
  assert.match(html, /400\.0 GB free there · about 49\.0 GB needed/)
  assert.match(html, /Quantize to fp8<\/button>/)
})

test('a step checkpoint is named as one rather than passed off as the model', () => {
  const html = render(Fp8Deliver.Fp8DeliverPlan, {
    plan: { ...PLAN, choice: { total: 3, is_final: false, step: 2750, pinned: true } },
  })
  assert.match(html, /the step 2750 checkpoint, chosen over 2 other checkpoints/)
})

test('an unconfigured ComfyUI says where the file really lands, and warns', () => {
  const html = render(Fp8Deliver.Fp8DeliverPlan, {
    plan: {
      ...PLAN, destination_dir_kind: 'fallback',
      destination_dir: 'C:\\lds\\data\\models\\diffusion_models',
      destination_dir_note: 'ComfyUI is not configured in Settings, so the file goes to '
        + "the app's own models folder — move it into ComfyUI yourself",
    },
  })
  assert.match(html, /⚠ ComfyUI is not configured in Settings/)
  assert.match(html, /text-amber-200/)
})

test('too little disk is a refusal with both numbers and a dead start button', () => {
  const html = render(Fp8Deliver.Fp8DeliverPlan, {
    plan: {
      ...PLAN, enough_space: false,
      space_error: 'not enough disk space where the file would go: 12.0 GB free in '
        + 'D:\\ComfyUI\\models\\diffusion_models, about 49 GB needed',
    },
  })
  assert.match(html, /12\.0 GB free/)
  assert.match(html, /about 49 GB needed/)
  assert.match(html, /role="alert"/)
  assert.match(html, /Quantize to fp8<\/button>/)
  // The start button AND the "check that folder" button (empty field) are dead.
  assert.equal((html.match(/disabled=""/g) || []).length, 2,
    'the start button must be dead while the disk cannot take the file')
  // A full drive ends this destination, not the operation: the same file often
  // fits one volume over, and refusing without offering that is a dead end.
  assert.match(html, /aria-label="Folder to write the fp8 file into instead"/)
  assert.match(html, /Check that folder<\/button>/)
})

test('keeping the master is the default, and both options carry their cost', () => {
  const html = render(Fp8Deliver.Fp8DeliverPlan, { plan: PLAN, keepMaster: true })
  assert.match(html, /Keep it — a local backup you can train from again \(25\.6 GB of disk\)/)
  assert.match(html, /Delete it — frees 25\.6 GB/)
  assert.match(html, /another 25\.6 GB download/)
  // Exactly one radio is checked, and it is "keep".
  const keep = html.slice(0, html.indexOf('Delete it'))
  assert.match(keep, /checked=""/)
  assert.equal((html.match(/checked=""/g) || []).length, 1)
})

test('a model already on this machine is never offered for deletion', () => {
  const html = render(Fp8Deliver.Fp8DeliverPlan, {
    plan: { ...PLAN, source_kind: 'local', download_bytes: 0 },
  })
  assert.doesNotMatch(html, /Delete it/)
  assert.doesNotMatch(html, /still has to come down/)
})

// ---- the long half is visible and stoppable --------------------------------

test('a download in flight shows the phase, the bytes, the target and a way out', () => {
  const html = render(Fp8Deliver.Fp8DeliverProgress, {
    onCancel: () => {},
    state: {
      status: 'downloading', weight_name: `${JOB}.safetensors`,
      downloaded_bytes: 6_400_000_000, download_total_bytes: 25_600_000_000,
      destination_dir: PLAN.destination_dir, destination_name: PLAN.destination_name,
    },
  })
  assert.match(html, /⬇ Downloading Krea_lds146_subject_Krea-2-Raw\.safetensors — 6\.4 GB of 25\.6 GB/)
  assert.match(html, /aria-valuenow="25"/)
  assert.match(html, /width:25%/)
  assert.match(html, /Stop<\/button>/)
  assert.match(html, /role="status"/)
})

test('local CPU progress does not offer an unsupported cancellation action', () => {
  const html = render(Fp8Deliver.Fp8DeliverProgress, {
    state: { status: 'quantizing', done: 1, total: 3, destination_dir: 'C:/models', destination_name: 'model_fp8.safetensors' },
  })
  assert.match(html, /1\/3 tensors/)
  assert.doesNotMatch(html, /Stop<\/button>/)
})

test('the conversion phase counts tensors rather than pretending to know bytes', () => {
  const html = render(Fp8Deliver.Fp8DeliverProgress, {
    state: {
      status: 'quantizing', done: 120, total: 480,
      destination_dir: PLAN.destination_dir, destination_name: PLAN.destination_name,
    },
  })
  assert.match(html, /✨ Quantizing on the CPU — 120\/480 tensors/)
  assert.match(html, /aria-valuenow="25"/)
})

test('an idle or finished job renders no progress block at all', () => {
  assert.equal(render(Fp8Deliver.Fp8DeliverProgress, { state: null }), '')
  assert.equal(render(Fp8Deliver.Fp8DeliverProgress, { state: { status: 'done' } }), '')
})

// ---- the outcome tells the whole truth --------------------------------------

test('success names the file, the folder and what happened to the master', () => {
  const html = render(Fp8Deliver.Fp8DeliverOutcome, {
    state: {
      status: 'done', destination_name: PLAN.destination_name,
      destination_dir: PLAN.destination_dir,
      result: { bytes_after: 10_100_000_000, scaled_tensors: 480, master_removed: false },
    },
  })
  assert.match(html, /Krea_lds146_subject_Krea-2-Raw_fp8\.safetensors/)
  assert.match(html, /10\.1 GB/)
  assert.match(html, /480 scaled tensors verified/)
  assert.match(html, /master was kept next to it/)

  const dropped = render(Fp8Deliver.Fp8DeliverOutcome, {
    state: {
      status: 'done', destination_name: PLAN.destination_name,
      destination_dir: PLAN.destination_dir,
      result: { bytes_after: 10_100_000_000, master_removed: true },
    },
  })
  assert.match(dropped, /master was deleted, as you asked/)
})

test('stopping says the bytes are kept — the reason someone dares stop', () => {
  const html = render(Fp8Deliver.Fp8DeliverOutcome, {
    state: {
      status: 'cancelled',
      error: 'Stopped. The part of the master already downloaded is kept, so starting '
        + 'again resumes instead of restarting.',
    },
  })
  assert.match(html, /resumes instead of restarting/)
})

test('a failure states that nothing was overwritten', () => {
  const html = render(Fp8Deliver.Fp8DeliverOutcome, {
    state: { status: 'error', error: 'Hugging Face refused the download (HTTP 401)' },
  })
  assert.match(html, /role="alert"/)
  assert.match(html, /Nothing was overwritten/)
})

// ---- the whole component still renders in its resting state -----------------

const TARGET = {
  repoId: 'me/krea-run-146', filename: `${JOB}.safetensors`, family: 'krea',
  name: `${JOB}.safetensors`, sizeBytes: 25_600_000_000,
  label: 'The full model this dataset’s run delivered',
}

test('with a target, the one click leads and the path field is the exception', () => {
  const html = render(Fp8Deliver.default, { target: TARGET })
  assert.match(html, /The full model this dataset’s run delivered/)
  assert.match(html, /Krea_lds146_subject_Krea-2-Raw\.safetensors/)
  assert.match(html, /25\.6 GB/)
  assert.match(html, /not on this machine — it is fetched first/)
  assert.match(html, /✨ Quantize to fp8<\/button>/)
  // The field survives, demoted, for a path nothing in the app points at.
  assert.match(html, /Or another file, already on this machine/)
  assert.match(html, /aria-label="Path of the model file to quantize to fp8"/)
})

test('the manual field is pre-filled when the app already holds a path', () => {
  const html = render(Fp8Deliver.default, { suggestedPath: 'D:\\models\\my-base.safetensors' })
  assert.match(html, /value="D:\\models\\my-base\.safetensors"/)
  // No target: no promise about a Hugging Face master that does not exist here.
  assert.doesNotMatch(html, /not on this machine — it is fetched first/)
})

test('a disabled host disables every control in either chrome', () => {
  for (const framed of [true, false]) {
    const html = render(Fp8Deliver.default, { framed, target: TARGET, disabled: true })
    assert.equal((html.match(/disabled=""/g) || []).length, 3,
      `framed=${framed}: the target button, the path field and its button must all be dead`)
  }
})

test('the slot hands the recipe door its props, and the panel ignores the surface name', () => {
  // PluginSlot passes `surface` to every contribution; the tool destructures
  // what it knows and must not spread the rest onto a DOM element.
  const html = render(Fp8Deliver.default, { surface: 'dense', target: TARGET, disabled: true })
  assert.doesNotMatch(html, /surface=/)
  assert.match(html, /✨ Quantize to fp8<\/button>/)
})
