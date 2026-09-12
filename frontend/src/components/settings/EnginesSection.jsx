import { CORE_ENGINE_CATALOG, engineSettingsOptions } from '../../engines/catalog.js'
import { useState } from 'react'
import { INPUT_CLASS, Card } from './primitives'
import { SettingsGroup, SettingsGroupsToc, useSettingsGroupProps } from './SettingsGroupsView'
import { ENGINES_GROUPS } from './settingsGroups'
import KleinLoraCombobox, { useKleinGenerationLoras } from './KleinLoraCombobox'
import ModelFilePicker, { useModelFiles } from './ModelFilePicker'
import PromptOverrideField from '../common/PromptOverrideField'
import PromptPreview from './PromptPreview'
import ResetToDefault from './ResetToDefault'
import { defaultValueAt } from './settingDefaults.js'
import { resetEngineSelection } from './settingDefaults.js'
import { kreaStrengthRange, KREA_LORA_STRENGTH_DEFAULT } from '../../utils/kreaGenerationLoras'
import { isFixedLoraDuplicate, fixedLoraDuplicateWarning } from '../../utils/loraDuplicateGuard'
import { kreaBaseNote, KREA_BASE_NOTE_CLASS } from '../../utils/kreaBaseNote'
// The bounds mirror krea_edit_helper's clamps. They live in utils/kreaDials.js
// because the workspace panel offers the SAME four dials — two copies of "512"
// would be two chances to drift away from the server.
import {
  KREA_GROUNDING_MIN, KREA_GROUNDING_MAX, KREA_GROUNDING_STEP,
  KREA_STEPS_MIN, KREA_STEPS_MAX,
  KREA_REF_BOOST_MIN, KREA_REF_BOOST_MAX, KREA_REF_BOOST_STEP,
  KREA_IDENTITY_STRENGTH_MIN, KREA_IDENTITY_STRENGTH_MAX, KREA_IDENTITY_STRENGTH_STEP,
  clampRefBoost, clampIdentityStrength,
  refBoostDescription, identityStrengthDescription, stepsDescription,
} from '../../utils/kreaDials.js'
import {
  identityPromptFields, PROMPT_SUBJECT_TYPES,
  readIdentityPrompt, writeIdentityPrompt, subjectHasOverride,
  GLOBAL_PROMPT_PART_FIELDS, SUBJECT_PROMPT_PART_FIELDS, FRAMING_PROMPT_PART_FIELDS,
} from '../common/promptOverride.js'
import { SUBJECT_TYPE_LABELS } from '../dataset/subjectTypes.js'

// The API engines' keys, models and lanes are their plugin's: it contributes a
// settings group of its own (the `settings.group` slot, rendered after the
// core's group below). The dropdown rows come from the catalog, API engines
// first as always listed — read inside the component, at render time.

/* Optional generation-LoRA PRESETS, originally for the local Klein engine
   (Idea by @waltm — Discord feature request) and now shared with the local
   Krea 2 Edit engine too: named combinations of user-pointed LoRA files (any
   files, any purpose — texture, anatomy, style…). Inside a preset the rows
   chain after the consistency/identity-edit LoRA in LIST ORDER (file +
   strength, reorderable, capped at 8). Per run each engine's own tuning panel
   just PICKS a preset, starting on the engine's own default preset setting
   ("None" until one is chosen) — the choice carries the intent,
   there is no automatic gating. The app never ships or hardcodes a LoRA name. */
const MAX_GENERATION_LORAS = 8        // mirrors the klein_edit_helper AND
const MAX_GENERATION_LORA_PRESETS = 12 // krea_edit_helper caps — both the same

const SMALL_BTN = 'grid h-6 w-6 place-items-center rounded border border-border text-xs ' +
  'text-content-muted hover:bg-surface-raised disabled:opacity-30'
const TEXT_BTN = 'rounded-md border border-border-strong px-2 py-1 text-xs font-medium ' +
  'text-content hover:bg-surface-raised disabled:opacity-50'

/** Fresh name not colliding with the existing presets ("Preset 2", "x (copy)"…). */
function freeName(presets, base) {
  const taken = new Set(presets.map((p) => (p?.name || '').trim()))
  if (!taken.has(base)) return base
  for (let n = 2; ; n += 1) {
    const cand = `${base} ${n}`
    if (!taken.has(cand)) return cand
  }
}

/* One preset: its name, its ordered LoRA rows, and the row controls. Shared by
   the Klein and the Krea cards — the shapes are identical, only the strength
   range, its default and the engine the badge judges for differ. */
