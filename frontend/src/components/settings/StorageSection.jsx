import { useCallback, useEffect, useState } from 'react'
import { apiFetch, postJson } from '../../api/fetchClient'
import { Card } from './primitives'
import { SettingsGroup, SettingsGroupsToc, useSettingsGroupProps } from './SettingsGroupsView'
import { STORAGE_GROUPS } from './settingsGroups'
import { LocationEditor } from '../shared/LocationEditor.jsx'
import {
  formatSize, locationRows,
} from './storageLocations.js'

/* Settings › Storage — everything that answers "where does this live and how
   much of my disk does it take".

   It exists because those answers were scattered: the trash was in Maintenance,
   the Hugging Face allowance in Training, the dataset root in a card called
   "Data", and the two directories that actually fill a drive — the cloud run
   staging and the checkpoints — were hard-coded and invisible. When C: fills up,
   "put it on the other drive" was a config.json edit and a manual copy.

   Two rules run through the whole tab:
     - sizes are measured on demand, never on mount (walking a 127 GB tree is not
       something a tab is allowed to do while you are reading it);
     - a location change never moves files by itself. You choose. */

/* One relocatable root. Type a path, check it, then pick what happens to the
   files already there — the two answers are spelled out before anything runs. */
function TrashCard({ reloadKey }) {
  const [size, setSize] = useState(null)
  const [busy, setBusy] = useState(false)
  const [opening, setOpening] = useState(false)
  useEffect(() => {
    let alive = true
    apiFetch('/api/trash')
      .then((d) => { if (alive) setSize(d?.size_bytes ?? null) })
      .catch(() => { /* best-effort */ })
    return () => { alive = false }
  }, [reloadKey])
  const openFolder = async () => {
    setOpening(true)
    try {
      const d = await postJson('/api/trash/open', {})
      if (!d?.ok) window.alert(d?.error || 'Could not open the trash folder.')
    } catch {
      window.alert('Could not open the trash folder.')
    } finally {
      setOpening(false)
    }
  }
  const empty = async () => {
    if (!window.confirm('Permanently delete everything in the trash?\n\nThis is the ONLY destructive action — deleted checkpoints cannot be recovered afterwards.')) return
    setBusy(true)
    try {
      const d = await postJson('/api/trash/empty', {})
      if (d?.ok) setSize(0)
    } finally {
      setBusy(false)
    }
  }
  return (
    <Card title="Trash" help="Everything the app deletes (checkpoints, cloud staging, deployed LoRAs) is moved here first — emptying it is the only action that actually destroys files. It sits on the same disk, so cleaning does not give space back until you empty it.">
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-sm text-content">
          <span aria-hidden>🗑</span> Trash size:{' '}
          <span className="font-semibold tabular-nums">{size == null ? '…' : formatSize(size)}</span>
        </span>
        <button type="button" onClick={openFolder} disabled={opening}
          title="Open the trash folder in the file explorer"
          className="rounded-md border border-border bg-surface-raised px-3 py-1.5 text-sm font-medium text-content disabled:opacity-40">
          {opening ? 'Opening…' : '📂 Open folder'}
        </button>
        <button type="button" onClick={empty} disabled={busy || !size}
          className="rounded-md border border-red-500/40 bg-red-500/10 px-3 py-1.5 text-sm font-medium text-red-300 disabled:opacity-40">
          {busy ? 'Emptying…' : 'Empty trash'}
        </button>
      </div>
    </Card>
  )
}

/* The run image archive: a deduplicated copy of every image a training run was
   launched on, so a comparison can still SHOW an image that has since been
   deleted from its dataset. Content-addressed, so an unchanged dataset costs
   nothing on its second launch — but it is still bytes, so its size is visible
   and clearable here rather than growing invisibly. */
function RunArchiveCard() {
  const [info, setInfo] = useState(null)
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    let alive = true
    apiFetch('/api/run-archive')
      .then((d) => { if (alive) setInfo(d || null) })
      .catch(() => { /* best-effort */ })
    return () => { alive = false }
  }, [])
  const clear = async () => {
    if (!window.confirm('Delete every archived training image?\n\nYour runs, their settings and their captions are kept — you just lose the ability to look at images that have since been deleted from their dataset.')) return
    setBusy(true)
    try {
      const d = await postJson('/api/run-archive/clear', {})
      if (d?.ok) setInfo((v) => ({ ...(v || {}), size_bytes: 0 }))
    } finally {
      setBusy(false)
    }
  }
  return (
    <Card title="Run image archive" help="When a training run is launched, a deduplicated copy of the images it trains on is kept so that comparing two runs can still show an image you have since deleted. Only new or edited images are copied, and the archive stops growing at its ceiling.">
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-sm text-content">
          <span aria-hidden>🗂</span> Archive size:{' '}
          <span className="font-semibold tabular-nums">
            {info == null ? '…' : formatSize(info.size_bytes || 0)}
          </span>
          {info?.max_bytes ? (
            <span className="text-content-subtle"> / {formatSize(info.max_bytes)} ceiling</span>
          ) : null}
        </span>
        {info && !info.enabled && (
          <span className="text-xs text-content-subtle">Archiving is turned off.</span>
        )}
        <button type="button" onClick={clear} disabled={busy || !info?.size_bytes}
          className="rounded-md border border-red-500/40 bg-red-500/10 px-3 py-1.5 text-sm font-medium text-red-300 disabled:opacity-40">
          {busy ? 'Clearing…' : 'Clear archive'}
        </button>
      </div>
    </Card>
  )
}

