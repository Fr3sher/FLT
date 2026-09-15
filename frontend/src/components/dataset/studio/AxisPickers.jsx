import { useState } from 'react';

function StepChoices({ choices, selected, onToggle, label, amber = false }) {
  const values = [...new Set([...choices, ...selected])].sort((a, b) => a - b);
  const [position, setPosition] = useState(null);
  const last = Math.max(0, values.length - 3);
  const start = Math.min(last, Math.max(0, position ?? (values.indexOf(selected[0]) - 1)));
  const buttonClass = 'min-h-10 min-w-10 rounded-lg border px-2.5 py-1 text-xs tabular-nums transition-colors';
  return (
    <div className="flex flex-col gap-1">
      <span className="text-content-muted text-[0.625rem] uppercase">{label}</span>
      <div role="group" aria-label={label} className="flex items-center gap-2">
        <button type="button" aria-label="Show lower step counts" title="Show lower step counts"
          disabled={start === 0} onClick={() => setPosition(start - 1)}
          className={`${buttonClass} border-border bg-surface text-content-muted disabled:opacity-30`}>
          −
        </button>
        {values.slice(start, start + 3).map((v) => (
          <button key={v} type="button" aria-pressed={selected.includes(v)} onClick={() => onToggle(v)}
            className={`${buttonClass} ${selected.includes(v)
              ? amber ? 'border-amber-400/60 bg-amber-500/20 text-amber-200 font-semibold'
                : 'border-purple-400/60 bg-purple-500/20 text-purple-200 font-semibold'
              : 'border-border bg-surface text-content-muted'}`}>
            {v}
          </button>
        ))}
        <button type="button" aria-label="Show higher step counts" title="Show higher step counts"
          disabled={start === last} onClick={() => setPosition(start + 1)}
          className={`${buttonClass} border-border bg-surface text-content-muted disabled:opacity-30`}>
          +
        </button>
      </div>
      <span className="text-[0.6875rem] text-content-muted break-words" aria-live="polite">
        Selected: {selected.join(', ')}
      </span>
    </div>
  );
}