function LoraPresetCard({ preset, index, presets, save, loraScan,
                          engineLabel = 'Klein', strengthRange, defaultStrength,
                          placeholder = 'klein/my-lora.safetensors',
                          engineId = 'klein', fixedLora = '' }) {
  const rows = Array.isArray(preset?.loras) ? preset.loras : []
  const patchPreset = (p) => save(presets.map((x, j) => (j === index ? { ...x, ...p } : x)))
  const patchRow = (i, p) => patchPreset({ loras: rows.map((r, j) => (j === i ? { ...r, ...p } : r)) })
  const moveRow = (i, dir) => {
    const j = i + dir
    if (j < 0 || j >= rows.length) return
    const next = [...rows]
    ;[next[i], next[j]] = [next[j], next[i]]
    patchPreset({ loras: next })
  }
  return (
    <div className="rounded-lg border border-border p-3 space-y-2">
      <div className="flex items-center gap-2">
        <input
          type="text" aria-label={`Preset ${index + 1} name`}
          value={preset?.name || ''}
          onChange={(e) => patchPreset({ name: e.target.value })}
          placeholder="Preset name"
          className={`${INPUT_CLASS} mt-0 font-medium`}
        />
        <button type="button" className={TEXT_BTN}
          disabled={presets.length >= MAX_GENERATION_LORA_PRESETS}
          onClick={() => save([...presets,
            { ...preset, name: freeName(presets, `${(preset?.name || 'Preset').trim() || 'Preset'} (copy)`), loras: rows.map((r) => ({ ...r })) }])}
          title="Duplicate this preset">
          Duplicate
        </button>
        <button type="button" className={`${TEXT_BTN} hover:bg-red-500/15 hover:text-red-300`}
          onClick={() => save(presets.filter((_, j) => j !== index))}
          title="Delete this preset">
          Delete
        </button>
      </div>
      {rows.length === 0 && (
        <p className="text-xs text-content-muted">Empty preset — add a LoRA below.</p>
      )}
      {rows.map((row, i) => {
        const strength = Number.isFinite(Number(row?.strength)) ? Number(row.strength) : defaultStrength
        const range = strengthRange(row?.file || '')
        // The row the server will DROP: it names the LoRA this engine already
        // loads outside the presets. Said HERE, where the row is written —
        // until now the only trace was one line in the server log, so a preset
        // whose single row was that file produced a run with no LoRA at all and
        // nothing on screen to explain it. Comparison is normcase+normpath, the
        // server's own, so a '/' or a case difference cannot dodge it.
        const duplicate = isFixedLoraDuplicate(row?.file, fixedLora)
        return (
          <div key={i} className="flex items-center gap-2 flex-wrap">
            <span className="text-xs text-content-muted w-4 shrink-0" aria-hidden="true">{i + 1}.</span>
            <KleinLoraCombobox
              ariaLabel={`Preset ${index + 1} LoRA file ${i + 1}`}
              value={row?.file || ''}
              onChange={(next) => patchRow(i, { file: next })}
              engineLabel={engineLabel}
              placeholder={placeholder}
              {...loraScan}
            />
            <label className="flex items-center gap-1.5 text-xs text-content-muted">
              <span className="whitespace-nowrap">{strength.toFixed(2)}</span>
              <input
                type="range" min={range.min} max={range.max} step={0.05} value={strength}
                aria-label={`Preset ${index + 1} LoRA ${i + 1} strength`}
                onChange={(e) => patchRow(i, { strength: Number(e.target.value) })}
                className="w-28 accent-indigo-500"
              />
            </label>
            <button type="button" onClick={() => moveRow(i, -1)} disabled={i === 0}
              aria-label={`Move LoRA ${i + 1} up in preset ${index + 1}`} title="Chain earlier" className={SMALL_BTN}>↑</button>
            <button type="button" onClick={() => moveRow(i, 1)} disabled={i === rows.length - 1}
              aria-label={`Move LoRA ${i + 1} down in preset ${index + 1}`} title="Chain later" className={SMALL_BTN}>↓</button>
            <button type="button" onClick={() => patchPreset({ loras: rows.filter((_, j) => j !== i) })}
              aria-label={`Remove LoRA ${i + 1} from preset ${index + 1}`} title="Remove this LoRA"
              className={`${SMALL_BTN} hover:bg-red-500/15 hover:text-red-300`}>✕</button>
            {/* w-full inside the WRAPPING flex row = its own line under the
                controls, without re-nesting (and re-indenting) the whole row. */}
            {duplicate && (
              <p role="alert" className="w-full pl-6 text-[0.6875rem] text-amber-400">
                {fixedLoraDuplicateWarning(engineId)}
              </p>
            )}
          </div>
        )
      })}
      <div className="flex items-center gap-3">
        <button
          type="button" className={TEXT_BTN}
          onClick={() => patchPreset({ loras: [...rows, { file: '', strength: defaultStrength }] })}
          disabled={rows.length >= MAX_GENERATION_LORAS}
        >
          ＋ Add LoRA
        </button>
        <span className="text-xs text-content-muted">{rows.length}/{MAX_GENERATION_LORAS} in the chain</span>
      </div>
    </div>
  )
}

/* Which preset the run panel OPENS on, per engine.
   The panel used to start on "None" on every single visit, so a preset someone
   had carefully built applied only when they remembered to re-pick it — and a
   run that forgot carried no LoRA anywhere in its PNG metadata, which reads as
   the app ignoring its own settings. This is the missing half of the feature,
   not a new one.
   Deliberately per ENGINE: klein.generation_lora_presets and
   krea.generation_lora_presets are independent lists where the same NAME can
   designate two different chains, so one shared default would be a lie half the
   time. And deliberately a STARTING POINT, which the note under the field says
   out loud: the run panel still offers None and every other preset for that run,
   and choosing there never writes back here. */
function DefaultPresetField({ id, engineLabel, presets, value, onChange }) {
  const names = presets.map((p) => (p?.name || '').trim()).filter(Boolean)
  const current = typeof value === 'string' ? value.trim() : ''
  // Fail-closed, mirroring resolveDefaultPresetName: a name matching nothing
  // (renamed preset, hand-edited config.json) behaves as "None" everywhere, so
  // the field must not silently show "None" as if the setting were empty.
  const stale = !!current && !names.includes(current)
  return (
    <div className="border-t border-border pt-3">
      <label htmlFor={id} className="block text-xs font-medium text-content">
        Preset selected by default
      </label>
      <select
        id={id}
        value={stale ? '' : current}
        onChange={(e) => onChange(e.target.value)}
        className={`${INPUT_CLASS} sm:max-w-xs`}
      >
        <option value="">None</option>
        {names.map((n) => <option key={n} value={n}>{n}</option>)}
      </select>
      <p className="mt-1 text-[0.6875rem] text-content-subtle">
        Which preset the {engineLabel} tuning panel starts on when you open a dataset.
        “None” is the shipped default and keeps today’s behaviour exactly. You can still
        pick another preset — or None — for a single run without changing this setting.
      </p>
      {stale && (
        <p role="alert" className="mt-1 text-[0.6875rem] text-amber-400">
          “{current}” is no longer one of your presets, so runs start on None. Pick a
          preset above to set a new default.
        </p>
      )}
    </div>
  )
}

function KleinLorasCard({ config, setField }) {
  const presets = Array.isArray(config.klein?.generation_lora_presets)
    ? config.klein.generation_lora_presets : []
  const save = (next) => setField('klein', 'generation_lora_presets', next)
  // ONE scan of ComfyUI's loras folder, shared by every row's picker (never one
  // fetch per row). Degrades to free-text on any failure — see the hook.
  const loraScan = useKleinGenerationLoras()
  return (
    <Card
      id="klein-generation-lora-presets"
      title="Klein generation LoRA presets (optional)"
      help={`Named combinations of your own LoRA files, chained after the consistency LoRA on the local Klein engine — inside a preset the order is the chain order (max ${MAX_GENERATION_LORAS} LoRAs each, ${MAX_GENERATION_LORA_PRESETS} presets). Pick each row from the LoRAs found under ComfyUI's models/loras (Klein-compatible ones are listed first; you can still type a path for a file not on disk yet) — any LoRA, any purpose. Per run, pick a preset in the workspace's Klein tuning panel — it opens on the default preset chosen below ("None" until you choose one), and picking something else there applies to that run only. Presets and LoRA autocomplete by @waltm (Discord).`}
    >
      {presets.length === 0 && (
        <p className="text-sm text-content-muted">No presets yet — create your first combination below.</p>
      )}
      {presets.map((preset, i) => (
        <LoraPresetCard key={i} preset={preset} index={i} presets={presets} save={save}
          loraScan={loraScan} engineLabel="Klein"
          strengthRange={() => ({ min: 0, max: 1.5 })}
          defaultStrength={0.6}
          engineId="klein" fixedLora={config.klein?.consistency_lora || ''} />
      ))}
      <div className="flex items-center gap-3">
        <button
          type="button" className={TEXT_BTN}
          onClick={() => save([...presets, { name: freeName(presets, 'My preset'), loras: [] }])}
          disabled={presets.length >= MAX_GENERATION_LORA_PRESETS}
        >
          ＋ New preset
        </button>
        <span className="text-xs text-content-muted">{presets.length}/{MAX_GENERATION_LORA_PRESETS}</span>
      </div>
      <DefaultPresetField
        id="klein-default-lora-preset" engineLabel="Klein" presets={presets}
        value={config.klein?.default_generation_lora_preset || ''}
        onChange={(v) => setField('klein', 'default_generation_lora_preset', v)} />
    </Card>
  )
}

