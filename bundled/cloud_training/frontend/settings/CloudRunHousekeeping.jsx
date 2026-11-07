import { useState } from 'react'
import { apiFetch, postJson } from '@lds/plugin-sdk';
import { Card } from '@lds/plugin-sdk/ui';
import { formatSize } from '@lds/plugin-sdk/data';

/* The cleanup that used to destroy weights, and the folders it used to ignore.
   Both live here rather than on the Runs hub: this is the disk tab. */
export default function CloudRunHousekeeping({ toast, onChanged }) {
  const [orphans, setOrphans] = useState(null)
  const [busy, setBusy] = useState('')

  const scan = async () => {
    setBusy('scan')
    try {
      setOrphans((await apiFetch('/api/dataset/train/cloud/orphans')).orphans || [])
    } catch (e) {
      toast?.error(e.message || 'Could not scan the run folders.')
    } finally {
      setBusy('')
    }
  }

  const purge = async () => {
    const total = (orphans || []).reduce((n, o) => n + (o.size_bytes || 0), 0)
    const withCkpt = (orphans || []).filter((o) => o.checkpoints > 0).length
    if (!window.confirm(
      `Move ${orphans.length} unclaimed run folder(s) (${formatSize(total)}) to the trash?\n\n`
      + (withCkpt ? `${withCkpt} of them still hold a checkpoint — those are moved into the checkpoint store first, never deleted.\n\n` : '')
      + 'Files go to the trash on this same disk; the space comes back when you empty it.',
    )) return
    setBusy('purge')
    try {
      const res = await postJson('/api/dataset/train/cloud/purge-orphans', {})
      toast?.success(`${res.purged_dirs} folder(s) moved to the trash`
        + (res.rescued_checkpoints ? `, ${res.rescued_checkpoints} checkpoint(s) rescued` : '')
        + '.')
      await scan()
      onChanged?.()
    } catch (e) {
      toast?.error(e.message || 'Could not clean those folders.')
    } finally {
      setBusy('')
    }
  }

  const adopt = async () => {
    setBusy('adopt')
    try {
      const res = await postJson('/api/storage/adopt-checkpoints', {})
      toast?.success(res.moved
        ? `${res.moved} checkpoint(s) moved out of the run folders and into the store.`
        : 'Every checkpoint is already in the store.')
      onChanged?.()
    } catch (e) {
      toast?.error(e.message || 'Could not move the checkpoints.')
    } finally {
      setBusy('')
    }
  }

  return (
    <Card title="Cloud run housekeeping"
      help="Cleaning a finished run trashes its dataset copy, its sample images and its logs — never a checkpoint. Everything goes to the trash on the same disk, so the space only comes back when you empty it.">
      <div className="flex flex-wrap items-center gap-2">
        <button id="storage-scan-orphans" type="button" onClick={scan} disabled={!!busy}
          className="rounded-md border border-border-strong px-3 py-1.5 text-sm font-medium text-content hover:bg-surface-raised disabled:opacity-50">
          {busy === 'scan' ? 'Scanning…' : 'Find unclaimed run folders'}
        </button>
        <button id="storage-adopt-checkpoints" type="button" onClick={adopt} disabled={!!busy}
          className="rounded-md border border-border px-3 py-1.5 text-sm font-medium text-content hover:bg-surface-raised disabled:opacity-50">
          {busy === 'adopt' ? 'Moving…' : 'Move stray checkpoints into the store'}
        </button>
      </div>
      {orphans && orphans.length === 0 && (
        <p className="text-xs text-content-muted">
          Every run folder on disk belongs to a run this app knows about.
        </p>
      )}
      {orphans && orphans.length > 0 && (
        <div className="space-y-2">
          <p className="text-sm text-content">
            {orphans.length} folder(s) no run points at —{' '}
            <span className="font-semibold tabular-nums">
              {formatSize(orphans.reduce((n, o) => n + (o.size_bytes || 0), 0))}
            </span>.
          </p>
          <ul className="space-y-1 text-xs text-content-subtle">
            {orphans.map((o) => (
              <li key={o.name} className="break-all">
                {o.name} — {formatSize(o.size_bytes)}
                {o.checkpoints > 0 && (
                  <span className="text-amber-300">
                    {' '}· holds {o.checkpoints} checkpoint(s), which will be rescued
                  </span>
                )}
              </li>
            ))}
          </ul>
          <button type="button" onClick={purge} disabled={!!busy}
            className="rounded-md border border-red-500/40 bg-red-500/10 px-3 py-1.5 text-sm font-medium text-red-300 disabled:opacity-40">
            {busy === 'purge' ? 'Cleaning…' : 'Move them to the trash'}
          </button>
        </div>
      )}
    </Card>
  )
}
