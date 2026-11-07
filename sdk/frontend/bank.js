import { runtime } from './runtime.js'
// Shared host interaction and presentation contract, version 1.5.
// Extracted from LDS under PolyForm-Noncommercial-1.0.0.

export function formatEtaSeconds(seconds) {
  // `Number(null)` is 0, and 0 renders as "under a minute" — which would put a
  // duration on every pass that publishes none.
  if (seconds === null || seconds === undefined || seconds === '') return null;
  const s = Number(seconds);
  if (!Number.isFinite(s) || s < 0) return null;
  if (s < 45) return 'under a minute';
  if (s < 90) return 'about a minute';
  const minutes = s / 60;
  if (minutes < 10) return `about ${Math.max(2, Math.round(minutes))} minutes`;
  if (minutes < 45) return `about ${Math.round(minutes / 5) * 5} minutes`;
  const hours = s / 3600;
  if (hours < 4) {
    // Half-hour buckets are as fine as this deserves to get. Below four hours
    // the half still carries information ("2 hours 30" is a different plan from
    // "2 hours"); above it, it is noise.
    const half = Math.round(hours * 2) / 2;
    if (half === 1) return 'about an hour';
    const whole = Math.floor(half);
    const unit = whole === 1 ? 'hour' : 'hours';
    return half === whole
      ? `about ${whole} ${unit}`
      : `about ${whole} ${unit} 30 minutes`;
  }
  if (hours < 24) return `about ${Math.round(hours)} hours`;
  return 'more than a day';
}

export function etaPhrase(activity) {
  if (!activity || activity.finished || activity.error || activity.cancelled) return '';
  const state = activity.eta_state;
  if (state === 'ready') {
    const text = formatEtaSeconds(activity.eta_seconds);
    if (!text) return '';
    return activity.eta_scope === 'phase' ? `${text} left in this step` : `${text} left`;
  }
  if (state === 'estimating') return 'estimating time left…';
  return '';
}

export function BankLaneTabs(props) {
  const host = runtime()
  return host.React.createElement(host.ui.BankLaneTabs, props)
}
export function loadRailOpen(...args) { return runtime().bank.loadRailOpen(...args) }
export function saveRailOpen(...args) { return runtime().bank.saveRailOpen(...args) }
export function railIsColumn(...args) { return runtime().bank.railIsColumn(...args) }
export function passesButtonLabel(...args) { return runtime().bank.passesButtonLabel(...args) }
export function laneTabClass(...args) { return runtime().bank.laneTabClass(...args) }