/* The pinnable Klein model slots. `key` is the DOM id the help registry focuses
   (the contract test scans these literals); `cfg` is the klein.* config key;
   `slot` matches caps.comfyui.klein_overrides.
   Ported from socrasteeze's branch (GitHub #20). */
const KLEIN_MODEL_SLOTS = [
  { key: 'klein-model-unet', cfg: 'unet', slot: 'unet', pick: 'klein_unet', label: 'Diffusion model (UNET)',
    hint: 'Full path from anywhere, or relative to a diffusion-model folder — e.g. klein/flux-2-klein-9b-fp8.safetensors under models/unet (a bare filename for a file sitting at a folder root). A filename without "fp8" loads at full precision instead of being quantized.' },
  { key: 'klein-model-text_encoder', cfg: 'text_encoder', slot: 'text_encoder', pick: 'klein_text_encoder', label: 'Text encoder',
    hint: 'Full path, or relative to models/text_encoders — e.g. qwen_3_8b_fp8mixed.safetensors.' },
  { key: 'klein-model-vae', cfg: 'vae', slot: 'vae', pick: 'klein_vae', label: 'VAE',
    hint: 'Full path, or relative to models/vae — e.g. flux2-vae.safetensors.' },
  { key: 'klein-model-consistency_lora', cfg: 'consistency_lora', slot: 'consistency_lora', pick: 'klein_consistency_lora',
    label: 'Consistency LoRA',
    placeholder: 'Empty = no consistency LoRA',
    missText: 'Not found — at the shipped name the LoRA is simply skipped (Setup can download it); a name you chose yourself stops the engine instead',
    hint: 'Full path, or relative to models/loras — the structure-anchoring LoRA chained onto the Klein edit graph. Unlike the three above, this one has a shipped default and clearing it disables the LoRA rather than turning on auto-detection.' },
]

/* One badge per resolve status from caps.comfyui.klein_overrides. Two wordings
   are deliberate rather than cosmetic:
   - 'outside_roots' is NOT "not found" — the file IS there, ComfyUI simply
     cannot reach it, and a different action fixes that;
   - what happens after a miss is not the same for every slot, so the badge does
     not claim it: the three model slots fall back to auto-detection, while the
     consistency LoRA has no detection to fall back to (it is just skipped, and
     reported as a missing asset Setup can download). Saying "auto-detection is
     used" on that row would name a mechanism that does not exist for it. */
function overrideBadge(st, missText) {
  if (!st) return null
  if (st.found) return { cls: 'text-emerald-400', text: 'Found' }
  if (st.status === 'outside_roots') {
    return { cls: 'text-amber-400',
             text: "Could not be linked into ComfyUI's model folders — check permissions, or move the file" }
  }
  return { cls: 'text-amber-400', text: missText || 'Not found — the engine will refuse to run until you fix or clear this' }
}

/* ONE pinnable slot. Its own component because each row needs its OWN scan of a
   DIFFERENT ComfyUI folder, and a hook cannot be called inside a .map. Each scan
   is cached server-side on that folder's mtime, so four rows are four cheap
   requests, not four directory walks. */
function KleinModelSlotRow({ spec, config, setField, override }) {
  const { key, cfg, label, hint, placeholder, missText, pick } = spec
  const scan = useModelFiles(pick)
  const badge = overrideBadge(override, missText)
  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-x-2">
        <label htmlFor={key} className="block text-sm font-medium text-content">{label}</label>
        {badge && (
          <span className={`text-xs sm:text-right ${badge.cls}`}>{badge.text}</span>
        )}
      </div>
      <ModelFilePicker
        id={key}
        ariaLabel={`Klein ${label}`}
        value={config.klein?.[cfg] || ''}
        onChange={(v) => setField('klein', cfg, v)}
        placeholder={placeholder || 'Empty = auto-detect'}
        {...scan}
      />
      <p className="mt-1 text-[0.6875rem] text-content-subtle">{hint}</p>
    </div>
  )
}

function KleinModelFilesCard({ config, setField, caps }) {
  const overrides = caps?.comfyui?.klein_overrides || {}
  return (
    <Card
      id="klein-model-files"
      title="Klein model files (optional)"
      help="Pin the exact files the Klein graph loads instead of relying on auto-detection (the canonical download names, then a narrow token scan). Each field takes a full absolute path OR a ComfyUI-relative loader name. A path under one of ComfyUI's model folders (extra_model_paths.yaml roots included) is converted automatically to what the loader needs; a path from anywhere else is hardlinked into an lds-pinned/ folder so ComfyUI can load it without you moving a multi-GB file. Each field lists the files actually found in that ComfyUI folder — you can still type a name or a full path for a file that is not there yet. Leave a field empty to keep auto-detection for that slot. A pinned file that cannot be resolved STOPS the engine and says which one: it used to fall back to auto-detection, which meant the graph loaded a different file from the one shown here and nobody found out until the images came back wrong. Clearing the field is how you go back to auto-detection. Contributed by socrasteeze (GitHub)."
    >
      {KLEIN_MODEL_SLOTS.map((s) => (
        <KleinModelSlotRow key={s.key} spec={s} config={config} setField={setField}
          override={overrides[s.slot]} />
      ))}
    </Card>
  )
}

/* Klein GENERATION sampling. The shipped workflow hardcodes 5 steps at its
   sampler node and nothing on the generation paths ever passed a value, so the
   engine's own `sampler_steps` parameter was unreachable — "is the number of
   generation steps fixed at 5?" (ashish.sinha, Discord). Default 5 = the exact
   historical render; the ceiling mirrors the backend clamp. Deliberately its own
   card, next to the other Klein knobs and clearly NOT the "Upscale & improve"
   steps, which drive a different pass. */
const KLEIN_GENERATION_STEPS_MAX = 50   // face_dataset_service._IMPROVE_MAX_STEPS
const KLEIN_EDIT_LORA_MAX = 2           // face_dataset_service._IMPROVE_MAX_STRENGTH

