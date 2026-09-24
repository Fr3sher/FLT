/**
 * Show the blend sweep's combinations, images and estimated minutes BEFORE launch. No hard cap by
 * design, matching server build_matrix: the queue is serial and users see count and duration
 * first. A weight sweep follows the same rule as strength sweeps. Above BLEND_WARN_CELLS, show
 * amber figures rather than forbid the run on the user's machine.
 */
import { blendSweepCost } from './loraStack';

export default function BlendSweepSummary({ configCount, count = 1, batchMult = 1,
  secondsPerImage = null }) {
  const cost = blendSweepCost({ configCount, count, batchMult, secondsPerImage });
  if (cost.configs <= 1) return null;   // A single configuration needs no announcement.

  return (
    <p data-testid="blend-sweep-summary"
      className={'m-0 rounded-lg border px-2.5 py-1.5 text-[0.6875rem] '
        + (cost.warn
          ? 'border-amber-400/40 bg-amber-500/10 text-amber-200'
          : 'border-border bg-surface text-content-muted')}
      role={cost.warn ? 'status' : undefined}>
      <span aria-hidden>{cost.warn ? '⚠' : '🧮'}</span>{' '}
      <strong className="tabular-nums">{cost.configs}</strong> weight combinations
      {' → '}<strong className="tabular-nums">{cost.cells}</strong> image
      {cost.cells > 1 ? 's' : ''}, about {cost.label}
      {cost.measured ? ' at your current pace' : ''}.
      {cost.warn && ' That is a long queue — untick a few weights if you did not mean it.'}
    </p>
  );
}