export default function StorageSection({
  config, setField, configDefaults, saveConfigPatch, toast,
}) {
  const [locations, setLocations] = useState([])
  const [sizes, setSizes] = useState({})
  const [measuring, setMeasuring] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)

  const loadLocations = useCallback(async () => {
    try {
      setLocations((await apiFetch('/api/storage/locations')).locations || [])
    } catch { /* the editors below still work off the config */ }
  }, [])
  useEffect(() => { loadLocations() }, [loadLocations, reloadKey])

  const measure = async () => {
    setMeasuring(true)
    try {
      setSizes((await apiFetch('/api/storage/sizes')).sizes || {})
    } catch (e) {
      toast?.error(e.message || 'Could not measure the folders.')
    } finally {
      setMeasuring(false)
    }
  }

  const rows = locationRows(locations, sizes)
  const byKey = Object.fromEntries(rows.map((r) => [r.key, r]))
  const changed = () => { setReloadKey((k) => k + 1); setSizes({}) }
  // Shared props of the three relocatable roots. The DOM `id` stays a LITERAL on
  // each element below (the help registry's focus targets are matched against
  // the JSX source, and a computed id is invisible to it).
  const shared = (key) => ({
    current: byKey[key]?.path,
    sizeBytes: byKey[key]?.sizeBytes,
    config, setField, configDefaults, saveConfigPatch, toast, onChanged: changed,
  })

  // Summary + collapsible groups — same shells as Image engines; deep-links
  // and search open a collapsed group on their own.
  const [overviewGroup, locationsGroup, housekeepingGroup] = STORAGE_GROUPS
  const groupProps = useSettingsGroupProps('storage')
  const groups = STORAGE_GROUPS.filter(group => group.id !== 'models')
  return (
    <div className="space-y-4">
      <SettingsGroupsToc sectionId="storage" groups={groups} />

      <SettingsGroup {...groupProps(overviewGroup)}>
      <Card title="What lives where"
        help="Every folder this app writes to, with the drive it sits on. Sizes are measured only when you ask — walking a hundred gigabytes of datasets is not something a page should do while you read it.">
        <div className="flex flex-wrap items-center gap-3">
          <button id="storage-measure" type="button" onClick={measure} disabled={measuring}
            className="rounded-md border border-border-strong px-3 py-1.5 text-sm font-medium text-content hover:bg-surface-raised disabled:opacity-50">
            {measuring ? 'Measuring…' : '📏 Measure everything'}
          </button>
          <span className="text-xs text-content-subtle">
            {Object.keys(sizes).length ? 'Measured just now.' : 'Not measured yet.'}
          </span>
        </div>
        {/* The table scrolls inside its own box: a long Windows path must never
            make the whole page scroll sideways on a phone. */}
        <div className="-mx-2 overflow-x-auto px-2">
          <ul className="min-w-[18rem] space-y-2">
            {rows.map((row) => (
              <li key={row.key} className="rounded-lg border border-border bg-surface-raised p-3">
                <div className="flex flex-col gap-1 sm:flex-row sm:items-baseline sm:justify-between">
                  <p className="text-sm font-medium text-content">
                    {row.label}
                    {row.relocatable && (
                      <span className="ml-2 rounded border border-border px-1 text-[0.625rem] uppercase tracking-wide text-content-subtle">
                        movable
                      </span>
                    )}
                  </p>
                  <p className="shrink-0 text-sm tabular-nums text-content">{row.sizeLabel}</p>
                </div>
                <p className="mt-0.5 break-all text-xs text-content-subtle">
                  {row.path || 'not configured'}{row.exists ? '' : ' (not created yet)'}
                </p>
                <p className="mt-0.5 text-xs text-content-muted">{row.holds}</p>
                {row.volumeLabel && (
                  <p className="mt-0.5 text-[0.6875rem] text-content-subtle">{row.volumeLabel}</p>
                )}
              </li>
            ))}
          </ul>
        </div>
      </Card>

      </SettingsGroup>

      <SettingsGroup {...groupProps(locationsGroup)}>
      <LocationEditor id="dataset-images-root" storageKey="datasets"
        label="Dataset images root" section="paths" field="dataset_images_root"
        help="Where dataset images live on disk — usually the biggest folder of all."
        {...shared('datasets')} />


      <LocationEditor id="checkpoints-dir" storageKey="checkpoints"
        label="Checkpoint store" section="paths" field="checkpoints_dir"
        help="Where completed training checkpoints are kept for good. No cleanup in the app ever removes a file from here — only you can, from the Checkpoints panel or by emptying the trash."
        {...shared('checkpoints')} />

      </SettingsGroup>

      <SettingsGroup {...groupProps(housekeepingGroup)}>
      <TrashCard reloadKey={reloadKey} />
      <RunArchiveCard />
      </SettingsGroup>

    </div>
  )
}