function KleinGenerationCard({ config, setField, configDefaults }) {
  // The shipped 5 is read from the server payload, never retyped here: it used
  // to be a literal `?? 5` in this file, i.e. a second copy of a backend default
  // that nothing kept in sync.
  const shipped = defaultValueAt(configDefaults, 'klein', 'generation_steps')
  const steps = config.klein?.generation_steps ?? shipped
  // Enhancement LoRA on the EDIT lanes. The workflow pins node 139 at 0.8 and no
  // lane but "Upscale & improve" overrode it, which only became visible once
  // Setup started downloading the file: every edit gained a style LoRA at 0.8.
  // Default 0 = the render before that download existed.
  const editLoraShipped = defaultValueAt(configDefaults, 'klein', 'edit_base_lora_strength')
  const editLora = config.klein?.edit_base_lora_strength ?? editLoraShipped
  return (
    <Card
      id="klein-generation"
      title="Klein generation quality"
      help="How many sampler steps the local Klein engine spends on each generated variation, and how much of the enhancement LoRA it mixes in. 5 steps is the value the app used before this was exposed, so leaving it alone keeps today's result. More steps render more cleanly but take proportionally longer — 10 steps is roughly twice the wait per image. It will not fix a wrong prompt: anatomy problems (extra limbs, tails) come from the identity prompt, not from the step count. Raised by ashish.sinha (Discord)."
    >
      <div className="sm:max-w-xs">
        <label htmlFor="klein-generation-steps" className="block text-xs font-medium text-content">
          Generation steps
        </label>
        <input
          id="klein-generation-steps"
          type="number"
          min={1}
          max={KLEIN_GENERATION_STEPS_MAX}
          step={1}
          value={steps}
          onChange={(e) => setField('klein', 'generation_steps',
            e.target.value === '' ? shipped : Number(e.target.value))}
          className={INPUT_CLASS}
        />
        <p className="mt-1 text-[0.6875rem] text-content-subtle">
          {shipped} = the shipped value. More steps = slower, usually cleaner; 1–{KLEIN_GENERATION_STEPS_MAX}.
          Applies to variations, regenerations and the small-image rescue — not to
          the optional Improve &amp; upscale plug-in, which owns its own Steps.
        </p>
        <ResetToDefault label="Generation steps" section="klein" field="generation_steps"
          config={config} configDefaults={configDefaults} setField={setField} />
      </div>
      <div className="mt-4 sm:max-w-xs">
        <label htmlFor="klein-edit-lora" className="block text-xs font-medium text-content">
          Enhancement LoRA on edits
        </label>
        <input
          id="klein-edit-lora"
          type="number"
          min={0}
          max={KLEIN_EDIT_LORA_MAX}
          step={0.05}
          value={editLora}
          onChange={(e) => setField('klein', 'edit_base_lora_strength',
            e.target.value === '' ? editLoraShipped : Number(e.target.value))}
          className={INPUT_CLASS}
        />
        <p className="mt-1 text-[0.6875rem] text-content-subtle">
          0 = off. The workflow carries a detail LoRA (klein/realistic.safetensors) at
          0.8, and until now nothing turned it down on an edit — it pulled results
          away from the instruction you typed. Raise it to add its detail on purpose.
          Applies to reference edits, variations, regenerations and the small-image
          rescue. The optional Improve &amp; upscale plug-in has a separate enhancement strength.
        </p>
        <ResetToDefault label="Enhancement LoRA on edits"
          section="klein" field="edit_base_lora_strength"
          config={config} configDefaults={configDefaults} setField={setField} />
      </div>
    </Card>
  )
}

/* Krea 2 Identity Edit — the second LOCAL engine. Its headline knob is
   `grounding_px`, THE consistency <-> prompt-adherence dial, so it is first and
   explained in plain words: a number nobody can interpret is not a setting.
   The FOUR calibration dials of this card (grounding, steps, reference pull,
   identity LoRA strength) are the same four the workspace's "Krea 2 Edit
   tuning" panel offers, on purpose: they are judged on the images that panel
   produces and configured here, and since every control writes the SAME global
   key through the same endpoint there is only ever one value to read.
   The two path fields are NOT duplicated there — they are filled once at
   install, not adjusted while looking at a result. They are BLANK-MEANS-AUTO on
   purpose: the resolver finds the files by canonical name then by a narrow
   token across every ComfyUI model root, so an install that looks nothing like
   the developer's works untouched — they exist for the person whose files are
   named something else. */

