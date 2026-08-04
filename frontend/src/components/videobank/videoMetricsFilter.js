/** 🎬 Quality flags in the grid — pure helpers (no JSX, so `node --test` runs them).
 *
 * The backend stores RAW scores and derives flags at read time against the cuts
 * in force, so everything here is presentation: counting, filtering, describing.
 * Two decisions worth stating:
 *
 * "Unmeasured" is a state of its own, never "clean". A clip with no flags
 * because nothing was measured and a clip with no flags because it is fine are
 * different facts — collapsing them makes a half-scanned bank look healthy.
 *
 * And the dry-run sentence changes TONE when a cut would flag most of the bank.
 * The failure mode is documented: a public pipeline once kept 47 clips out of
 * 1493 with one mis-set threshold and discovered it after the fact. A preview
 * that reports "400 clips flagged" in the same cheerful voice as "4 clips
 * flagged" does not prevent that.
 */

export const FLAG_LABELS = {
  still: 'Barely moves',
  agitated: 'Too much motion',
  black: 'Black moment',
  freeze: 'Frozen stretch',
  soft: 'No sharp frames',
  unmeasured: 'Not measured yet',
}

/** {flagName: count, flagged: N, unmeasured: N}. `flagged` counts CLIPS, so a
 * clip carrying two flags is one clip — the same rule as the backend dry run,
 * and for the same reason: the total must not overstate the damage. */
export function flagCounts(clips) {
  const counts = { flagged: 0, unmeasured: 0 }
  for (const clip of clips) {
    if (!clip.metrics) {
      counts.unmeasured += 1
      continue
    }
    const flags = clip.flags || []
    if (flags.length) counts.flagged += 1
    for (const f of flags) counts[f] = (counts[f] || 0) + 1
  }
  return counts
}

/** The clips a flag chip selects. `'unmeasured'` is a pseudo-flag over the
 * metrics field; null/undefined means no filter. */
export function filterByFlag(clips, flag) {
  if (!flag) return clips
  if (flag === 'unmeasured') return clips.filter((c) => !c.metrics)
  return clips.filter((c) => (c.flags || []).includes(flag))
}

/** The threshold panel renders from this table. A cut the backend supports but
 * this table omits would be configurable only by hand-editing config.json —
 * invisibly — so the table IS the panel's contract, and a test pins the keys
 * against the backend's. `direction` says which side of the value gets flagged,
 * because "0.001" alone does not tell a user whether raising it is stricter. */
export function thresholdFields() {
  return [
    { key: 'motion_floor', flag: 'still', direction: 'below',
      label: 'Motion floor',
      hint: 'Flags clips whose average motion falls below this.' },
    { key: 'motion_ceiling', flag: 'agitated', direction: 'above',
      label: 'Motion ceiling',
      hint: 'Flags clips whose busiest moments exceed this.' },
    { key: 'luma_floor', flag: 'black', direction: 'below',
      label: 'Darkest moment',
      hint: 'Flags clips whose darkest frame falls below this brightness.' },
    { key: 'freeze_max', flag: 'freeze', direction: 'above',
      label: 'Frozen share',
      hint: 'Flags clips where more than this share of frames do not move.' },
    { key: 'sharpness_floor', flag: 'soft', direction: 'below',
      label: 'Sharpness floor',
      hint: 'Flags clips whose sharpest stretch stays below this.' },
  ]
}

/** One sentence for the dry-run result. Real numbers, per-rule detail, and a
 * warning tone once the cut would take most of the bank. */
export function cutSummary(dryRun, totalClips) {
  const flagged = dryRun?.total_flagged || 0
  if (!flagged) return 'These cuts would remove nothing — no clips flagged.'
  const parts = Object.entries(dryRun)
    .filter(([k, v]) => k !== 'total_flagged' && v > 0)
    .map(([k, v]) => `${k}: ${v}`)
    .join(', ')
  const head = `${flagged} of ${totalClips} clips would be flagged (${parts}).`
  if (flagged > totalClips / 2) {
    return `⚠ ${head} That is most of the bank — check the thresholds before applying.`
  }
  return head
}
