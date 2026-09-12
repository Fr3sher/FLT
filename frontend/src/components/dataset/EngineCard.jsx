import { ENGINE_ACCENTS, ENGINE_LABELS } from './engineSelection.js'
import { contributions } from '../../plugins/registry.js'

export default function EngineCard({ id, checked, available, generating, onToggle, icon, title, tags, hint }) {
  const spec = contributions('engine.spec').find(item => item.id === id);
  const accent = spec?.accent || ENGINE_ACCENTS[id] || ENGINE_ACCENTS.klein;
  return (
    <button type="button" role="checkbox" aria-checked={checked}
      aria-label={spec?.label || ENGINE_LABELS[id] || (typeof title === 'string' ? title : id)}
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