function KreaCard({ config, setField, configDefaults, caps }) {
  const krea = config.krea || {}
  const reset = { config, configDefaults, setField }
  const dflt = (key) => defaultValueAt(configDefaults, 'krea', key)
  // One scan per slot, fired when the card mounts. Both degrade to an empty list
  // (=> plain free-text field) rather than blocking the panel — an absolute path
  // from outside every ComfyUI root is a legitimate value no scan can enumerate.
  const baseScan = useModelFiles('krea_base_model')
  const identityScan = useModelFiles('krea_identity_lora')
  const grounding = Number(krea.grounding_px ?? dflt('grounding_px'))
  const steps = krea.steps ?? dflt('steps')
  // Clamped for DISPLAY only: a config.json hand-edited past the server's clamp
  // would otherwise park the slider thumb at an end while the label showed a
  // number the graph will never receive. The server re-clamps on its side.
  const refBoost = clampRefBoost(krea.ref_boost, dflt('ref_boost'))
  const identityStrength = clampIdentityStrength(krea.identity_lora_strength,
    dflt('identity_lora_strength'))
  // WHICH Krea base this install loads, named. Resolved SERVER-side
  // (caps.comfyui.krea_base_resolved = the resolve_krea_unet() the generation
  // path calls) — the browser ranks nothing. See utils/kreaBaseNote.js.
  const baseNote = kreaBaseNote(krea.base_model, caps?.comfyui?.krea_base_resolved)
  return (
    <Card
      id="krea-engine"
      title="Krea 2 Edit (local)"
      help="The second local engine. It re-stages your reference photo — new angle, framing, light, background — while keeping the face and the body, from that ONE photo and with no character LoRA, which is what makes it useful before a LoRA exists. It needs the comfyui-krea2edit custom-node pack plus four model files; the engine card in the workspace names whatever is still missing. Krea Fit v1.2 honors the selected shot card's framing and aspect ratio instead of copying the source photo's shape."
    >
      <div className="sm:max-w-md">
        <label htmlFor="krea-grounding" className="block text-xs font-medium text-content">
          Reference grounding ({grounding} px)
        </label>
        <input
          id="krea-grounding"
          type="range"
          min={KREA_GROUNDING_MIN}
          max={KREA_GROUNDING_MAX}
          step={KREA_GROUNDING_STEP}
          value={grounding}
          onChange={(e) => setField('krea', 'grounding_px', Number(e.target.value))}
          className="mt-1 w-full accent-violet-500"
        />
        <p className="mt-1 text-[0.6875rem] text-content-subtle">
          The resolution your reference is shown to the model&rsquo;s vision encoder at — the
          consistency ↔ prompt dial. At the low end it follows the shot description (more
          variety in pose, outfit and scene, looser likeness). <b>Higher</b> = it resembles
          the reference more, but can copy the pose and outfit you asked it to change.
          512 px is the dataset-restaging balance: it keeps the prompt and selected shot card
          in charge while preserving identity. Raise it deliberately when reference likeness
          matters more. Also adjustable, with this exact value, from the workspace&rsquo;s
          Krea 2 Edit tuning panel.
        </p>
        <ResetToDefault label="Reference grounding" section="krea" field="grounding_px" {...reset} />
      </div>

      <div className="mt-3 sm:max-w-md">
        <label htmlFor="krea-steps" className="block text-xs font-medium text-content">
          Sampler steps
        </label>
        <input
          id="krea-steps"
          type="number"
          min={KREA_STEPS_MIN}
          max={KREA_STEPS_MAX}
          step={1}
          value={steps}
          onChange={(e) => setField('krea', 'steps',
            e.target.value === '' ? dflt('steps') : Number(e.target.value))}
          className={INPUT_CLASS}
        />
        <p className="mt-1 text-[0.6875rem] text-content-subtle">
          {stepsDescription(steps)}. {dflt('steps')} is the value the model&rsquo;s own
          reference workflow uses. More is slower and rarely better on this pipeline.
        </p>
        <ResetToDefault label="Sampler steps" section="krea" field="steps" {...reset} />
      </div>

      {/* The two calibration dials that used to have NO input on this page: they
          were reachable only from the workspace panel, so "where do I change
          this?" had a different answer per dial. Same key, same endpoint, same
          value — a slider here and a slider there cannot disagree. */}
      <div className="mt-3 sm:max-w-md">
        <label htmlFor="krea-ref-boost" className="block text-xs font-medium text-content">
          Reference pull ({refBoost})
        </label>
        <input
          id="krea-ref-boost"
          type="range"
          min={KREA_REF_BOOST_MIN}
          max={KREA_REF_BOOST_MAX}
          step={KREA_REF_BOOST_STEP}
          value={refBoost}
          onChange={(e) => setField('krea', 'ref_boost',
            clampRefBoost(e.target.value, dflt('ref_boost')))}
          className="mt-1 w-full accent-violet-500"
        />
        <p className="mt-1 text-[0.6875rem] text-content-subtle">
          {refBoostDescription(refBoost)}. How hard the source latent is pushed back into the
          model at every denoising step — the lever for &ldquo;the subject does not look enough
          like my reference&rdquo;. High values also recopy the composition, pose and outfit the
          shot card asked it to change. Also on the workspace&rsquo;s Krea 2 Edit tuning panel,
          where you judge the result.
        </p>
        <ResetToDefault label="Reference pull" section="krea" field="ref_boost"
          value={refBoost} {...reset} />
      </div>

      <div className="mt-3 sm:max-w-md">
        <label htmlFor="krea-identity-lora-strength" className="block text-xs font-medium text-content">
          Identity LoRA strength ({identityStrength})
        </label>
        <input
          id="krea-identity-lora-strength"
          type="range"
          min={KREA_IDENTITY_STRENGTH_MIN}
          max={KREA_IDENTITY_STRENGTH_MAX}
          step={KREA_IDENTITY_STRENGTH_STEP}
          value={identityStrength}
          onChange={(e) => setField('krea', 'identity_lora_strength',
            clampIdentityStrength(e.target.value, dflt('identity_lora_strength')))}
          className="mt-1 w-full accent-violet-500"
        />
        <p className="mt-1 text-[0.6875rem] text-content-subtle">
          {identityStrengthDescription(identityStrength)}. The weight of the Krea 2
          identity-edit LoRA itself — the piece that carries the face across. Below 1 loosens
          the likeness, 0 disables the face transfer, above 1 is past what the file was
          trained for and can posterize. Also on the workspace&rsquo;s Krea 2 Edit tuning panel.
        </p>
        <ResetToDefault label="Identity LoRA strength" section="krea"
          field="identity_lora_strength" value={identityStrength} {...reset} />
      </div>

      <div className="mt-3 sm:max-w-md">
        <label htmlFor="krea-base-model" className="block text-xs font-medium text-content">
          Base model file (optional)
        </label>
        <ModelFilePicker
          id="krea-base-model"
          ariaLabel="Krea base model file"
          value={krea.base_model ?? ''}
          onChange={(v) => setField('krea', 'base_model', v)}
          placeholder="auto — finds a Krea 2 Turbo/Raw build"
          {...baseScan}
        />
        <p className={`mt-1 font-mono text-[0.6875rem] ${KREA_BASE_NOTE_CLASS[baseNote.tone]}`}>
          {baseNote.text}
        </p>
        <p className="mt-1 text-[0.6875rem] text-content-subtle">
          Leave blank unless you own several Krea builds. Blank = the app picks a Krea 2
          Turbo then Raw model from your ComfyUI. The list is what the app would actually
          elect from: non-Krea-2 checkpoints that merely carry &ldquo;krea&rdquo; in their name are
          skipped there too, because the identity LoRA renders pure noise on them. Pick a
          file that is not on disk and Krea refuses to run rather than loading another one.
        </p>
        {/* The default here is the EMPTY string, and resetting writes exactly
            that: blank means "resolve it yourself", and a reset must give that
            state back rather than freeze whichever file the app happens to
            pick today. */}
        <ResetToDefault label="Base model file" section="krea" field="base_model" {...reset} />
      </div>

      <div className="mt-3 sm:max-w-md">
        <label htmlFor="krea-identity-lora" className="block text-xs font-medium text-content">
          Identity edit LoRA (optional)
        </label>
        <ModelFilePicker
          id="krea-identity-lora"
          ariaLabel="Krea identity edit LoRA"
          value={krea.identity_lora ?? ''}
          onChange={(v) => setField('krea', 'identity_lora', v)}
          placeholder="blank = find krea2_identity_edit automatically"
          {...identityScan}
        />
        <p className="mt-1 text-[0.6875rem] text-content-subtle">
          Blank = the app searches your LoRA folders for a krea2_identity_edit file, so a
          renamed download still works. Name one here and that is the LoRA it loads — if it
          is not on disk, Krea refuses to run instead of substituting another face transfer.
        </p>
        <ResetToDefault label="Identity edit LoRA" section="krea" field="identity_lora" {...reset} />
      </div>
    </Card>
  )
}

/* The Krea hi-res fix — a SECOND latent pass on the generation graph.

   It sits in the Krea group but reads `krea_hires.*`, not `krea.*`, and that is
   not tidiness: the card above tunes the Krea 2 EDIT engine, a hand-built graph
   that never loads krea2_turbo.json. Two graphs, two namespaces; a shared one
   would be a dial that silently applies to only one of them.

   Off by default, and off means no node is added to the graph at all — an
   install that never touches this renders exactly what it rendered before. */
const KREA_HIRES_SCALE_MIN = 1.0
// utils/comfyui.KREA_HIRES_MAX_SCALE — the server re-clamps on its side.
const KREA_HIRES_SCALE_MAX = 2.0
const KREA_HIRES_SCALE_STEP = 0.25
const KREA_HIRES_DENOISE_MIN = 0.05
const KREA_HIRES_DENOISE_MAX = 1.0
const KREA_HIRES_STEPS_MAX = 50

