import { CARD_H } from '../../utils/lineageGraph';
import { resumeCaption } from '../../utils/lineageTree';
import { famLabel, StatusDot, SavesChip } from './lineageChrome';
import { trainingRunVariantLabel } from '../../utils/trainingRuns';
import { runNumber, cloudNumber, runIdentityLabel } from '../../utils/runIdentity';

/* ◉ The two things a lineage is DRAWN with: a run card and a checkpoint pill.

   They used to live inside RunLineageGraph.jsx, which also owns that graph's
   whole interaction model (popover, inline generation, compare selection, pan).
   The LoRA Canvas draws the same runs on a different surface — several datasets
   at once, its own zoom and pan — so the drawing had to stop being a private
   detail of one screen. Extracted verbatim: both surfaces render the SAME card
   and the SAME pill, which is the point. A visual tweak lands on both, and there
   is no second rendering to drift.

   Presentational only — every action arrives as a prop. Neither component
   fetches, neither knows which screen it is on. */

/** The run's variant as the app NAMES it, not the raw stored value: Krea's raw
 *  recipe is stored 'base' and shown "Raw" everywhere else, so a card reading
 *  "Krea 2 · base" next to a dialog reading "Krea 2 · Raw" looked like two
 *  different runs. One label helper for both. */
export const variantLabel = (node) => trainingRunVariantLabel(node.train_type, node.variant);

/** One run as a fixed-size card. Mirrors the list card's content, sized to the
 *  graph's card box; sits at the top of the run's cell (pills go below). */
export function GraphCard({ node, lit, annotated, compareRole, onSelect }) {
  const cur = node.is_current;
  const dim = node.checkpoint_ready === false;
  const clickable = typeof onSelect === 'function';
  return (
    <div
      role={clickable ? 'button' : undefined}
      tabIndex={clickable ? 0 : undefined}
      onClick={clickable ? (e) => onSelect(node, e) : undefined}
      onKeyDown={clickable ? (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect(node, e); } } : undefined}
      title={clickable ? 'Click to inspect · Shift-click to compare' : undefined}
      style={{ height: CARD_H }}
      className={'lds-gcard flex w-full flex-col justify-center gap-1 rounded-xl border px-2.5 py-1.5 '
        + (cur
          ? 'lds-gcard-current border-indigo-400/70 bg-indigo-500/10 ring-1 ring-indigo-400/30 '
          : dim
            ? 'border-border bg-app/40 '
            : 'border-border bg-surface-raised ')
        + (lit && !cur ? 'ring-1 ring-indigo-300/40 border-indigo-400/50 ' : '')
        + (compareRole ? 'ring-2 ring-amber-400/70 border-amber-400/60 ' : '')
        + (clickable ? 'cursor-pointer' : '')}>
      <div className="flex min-w-0 items-center gap-1.5">
        <StatusDot status={node.status} />
        {/* THE run number = the record id, the same one the inspector shows.
            The cloud id rides along as an explicit secondary (and in the title)
            so the card can still be matched to a row on the Runs page — it is
            never printed as a bare number that would read like the run's own. */}
        <span className="shrink-0 font-mono text-content-muted text-[0.625rem]"
          title={runIdentityLabel(node)}>
          <span aria-hidden>{node.source === 'cloud' ? '☁' : '💻'}</span>{' '}
          {runNumber(node)}
          {cloudNumber(node) != null && (
            <span className="text-content-subtle"> · cloud #{cloudNumber(node)}</span>
          )}
        </span>
        <span className={`min-w-0 truncate text-[0.75rem] font-semibold ${dim ? 'text-content-muted' : 'text-content'}`}
          title={`${famLabel(node.train_type)}${variantLabel(node) ? ` · ${variantLabel(node)}` : ''}`}>
          {famLabel(node.train_type)}{variantLabel(node)
            ? <span className="font-normal text-content-muted"> · {variantLabel(node)}</span> : null}
        </span>
        {cur && (
          <span className="shrink-0 rounded-full bg-indigo-500/25 px-1.5 py-0.5 text-indigo-100 text-[0.5rem] font-bold uppercase tracking-wider">
            this run
          </span>
        )}
        {annotated && (
          <span aria-hidden title="Has notes" className="shrink-0 text-amber-300 text-[0.625rem] leading-none">●</span>
        )}
        {compareRole && (
          <span title={`Selected for compare (${compareRole})`}
            className="shrink-0 rounded-full bg-amber-500/25 px-1.5 py-0.5 text-amber-100 text-[0.5rem] font-bold uppercase tracking-wider">
            {compareRole}
          </span>
        )}
        <span className="ml-auto shrink-0"><SavesChip node={node} /></span>
      </div>
      <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-0.5 text-content-subtle text-[0.5625rem]">
        {node.version != null && (
          <span className="rounded bg-app/60 px-1 py-px font-medium text-content-muted">v{node.version}</span>
        )}
        {node.steps ? <span className="tabular-nums">{node.steps.toLocaleString()} steps</span> : null}
        {resumeCaption(node) && (
          <span className="inline-flex items-center gap-0.5">
            <span aria-hidden className="text-[0.625rem] leading-none">↳</span>{resumeCaption(node)}
          </span>
        )}
        {node.origin_unknown && (
          <span className="italic" title="This run resumed from an earlier checkpoint, but its source run predates lineage tracking">
            origin not recorded
          </span>
        )}
      </div>
    </div>
  );
}

