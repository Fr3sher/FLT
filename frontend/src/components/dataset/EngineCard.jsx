import { engineAccent, engineLabel } from '../../engines/catalog.js';

/* One engine CHECKBOX card of the generate panel. A checkbox, not a radio:
   engines combine. Each carries its own accent (the catalog's) so a mixed run
   is readable — green is deliberately not one of them, it already means
   "kept / free".

   Its own module because the plugins' engines render through it too: an API
   engine's card is a panel the plugin contributes (`card` on its engine spec,
   see src/engines/catalog.js), and that panel imports THIS component rather
   than re-drawing the checkbox — one card shape for every engine, whoever
   brought it. */

/** The tag pills every card wears: a fact about the price or the machine. */
export const TAG_CLASS = 'px-1.5 py-px rounded-full bg-app/60 border border-border text-content-muted text-[0.625rem]';
/** Green stays a statement about the PRICE, never a selection state. */
export const FREE_TAG_CLASS = 'px-1.5 py-px rounded-full bg-emerald-500/15 border border-emerald-400/40 text-emerald-300 text-[0.625rem]';

export default function EngineCard({ id, checked, available, generating, onToggle, icon, title, tags, hint }) {
  const accent = engineAccent(id);
  return (
    <button type="button" role="checkbox" aria-checked={checked}
      aria-label={engineLabel(id)}
      onClick={() => onToggle(id)}
      disabled={!available || !!generating}
      title={generating ? 'A generation batch is running — wait for it to finish before changing engines' : undefined}
      className={`relative flex items-start gap-3 rounded-xl border p-3 text-left transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${checked
        ? accent.card
        : 'border-border bg-app/40 hover:enabled:bg-surface-raised'}`}>
      <span aria-hidden="true"
        className={`absolute top-2 right-2 w-4 h-4 rounded border grid place-items-center text-[0.625rem] font-bold ${checked
          ? `${accent.pill} border-transparent` : 'border-border text-transparent'}`}>✓</span>
      {icon}
      <span className="flex flex-col gap-1 min-w-0">
        <span className={`text-[0.8125rem] font-semibold ${checked ? accent.title : 'text-content-muted'}`}>
          {title}
        </span>
        <span className="flex flex-wrap gap-1">{tags}</span>
        {hint}
      </span>
    </button>
  );
}