// Axes optionnels du balayage : modèle Z-Image (select), formats / CFG / steps (multi-toggles).
// Extrait behavior-preserving de LoraTestStudio.jsx (blocs modèle/formats/CFG/steps).
// Chaque bloc conserve sa garde de rendu d'origine :
//   - modèle : z_models tableau de longueur > 1
//   - formats : aspects tableau de longueur > 1
//   - CFG : cfgChoices est un tableau
//   - steps : stepsChoices est un tableau
export default function AxisPickers({
  zModels, effectiveModels, onToggleModel,
  aspects, effectiveAspects, onToggleAspect,
  cfgChoices, effectiveCfgs, onToggleCfg, defaultCfg,
  stepsChoices, effectiveSteps, onToggleStep, defaultSteps,
  // Les bases sélectionnées n'ont PAS les mêmes défauts (ex. un Z-Image Turbo et un
  // Z-Image Base dans le même balayage) : une seule paire CFG/steps ne peut pas
  // convenir aux deux, on le DIT au lieu de faire semblant. (bobba84, GitHub #18)
  mixedDefaults = false,
  // Ce que le DÉFAUT de base a d'anormal (Krea : le fichier que Setup installe
  // n'est pas là, celui élu porte autre chose que des poids). Rendu HORS de la
  // garde `zModels.length > 1` : l'install qui n'a qu'une seule base est
  // précisément celle qui n'a pas de sélecteur et qui doit quand même le lire.
  baseNote = null,
  // SDXL uniquement : 2e passe (detail daemon). Absent (null) pour Z-Image.
  steps2Choices, effectiveSteps2, onToggleStep2, defaultSteps2,
  fmt,
}) {
  // En SDXL (2 passes), le 1er picker devient « pass 1 (classic) » ; sinon « Steps ».
  const hasPass2 = Array.isArray(steps2Choices);
  return (
    <>
      {baseNote && (
        <p className="m-0 text-[0.6875rem] leading-snug text-amber-300/80 break-words">
          {baseNote}
        </p>
      )}

      {Array.isArray(zModels) && zModels.length > 1 && (
        <div className="flex flex-col gap-1">
          {/* Libellé générique : la liste vient du payload PAR FAMILLE (Z-Image,
              checkpoints SDXL, ou « Official + UNET Krea locaux »). */}
          <span className="text-content-muted text-[0.625rem] uppercase">Base model (multi)</span>
          <div className="flex gap-2 flex-wrap">
            {zModels.map((m) => (
              <button key={m.value} type="button" onClick={() => onToggleModel(m.value)}
                aria-pressed={effectiveModels.includes(m.value)}
                className={`px-2.5 py-1 rounded-lg border text-[0.75rem] transition-colors ${
                  effectiveModels.includes(m.value)
                    ? 'border-purple-400/60 bg-purple-500/20 text-purple-200 font-semibold'
                    : 'border-border bg-surface text-content-muted'}`}>
                {m.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {Array.isArray(aspects) && aspects.length > 1 && (
        <div className="flex flex-col gap-1">
          <span className="text-content-muted text-[0.625rem] uppercase">Image formats (multi)</span>
          <div className="flex gap-2 flex-wrap">
            {aspects.map((a) => (
              <button key={a} type="button" onClick={() => onToggleAspect(a)}
                aria-pressed={effectiveAspects.includes(a)}
                className={`px-2.5 py-1 rounded-lg border text-[0.75rem] tabular-nums transition-colors ${
                  effectiveAspects.includes(a)
                    ? 'border-purple-400/60 bg-purple-500/20 text-purple-200 font-semibold'
                    : 'border-border bg-surface text-content-muted'}`}>
                {a}
              </button>
            ))}
          </div>
        </div>
      )}

      {mixedDefaults && (
        <p className="m-0 text-[0.625rem] leading-snug text-amber-300/80">
          The selected base models want different sampler settings (a distilled
          “Turbo” build runs at CFG 1 / 8 steps; a non-distilled “Base” build needs
          higher guidance and far more steps). The CFG and steps axes below apply to
          every base in the run — add the values both need, or run them separately.
        </p>
      )}

      {Array.isArray(cfgChoices) && (
        <div className="flex flex-col gap-1">
          <span className="text-content-muted text-[0.625rem] uppercase">CFG (multi) — default {fmt(defaultCfg ?? 1.0)}</span>
          <div className="flex gap-2 flex-wrap">
            {cfgChoices.map((v) => (
              <button key={v} type="button" onClick={() => onToggleCfg(v)}
                aria-pressed={effectiveCfgs.includes(v)}
                className={`px-2.5 py-1 rounded-lg border text-[0.75rem] tabular-nums transition-colors ${
                  effectiveCfgs.includes(v)
                    ? 'border-purple-400/60 bg-purple-500/20 text-purple-200 font-semibold'
                    : 'border-border bg-surface text-content-muted'}`}>
                {fmt(v)}
              </button>
            ))}
          </div>
        </div>
      )}

      {Array.isArray(stepsChoices) && (
        <StepChoices key={`steps-${defaultSteps}`} choices={stepsChoices}
          selected={effectiveSteps} onToggle={onToggleStep}
          label={`${hasPass2 ? 'Steps · pass 1 — classic (multi)' : 'Steps (multi)'} — default ${defaultSteps ?? 8}`} />
      )}

      {/* SDXL : 2e passe (detail daemon, node 57 du workflow HQ). Affichée seulement
          quand le backend la propose (steps2Choices non-null = dataset SDXL). */}
      {hasPass2 && (
        <StepChoices key={`steps2-${defaultSteps2}`} choices={steps2Choices}
          selected={effectiveSteps2} onToggle={onToggleStep2} amber
          label={`Steps · pass 2 — detail daemon (multi) — default ${defaultSteps2 ?? 8}`} />
      )}
    </>
  );
}
