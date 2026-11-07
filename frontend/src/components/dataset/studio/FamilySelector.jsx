// react-frontend/src/components/dataset/studio/FamilySelector.jsx
/**
 * Test Studio FAMILY/pipeline selector. One dataset may have checkpoints from ZIT, SDXL and Krea
 * in separate loras/<family> folders. Show ONLY payload.available_families. Selecting a family
 * scopes checkpoints, base, dimensions, workflow and remembered best settings across the Studio.
 */
import { FAMILY_LABELS } from './constants';

export default function FamilySelector({ families = [], active, onSelect }) {
  if (!families || families.length < 2) return null;  // With zero or one family, there is no choice to offer.
  return (
    <div className="flex items-center gap-2 flex-wrap" role="group" aria-label="Training pipeline">
      <span className="text-content-muted text-[0.6875rem] uppercase tracking-wide">Trained in</span>
      {families.map((f) => {
        const on = f.family === active;
        return (
          <button
            key={f.family}
            type="button"
            onClick={() => onSelect?.(f.family)}
            aria-pressed={on}
            title={`Test the ${FAMILY_LABELS[f.family] || f.family} training (${f.count} checkpoint${f.count > 1 ? 's' : ''})`}
            className={`px-2.5 py-1 rounded-lg border text-[0.75rem] leading-none transition-colors ${
              on ? 'border-amber-400/60 bg-amber-400/15 text-amber-200 font-semibold'
                 : 'border-border bg-surface text-content-muted hover:text-content'}`}
          >
            {FAMILY_LABELS[f.family] || f.label || f.family}
            <span className="ml-1 text-content-subtle tabular-nums">{f.count}</span>
          </button>
        );
      })}
    </div>
  );
}