/** What the configured scale costs and buys, in the units people think in. A x2
 *  LATENT is x4 the pixels, which is the number that decides whether it fits. */
function hiresScaleNote(scale, width = 1024, height = 1024) {
  if (!(scale > 1)) return 'Off — the graph is built exactly as it is today, with a single pass.'
  const w = Math.round(width * scale), h = Math.round(height * scale)
  return `A ${width}x${height} first pass is re-sampled at ${w}x${h} `
    + `(${(scale * scale).toFixed(2)}x the pixels, so roughly that much again in time and VRAM).`
}

function KreaHiresCard({ config, setField, configDefaults }) {
  const hires = config.krea_hires || {}
  const reset = { config, configDefaults, setField }
  const dflt = (key) => defaultValueAt(configDefaults, 'krea_hires', key)
  // Clamped for DISPLAY only, like the dials above: a hand-edited config.json
  // past the server's clamp would otherwise park the thumb at one end while the
  // label showed a number the graph will never receive.
  const scale = Math.min(KREA_HIRES_SCALE_MAX,
    Math.max(KREA_HIRES_SCALE_MIN, Number(hires.scale ?? dflt('scale')) || KREA_HIRES_SCALE_MIN))
  const denoise = Math.min(KREA_HIRES_DENOISE_MAX,
    Math.max(KREA_HIRES_DENOISE_MIN, Number(hires.denoise ?? dflt('denoise')) || KREA_HIRES_DENOISE_MIN))
  const steps = hires.steps ?? dflt('steps')
  const on = scale > 1
  return (
    <Card
      id="krea-hires"
      title="Krea hi-res fix (local)"
      help="A second sampling pass at a higher latent resolution, on the Krea generation graph — the Test Studio grid and the LoRA Canvas. Krea composes at the resolution it samples: asked for the final size in one pass it loses framing and starts duplicating subjects, kept small it caps the detail no upscaler can invent afterwards. Sampling small and re-sampling an upscaled latent lets the model DRAW that detail instead. Core ComfyUI nodes only — nothing to install. Off by default."
    >
      <div className="sm:max-w-md">
        <label htmlFor="krea-hires-scale" className="block text-xs font-medium text-content">
          Second pass ({on ? `${scale}x the latent` : 'off'})
        </label>
        <input
          id="krea-hires-scale"
          type="range"
          min={KREA_HIRES_SCALE_MIN}
          max={KREA_HIRES_SCALE_MAX}
          step={KREA_HIRES_SCALE_STEP}
          value={scale}
          onChange={(e) => setField('krea_hires', 'scale', Number(e.target.value))}
          className="mt-1 w-full accent-violet-500"
        />
        <p className="mt-1 text-[0.6875rem] text-content-subtle">
          {hiresScaleNote(scale)} {on ? '' : 'Slide right to turn it on. '}
          1.5x is the value the reference workflow this was ported from uses.
        </p>
        <ResetToDefault label="Second pass" section="krea_hires" field="scale" {...reset} />
      </div>

      {/* The two dials below only mean anything once the pass exists. Shown
          disabled rather than hidden: a control that appears out of nowhere is
          how people miss that it was there to be set. */}
      <div className={`mt-3 sm:max-w-md ${on ? '' : 'opacity-50'}`}>
        <label htmlFor="krea-hires-denoise" className="block text-xs font-medium text-content">
          How much it may rewrite ({denoise})
        </label>
        <input
          id="krea-hires-denoise"
          type="range"
          min={KREA_HIRES_DENOISE_MIN}
          max={KREA_HIRES_DENOISE_MAX}
          step={0.05}
          value={denoise}
          disabled={!on}
          onChange={(e) => setField('krea_hires', 'denoise', Number(e.target.value))}
          className="mt-1 w-full accent-violet-500"
        />
        <p className="mt-1 text-[0.6875rem] text-content-subtle">
          The dial of the whole feature. Near 1 the second pass ignores the first and
          renders a <b>different</b> picture at the larger size; too low and it costs a
          full extra pass to change nothing. {dflt('denoise')} keeps the composition and
          rewrites the texture.
        </p>
        <ResetToDefault label="How much it may rewrite" section="krea_hires" field="denoise" {...reset} />
      </div>

      <div className={`mt-3 sm:max-w-md ${on ? '' : 'opacity-50'}`}>
        <label htmlFor="krea-hires-steps" className="block text-xs font-medium text-content">
          Second-pass steps (0 = same as the first)
        </label>
        <input
          id="krea-hires-steps"
          type="number"
          min={0}
          max={KREA_HIRES_STEPS_MAX}
          step={1}
          value={steps}
          disabled={!on}
          onChange={(e) => setField('krea_hires', 'steps',
            e.target.value === '' ? dflt('steps') : Number(e.target.value))}
          className={INPUT_CLASS}
        />
        <p className="mt-1 text-[0.6875rem] text-content-subtle">
          0 inherits the first pass&rsquo;s count, which is the sane default: at a denoise
          below 1 the pass only walks part of the schedule anyway.
        </p>
        <ResetToDefault label="Second-pass steps" section="krea_hires" field="steps" {...reset} />
      </div>
    </Card>
  )
}

/* Krea's own always-on LoRA presets. Same shape as the Klein card — the two lanes
   are deliberate copies — with two differences that matter: the strength ceiling
   opens to 20 for utility LoRAs (the bypass ones do nothing below ~10), and the
   picker judges compatibility against the KREA graph, so a Klein LoRA is badged
   incompatible here instead of compatible. */
