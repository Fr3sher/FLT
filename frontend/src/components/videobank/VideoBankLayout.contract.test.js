/**
 * Video Bank shares Image Bank's Encre shell; this contract prevents visual drift. On 2026-09-01,
 * the maintainer reported that video felt like a separate app with different UI and methods. It
 * had no shared-atom imports, an older vertical stack and custom chips. Mirror
 * BankOverviewLayout.contract.test.js: the SAME decision module, atoms and shell literals across
 * two intentionally separate component trees, with ONE visual form.
 */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const read = (name) => readFileSync(new URL(`../../../../bundled/video/frontend/videobank/${name}`, import.meta.url), 'utf8')
const workspace = read('VideoBankWorkspace.jsx')
const rail = read('VideoFilterRail.jsx')
const passes = read('VideoPassesPanel.jsx')

test('the video lane decides its layout with bankLayout.js, never a copy of it', () => {
  // One decision module for both lanes: when the rail is a column, what the
  // preference key is, what the ⚙ button says. A videobank-local fork of any
  // of these is the drift this contract exists to refuse.
  assert.match(workspace, /from '@lds\/plugin-sdk\/bank'/)
  assert.match(workspace, /loadRailOpen|railIsColumn/)
  assert.doesNotMatch(workspace, /RAIL_SIDE_BY_SIDE|const railIsColumn =/)
})

test('the shell is the image lane’s: rail beside the grid, drawer below', () => {
  assert.match(workspace, /lg:grid-cols-\[17rem_minmax\(0,1fr\)\]/)
  assert.match(workspace, /railOpen && railIsColumnNow/)
  // The drawer really covers the grid instead of squeezing it…
  assert.match(workspace, /railOpen && !railIsColumnNow/)
  // …and as a column the rail is pinned, or it scrolls away after one screen.
  assert.match(workspace, /lg:sticky/)
})

test('the shared atoms dress every surface — no hand-rolled twins', () => {
  assert.match(workspace, /\{ Stat \} from '@lds\/plugin-sdk\/ui'/)
  assert.match(rail, /\{ Chip, FilterGroup, GroupLabel \} from '@lds\/plugin-sdk\/ui'/)
  assert.match(passes, /\{ GroupLabel, PassButton \} from '@lds\/plugin-sdk\/ui'/)
  // The drawer is a sheet of glass over the grid, not an opaque card — the
  // exact pin the image rail carries, for the exact same reason.
  assert.match(rail, /bg-surface-overlay/)
})

test('the passes are a panel on demand, and the probe can see all of it', () => {
  assert.match(workspace, /id="video-passes-panel"/)
  assert.match(workspace, /data-probe-reading/)
  assert.match(workspace, /aria-controls="video-passes-panel"/)
  assert.match(workspace, /id="video-filter-rail"/)
  assert.match(workspace, /aria-controls="video-filter-rail"/)
  assert.match(workspace, /data-probe-chrome="header"/)
  // The rail names itself to the probe in both of its lives.
  assert.match(rail, /data-probe-panel="rail"/)
})

test('what left the workspace arrived somewhere a user can still reach', () => {
  // The refactor moved surfaces, it must not lose them: every pass button, the
  // search box, the thresholds, the files list and the shot-cut dial live on.
  for (const [file, needle] of [
    [passes, /'probe', 'detect', 'thumbs', 'measure', 'embed'/],
    [passes, /VideoShotCutsPanel/],
    [rail, /VideoClipSearchBox/],
    [rail, /VideoThresholdsPanel/],
    [rail, /VideoSourceList/],
    [workspace, /PASS_LABELS\.pipeline/],
    [workspace, /PASS_LABELS\.promote/],
  ]) {
    assert.match(file, needle)
  }
})
