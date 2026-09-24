/**
 * One LoRA in a Blend stack: name, trigger, weight slider and weight CHECKBOXES that turn launch
 * into a sweep. Shared by Test Studio LoraStackPanel and LoRA Canvas CanvasBlendPanel. Callers
 * supply rendered label and trigger because one identifies LoRAs by filename, the other by run
 * badge. Slider, checkboxes and the no-checkbox-means-slider rule live here once. Use two rows: at
 * 400 px, placing name beside slider reduced it to a single letter.
 */
import {
  BLEND_WEIGHT_CHIPS, COMBINE_MAX_WEIGHT, COMBINE_MIN_WEIGHT, clampBlendWeight,
} from './loraStack';

export default function BlendWeightRow({
  index, label, title, trigger = null, weight, onWeight, set = [], onToggleChip,
}) {
  const sweeping = set.length > 0;

  return (
    <li className="flex flex-col gap-1 rounded-lg border border-border bg-surface-raised px-2.5 py-1.5">
      <div className="flex min-w-0 items-center gap-2">
        <span className="shrink-0 text-content-subtle text-[0.625rem] tabular-nums">{index}.</span>
        <span className="min-w-0 flex-1 truncate text-content text-[0.8125rem]" title={title || label}>
          {label}
        </span>
        {trigger}
      </div>

      <label className={'flex items-center gap-1.5 text-[0.6875rem] '
        + (sweeping ? 'text-content-subtle' : 'text-content-muted')}>
        <span className="shrink-0 uppercase">Weight</span>
        <input type="range" min={COMBINE_MIN_WEIGHT} max={COMBINE_MAX_WEIGHT} step="0.05"
          value={weight} onChange={(e) => onWeight(Number(e.target.value))}
          aria-label={`Weight for ${label}`}
          className="min-w-0 flex-1 accent-primary" />
        {/* The number, TYPEABLE. The slider now spans 0–5, so a 0.05 step is
            eighty drags from one end to the other and "1.35" is a target you
            hunt for. The readout was already the exact place the eye lands, so
            it becomes the field instead of gaining a second one beside it.
            An unreadable entry (empty, "abc", 12) leaves the weight where it
            was rather than inventing one — clampBlendWeight decides, once, and
            is unit-tested. */}
        <input type="number" inputMode="decimal"
          min={COMBINE_MIN_WEIGHT} max={COMBINE_MAX_WEIGHT} step="0.05"
          value={weight}
          data-testid="blend-weight-number"
          onChange={(e) => {
            const next = clampBlendWeight(e.target.value);
            if (next != null) onWeight(next);
          }}
          aria-label={`Weight value for ${label} (0 to ${COMBINE_MAX_WEIGHT})`}
          title={`Type a weight between ${COMBINE_MIN_WEIGHT} and ${COMBINE_MAX_WEIGHT}`}
          className="w-14 shrink-0 rounded border border-border bg-app/60 px-1 py-0.5 text-right text-content tabular-nums focus:border-primary focus:outline-none" />
      </label>

      {/*
       * Checking a weight sweeps that value; checking none leaves the slider in control,
       * preserving the original behavior and allowing off-grid weights. Explain BELOW the
       * checkboxes because they make users wonder why moving the slider no longer changes the
       * result.
       */}
      <div className="flex flex-wrap items-center gap-1">
        <span className="shrink-0 text-content-subtle text-[0.625rem] uppercase">Sweep</span>
        {BLEND_WEIGHT_CHIPS.map((w) => {
          const on = set.includes(w);
          return (
            <button key={w} type="button" onClick={() => onToggleChip(w)}
              aria-pressed={on}
              title={on ? `Stop sweeping ${w}` : `Also render this LoRA at ${w}`}
              className={'rounded border px-1.5 py-0.5 text-[0.625rem] font-semibold tabular-nums '
                + (on
                  ? 'border-primary/60 bg-primary/25 text-content'
                  : 'border-border bg-app/60 text-content-subtle hover:text-content')}>
              {w}
            </button>
          );
        })}
      </div>
      <p className="m-0 text-content-subtle text-[0.625rem]">
        {sweeping
          ? `Sweeping ${set.length} weight${set.length > 1 ? 's' : ''} — the slider is ignored for this LoRA.`
          : 'No box ticked: the slider above is this LoRA’s weight.'}
      </p>
    </li>
  );
}