function KreaLorasCard({ config, setField }) {
  const presets = Array.isArray(config.krea?.generation_lora_presets)
    ? config.krea.generation_lora_presets : []
  const save = (next) => setField('krea', 'generation_lora_presets', next)
  // ONE scan per card, judged for Krea. Degrades to free text — see the hook.
  const loraScan = useKleinGenerationLoras('krea')
  return (
    <Card
      id="krea-generation-lora-presets"
      title="Krea 2 Edit generation LoRA presets (optional)"
      help={`Named combinations of your own LoRA files, chained after the identity-edit LoRA when Krea 2 Edit generates dataset images — inside a preset the order is the chain order (max ${MAX_GENERATION_LORAS} LoRAs each, ${MAX_GENERATION_LORA_PRESETS} presets). Pick each row from the LoRAs found under ComfyUI's models/loras; Krea-compatible ones are listed first, and a LoRA of another architecture is badged because ComfyUI would load it as a silent no-op here. Strength goes to 6, or to 20 for utility LoRAs whose filename says filter-bypass — those have no effect below ~10. Per run, pick a preset in the workspace's Krea 2 Edit tuning panel — it opens on the default preset chosen below ("None" until you choose one), and picking something else there applies to that run only. Only the model side is patched, so a LoRA's text-encoder weights are ignored. Preset mechanism by @waltm (Discord).`}
    >
      {presets.length === 0 && (
        <p className="text-sm text-content-muted">No presets yet — create your first combination below.</p>
      )}
      {presets.map((preset, i) => (
        <LoraPresetCard key={i} preset={preset} index={i} presets={presets} save={save}
          loraScan={loraScan} engineLabel="Krea 2"
          strengthRange={kreaStrengthRange} defaultStrength={KREA_LORA_STRENGTH_DEFAULT}
          placeholder="krea/my-lora.safetensors"
          engineId="krea" fixedLora={config.krea?.identity_lora || ''} />
      ))}
      <div className="flex items-center gap-3">
        <button
          type="button" className={TEXT_BTN}
          onClick={() => save([...presets, { name: freeName(presets, 'My preset'), loras: [] }])}
          disabled={presets.length >= MAX_GENERATION_LORA_PRESETS}
        >
          ＋ New preset
        </button>
        <span className="text-xs text-content-muted">{presets.length}/{MAX_GENERATION_LORA_PRESETS}</span>
      </div>
      <DefaultPresetField
        id="krea-default-lora-preset" engineLabel="Krea 2 Edit" presets={presets}
        value={config.krea?.default_generation_lora_preset || ''}
        onChange={(v) => setField('krea', 'default_generation_lora_preset', v)} />
    </Card>
  )
}

/* Editable identity / quality prompts (feature request by @bbsorry / 雨田壹).
   The identity "locks" that ride ahead of every generated variation used to be
   hardcoded and invisible; here each is an override shown in ONE editable box
   that already holds the shipped default text, with a Reset — one set PER
   SUBJECT TYPE, picked with the chips at the top of the card.

   The two-box era is over: the field used to be an empty textarea next to a
   read-only copy of the shipped text and a button that pasted it in. One box is
   clearer, but it must not turn "I looked at the default" into a persisted COPY
   of it — that would freeze the prompt for that user and hide every future
   improvement. PromptOverrideField normalises the text back to '' whenever it
   equals the shipped default, so blank-means-default (the backend contract in
   face_variations.get_identity_prompt) still holds.

   The Klein-improve prompt additionally has an on/off toggle: off applies NO
   prompt to the manual "Klein upscale & improve".
   Field metadata (keys mirroring config identity_prompts.*, never renamed) lives
   in common/promptOverride.js, shared with the workspace's Extra-refs modal. */

// Bounds mirror the server-side clamps in face_dataset_service._improve_float /
// _improve_int — the UI should not offer a value the backend will silently pull back.
// The `fallback` numbers this list used to carry (2 / 0 / 0 / 4) are gone: they
// were a hand-kept copy of config.DEFAULTS['klein'], and one of them (0 for the
// consistency strength) had ALREADY drifted from the backend's 1.0. Both the
// displayed value and "Reset to default" now read the server's `config_defaults`.