/** One checkpoint as a compact pill: its step, a ✓ for the final save, an indigo
 *  ring when it's the point another run branched off, and — the Lab flagship — a
 *  select checkbox (deployed checkpoints only) plus its inline generated preview
 *  (thumbnail when done, a ◌ while it renders, a ⚠ if it failed). Clicking the
 *  body opens the pill's actions; the checkbox toggles it into the shared-prompt
 *  generation batch. Absolutely positioned at the exact box the layout computed. */
export function CheckpointPill({ pill, offX, offY, active, selected, preview, big, onOpen, onToggleSelect, onZoomPreview, onOpenGallery, selectable = null }) {
  const gone = pill.present === false;
  const st = preview?.status || null;
  const label = pill.step >= 1000 && pill.step % 1000 === 0 ? `${pill.step / 1000}k` : pill.step;
  const zoom = (e) => { e.stopPropagation(); onZoomPreview?.(preview.url, pill.step); };
  const zoomKey = (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); zoom(e); } };
  const shellCls = 'lds-ckpill rounded-md border transition-colors '
    + (gone
      ? 'border-dashed border-border bg-transparent text-content-subtle '
      : pill.final
        ? 'border-emerald-400/50 bg-emerald-500/10 text-emerald-200 '
        : 'border-border bg-app/70 text-content-muted hover:border-indigo-400/50 hover:text-content ')
    + (pill.isResumeSource ? 'ring-1 ring-indigo-400/60 border-indigo-400/60 ' : '')
    + (selected ? 'ring-2 ring-indigo-400/80 border-indigo-400/70 ' : active ? 'ring-2 ring-indigo-400/80 ' : '');
  const openTitle = `Checkpoint at step ${pill.step}${pill.final ? ' — final' : ''}${pill.isResumeSource ? ' — a run continued from here' : ''}${st ? ` — preview ${st}` : ''}`;
  return (
    <div style={{ position: 'absolute', left: offX, top: offY, width: pill.w, height: pill.h }}
      className="lds-ckpill-wrap">
      {big ? (
        // 🔍 Big-preview tile: a large generated image on top (ComfyUI-style — click
        // it to view full-screen), with a step label strip underneath that opens
        // the pill's actions. The whole tile still opens the popover except the
        // image, which zooms.
        <button type="button"
          onClick={(e) => { e.stopPropagation(); onOpen(pill); }}
          title={openTitle}
          style={{ width: pill.w, height: pill.h }}
          className={shellCls + ' flex w-full flex-col overflow-hidden text-[0.625rem] font-medium tabular-nums'}>
          <div className="relative min-h-0 flex-1 w-full">
            {preview?.url ? (
              <img src={preview.url} alt={`Preview at step ${pill.step}`}
                role="button" tabIndex={0} title="Click to view this preview full-screen"
                onClick={zoom} onKeyDown={zoomKey}
                className="h-full w-full cursor-zoom-in object-cover hover:opacity-90" />
            ) : (
              <div className="flex h-full w-full items-center justify-center text-base">
                {st === 'pending' ? <span aria-hidden title="Generating preview…" className="animate-pulse text-indigo-300">◌</span>
                  : st === 'failed' ? <span aria-hidden title="Preview failed" className="text-amber-300">⚠</span>
                  : <span aria-hidden className="opacity-50">💾</span>}
              </div>
            )}
          </div>
          <span className="flex shrink-0 items-center justify-center gap-0.5 border-t border-border bg-black/20 py-0.5 leading-none">
            {pill.final && <span aria-hidden className="text-emerald-300">✓</span>}
            <span>{label}</span>
          </span>
        </button>
      ) : (
        <button type="button"
          onClick={(e) => { e.stopPropagation(); onOpen(pill); }}
          title={openTitle}
          style={{ width: pill.w, height: pill.h }}
          className={shellCls + ' flex w-full items-center justify-center gap-0.5 text-[0.5625rem] font-medium tabular-nums'}>
          {pill.final && <span aria-hidden className="text-emerald-300">✓</span>}
          <span>{label}</span>
          {preview?.url ? (
            // The thumbnail is tiny by necessity (the pill is 60×20). Clicking it
            // opens the preview LARGE in a lightbox — a DISTINCT action from the
            // pill's popover, so stopPropagation keeps the two from colliding.
            <img src={preview.url} alt={`Preview at step ${pill.step}`} width={14} height={14}
              role="button" tabIndex={0}
              title="Click to view this preview large"
              onClick={zoom} onKeyDown={zoomKey}
              className="ml-0.5 h-3.5 w-3.5 shrink-0 cursor-zoom-in rounded-sm object-cover ring-1 ring-black/30 hover:ring-indigo-400/80" />
          ) : st === 'pending' ? (
            <span aria-hidden title="Generating preview…" className="ml-0.5 animate-pulse text-indigo-300">◌</span>
          ) : st === 'failed' ? (
            <span aria-hidden title="Preview failed" className="ml-0.5 text-amber-300">⚠</span>
          ) : (
            <span aria-hidden className="opacity-70">💾</span>
          )}
        </button>
      )}
      {/* Select for the shared-prompt batch. A corner box; clicking it never opens
          the popover. Slightly larger in big mode so it stays clickable on the tile.
          `selectable` defaults to "deployed only" — the in-card graph can render
          nothing else. The canvas passes a wider rule: it offers to DEPLOY the
          picks that are not in ComfyUI yet, so a not-yet-deployed checkpoint has
          to be pickable there. */}
      {(selectable ?? pill.testable) && typeof onToggleSelect === 'function' && (
        <button type="button" role="checkbox" aria-checked={selected}
          aria-label={`Select step ${pill.step} for preview`}
          title={selected ? 'Selected for preview' : 'Select for preview'}
          onClick={(e) => { e.stopPropagation(); onToggleSelect(pill); }}
          style={{ position: 'absolute', left: -6, top: -6 }}
          className={'lds-cksel flex items-center justify-center rounded-[3px] border leading-none shadow-sm '
            + (big ? 'h-5 w-5 text-[0.6875rem] ' : 'h-4 w-4 text-[0.625rem] ')
            + (selected ? 'border-indigo-400 bg-indigo-500 text-white ' : 'border-border-strong bg-surface-overlay text-transparent hover:border-indigo-400 ')}>
          ✓
        </button>
      )}
      {/* × N — how many images this checkpoint has produced IN TOTAL, from any
          surface (inline preview, Test Studio, comparison run). They accumulate
          now: a regenerated preview no longer replaces the previous one, it joins
          it. Clicking opens the gallery when the host offers one; without a
          handler it stays an honest count rather than a dead button. */}
      {preview?.count > 1 && (
        typeof onOpenGallery === 'function' ? (
          <button type="button"
            aria-label={`Open the ${preview.count} images of step ${pill.step}`}
            title={`${preview.count} images generated from this checkpoint — click to open them`}
            onClick={(e) => { e.stopPropagation(); onOpenGallery(pill); }}
            style={{ position: 'absolute', right: -6, bottom: -6 }}
            className="lds-ckcount flex h-4 min-w-4 items-center justify-center rounded-full border border-indigo-400/70 bg-surface-overlay px-1 text-indigo-200 text-[0.5625rem] font-semibold leading-none tabular-nums shadow-sm hover:bg-indigo-500 hover:text-white">
            {preview.count}
          </button>
        ) : (
          <span title={`${preview.count} images generated from this checkpoint`}
            style={{ position: 'absolute', right: -6, bottom: -6 }}
            className="lds-ckcount flex h-4 min-w-4 items-center justify-center rounded-full border border-border bg-surface-overlay px-1 text-content-muted text-[0.5625rem] font-semibold leading-none tabular-nums">
            {preview.count}
          </span>
        )
      )}
    </div>
  );
}