function IdentityPromptsCard({ config, setField, promptDefaults, promptDefaultsBySubject,
                               setIdentityPrompts }) {
  const ip = config.identity_prompts || {}
  // Subject type being edited. This screen has NO dataset context, so without an
  // explicit picker it edited "the" identity prompt — which is exactly how an
  // animal-tuned lock ended up on human generations (ashish.sinha, Discord).
  // Human first: it is the default subject and the one the flat legacy keys hold.
  const [subject, setSubject] = useState('human')
  const defaults = (promptDefaultsBySubject || {})[subject] || promptDefaults || {}
  const set = (key, v) => setField('identity_prompts', key, v)
  const setPrompt = (key, v) => setIdentityPrompts((prev) => writeIdentityPrompt(prev, subject, key, v))
  return (
    <Card
      id="identity-prompts"
      title="Identity, Klein & Krea 2 prompts (advanced)"
      help="The hidden prompts that lock a subject's identity across generated variations, now editable. Pick the subject type first: each type (Human, Animal, Creature, Object, Other, Anime) has its OWN set, and a text you write for one never applies to another. Each box already holds the prompt in use: edit it to override, Reset to go back. Reproducibility note: as long as a box still matches the built-in text, nothing is stored and generation stays byte-identical to before — you also keep receiving improvements to that prompt. Feature request by @bbsorry (雨田壹); per-subject scoping reported by ashish.sinha."
    >
      {/* flex-wrap: five chips fit one row on a laptop and wrap to two or three
          on a phone — never a row that overflows the card. */}
      <div>
        <span className="block text-sm font-medium text-content">Subject type</span>
        <p className="mt-1 mb-2 text-xs text-content-muted">
          Which datasets these three prompts apply to. Each subject type keeps its own texts —
          editing the Animal ones leaves your Human datasets untouched. A dot marks a type you
          have already customised.
        </p>
        <div role="group" aria-label="Subject type to edit" className="flex flex-wrap gap-1.5">
          {PROMPT_SUBJECT_TYPES.map((st) => {
            const on = st === subject
            return (
              <button
                key={st}
                type="button"
                aria-pressed={on}
                onClick={() => setSubject(st)}
                className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs ${
                  on ? 'border-indigo-400/60 bg-indigo-500/15 text-indigo-200 font-semibold'
                     : 'border-border bg-surface text-content-muted hover:text-content'}`}
              >
                {SUBJECT_TYPE_LABELS[st]}
                {subjectHasOverride(ip, st) && (
                  <span aria-label="customised" title="Customised" className="h-1.5 w-1.5 rounded-full bg-amber-400" />
                )}
              </button>
            )
          })}
        </div>
      </div>

      {identityPromptFields(subject).map((f) => (
        <PromptOverrideField
          key={`${subject}-${f.key}`}
          id={f.id}
          label={f.label}
          desc={f.desc}
          value={readIdentityPrompt(ip, subject, f.key)}
          defaultText={defaults[f.key]}
          onChange={(v) => setPrompt(f.key, v)}
        />
      ))}

      {/* The identity locks were one of SIX sources the prompt is built from.
          The other five shipped hardcoded and invisible; they are edited here,
          split the same way the storage is — per subject above the line, global
          below it. The composed preview closes the card, because the whole point
          of these boxes is to change a part and see the whole move. */}
      <div id="prompt-part-render-tail" className="border-t border-border pt-4">
        <h4 className="text-sm font-medium text-content">
          Klein &amp; Krea — the rest of the prompt ({SUBJECT_TYPE_LABELS[subject]})
        </h4>
        <p className="mt-1 mb-3 text-xs text-content-muted">
          These follow the subject type selected above, like the identity locks: the tail asks
          an Anime dataset for a drawing and every other type for a photograph.
        </p>
        {SUBJECT_PROMPT_PART_FIELDS.map((f) => (
          <PromptOverrideField
            key={`${subject}-${f.key}`}
            id={f.id}
            label={f.label}
            desc={f.desc}
            warn={f.warn}
            rows={f.rows}
            value={readIdentityPrompt(ip, subject, f.key)}
            defaultText={defaults[f.key]}
            onChange={(v) => setPrompt(f.key, v)}
            className="mt-3"
          />
        ))}
      </div>

      <div id="prompt-part-framing" className="border-t border-border pt-4">
        <h4 className="text-sm font-medium text-content">
          Shot detail per framing ({SUBJECT_TYPE_LABELS[subject]})
        </h4>
        <p className="mt-1 mb-1 text-xs text-content-muted">
          Klein and Krea under-fill a short tag prompt and invent the rest, so each shot carries
          a concrete description of what the framing should look like. This is where the lens
          talk (&ldquo;85mm portrait lens look&rdquo;) lives.
        </p>
        {/* Four boxes: two columns on a laptop, stacked on a phone. */}
        <div className="grid gap-3 sm:grid-cols-2">
          {FRAMING_PROMPT_PART_FIELDS.map((f) => (
            <PromptOverrideField
              key={`${subject}-${f.key}`}
              id={f.id}
              label={f.label}
              rows={f.rows}
              value={readIdentityPrompt(ip, subject, f.key)}
              defaultText={defaults[f.key]}
              onChange={(v) => setPrompt(f.key, v)}
              className="mt-2"
            />
          ))}
        </div>
      </div>

      <div id="prompt-part-global" className="border-t border-border pt-4">
        <h4 className="text-sm font-medium text-content">Applied to every subject type</h4>
        <p className="mt-1 mb-1 text-xs text-content-muted">
          These four are <strong>not</strong> per subject type: the two directives are only ever
          injected into human shots, and the skin hold is one sentence about not inventing
          detail. Editing them here changes them everywhere.
        </p>
        {GLOBAL_PROMPT_PART_FIELDS.map((f) => (
          <PromptOverrideField
            key={f.key}
            id={f.id}
            label={f.label}
            desc={f.desc}
            warn={f.warn}
            rows={f.rows}
            value={ip[f.key]}
            defaultText={defaults[f.key]}
            onChange={(v) => set(f.key, v)}
            className="mt-3"
          />
        ))}
      </div>

      <PromptPreview subject={subject} identityPrompts={ip} />


    </Card>
  )
}

/* The API engines' cards — their keys, their models, their subscription
   lane — moved to their plugin, which contributes them as a settings group of
   its own (the `settings.group` slot). What stays here is the core's: which
   engines are on and which one opens preselected, reading the catalog the
   plugins fill. */

/* The section is organised as a clickable SUMMARY plus collapsible groups —
   eleven flat cards had grown into a wall where API keys sat next to Klein
   pins next to the improve prompt, and finding anything meant scrolling
   (reported from a tablet, mid preset editing). Which cards live in which
   group is data (settingsGroups.ENGINES_GROUPS), the shells are shared
   (SettingsGroupsView.jsx — NOT settingsGroups.jsx with a capital: a name
   differing only by case resolves to the wrong file on a Windows checkout),
   and deep-links keep working untouched: each group is
   a native <details>, which the ?focus= reveal already knows how to open. */
export default function EnginesSection(props) {
  const { config, setField, toggleEngine, caps, configDefaults } = props
  const [group1, group2, group3, group4, group6] = ENGINES_GROUPS
  const groupProps = useSettingsGroupProps('engines')
  // The global default selects a run engine; each plugin owns its enabled toggles.
  const engineOptions = engineSettingsOptions()
  const coreEngineIds = new Set(CORE_ENGINE_CATALOG.map(engine => engine.id))
  return (
    <div className="space-y-4">
      <SettingsGroupsToc sectionId="engines" groups={ENGINES_GROUPS} />

      <SettingsGroup {...groupProps(group1)}>
      <Card title="Engines" help="Which engines appear in the generate panel, and which one is preselected. An engine a plugin brings is listed while that plugin is on.">
        <div>
          <label htmlFor="engine-default" className="block text-sm font-medium text-content">Default engine</label>
          <select
            id="engine-default"
            value={config.engines.default}
            onChange={(e) => setField('engines', 'default', e.target.value)}
            className={INPUT_CLASS}
          >
            {engineOptions.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
          </select>
          <ResetToDefault label="Default engine" section="engines" field="default"
            config={config} configDefaults={configDefaults} setField={setField} />
        </div>

        <fieldset id="engines-enabled" className="scroll-mt-24">
          <legend className="mb-1 block text-sm font-medium text-content">Enabled local engines</legend>
          <div className="flex flex-col gap-2">
            {engineOptions.filter(o => coreEngineIds.has(o.id)).map((o) => (
              <label key={o.id} htmlFor={`engine-enabled-${o.id}`} className="flex items-center gap-2 text-sm text-content">
                <input
                  id={`engine-enabled-${o.id}`}
                  type="checkbox"
                  checked={(config.engines.enabled || []).includes(o.id)}
                  onChange={() => toggleEngine(o.id)}
                  className="h-4 w-4 rounded border-border-strong"
                />
                {o.label}
              </label>
            ))}
          </div>
          {/* The only LIST with a reset. Ticking the boxes back one by one means
              knowing which five shipped enabled — and the catalog grows with
              releases, so that knowledge goes stale. Order is not compared: a
              re-ticked selection is the same selection. */}
          <button type="button" className="min-h-10 text-xs text-primary underline"
            onClick={() => setField('engines', 'enabled', resetEngineSelection(config.engines.enabled, configDefaults.engines?.enabled, [...coreEngineIds]))}>Reset local engines</button>
        </fieldset>
      </Card>
      </SettingsGroup>

      <SettingsGroup {...groupProps(group2)}>
      <KleinModelFilesCard config={config} setField={setField} caps={caps} />

      <KleinGenerationCard config={config} setField={setField} configDefaults={configDefaults} />
      </SettingsGroup>

      <SettingsGroup {...groupProps(group3)}>
      <KreaCard config={config} setField={setField} configDefaults={configDefaults} caps={caps} />

      <KreaHiresCard config={config} setField={setField} configDefaults={configDefaults} />
      </SettingsGroup>

      {/* The two preset lists live TOGETHER, not each under its engine: the
          activity is one ("my named LoRA chains"), and it is the block the
          scattered-options report came from. Each card still names its
          engine — the lists stay independent, one name can mean two chains. */}
      <SettingsGroup {...groupProps(group4)}>
      <KleinLorasCard config={config} setField={setField} />

      <KreaLorasCard config={config} setField={setField} />
      </SettingsGroup>


      <SettingsGroup {...groupProps(group6)}>
      <IdentityPromptsCard config={config} setField={setField} promptDefaults={props.promptDefaults}
        promptDefaultsBySubject={props.promptDefaultsBySubject}
        setIdentityPrompts={props.setIdentityPrompts} configDefaults={configDefaults} />
      </SettingsGroup>
    </div>
  )
}
