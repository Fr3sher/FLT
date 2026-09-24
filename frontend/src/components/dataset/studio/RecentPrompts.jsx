// Prompt history shows a STRIP of recent items and opens Saved prompts for the rest. The
// 2026-09-01 redesign replaces an unbounded wall of 167 entries with 32x40 thumbnails and about 30
// prompt characters, no search; 62 entries shared their first 30 characters, leaving tiny images
// as the only identifier. Those images were seven times smaller than Studio ResultTile (80x112)
// and fourteen times smaller than CivitaiBrowserModal (112x160). Keep a few recognizable recent
// images and move the full searchable history into a dialog with complete prompts. Each card's
// BATCH checkbox changes only the next launch's replay selection; clicking the card still fills
// the prompt. Checked prompts generate with current settings; none checked preserves the normal
// field behavior. Both Test Studio and Canvas mount this through PromptField/RunSetupPanel,
// sharing strip, browser and batch without duplication.
import { useState } from 'react';
import { HelpBadge } from '../../../help/HelpMode';
import { datasetThumbUrl } from '../../../utils/datasetThumbUrl';
import SavedPromptsModal from './SavedPromptsModal';
import { normalizeSavedPrompt } from './savedPrompts';

// Keep six prompts immediately available: one wide row or two at 400 px, enough for returning to a
// recent attempt. Beyond that, searching beats scrolling.
const INLINE = 6;
// Thumbnail size: 96x128 CSS pixels; a 256-pixel source stays sharp at 2x density.
const THUMB_SIDE = 256;

export default function RecentPrompts({
  items, datasetId, selectedPrompt, onPick, onDelete,
  batch = null, onToggleBatch = null, onClearBatch = null,
}) {
  const [browserOpen, setBrowserOpen] = useState(false);
  // Offer batching only when the host accepts it. Without onToggleBatch, neither surface shows
  // checkboxes.
  const batchable = typeof onToggleBatch === 'function';
  const picked = Array.isArray(batch) ? batch : [];
  const total = items.length;

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
        <span className="text-content-subtle text-[0.5625rem] uppercase">
          Saved prompts — click a card to reload it · thumbnail = an image you liked
        </span>
        {batchable && <HelpBadge topic="studio-prompt-batch" />}
        {batchable && picked.length > 0 && (
          <span className="flex items-center gap-1.5">
            <span className="rounded bg-purple-500/20 px-1.5 py-0.5 text-[0.5625rem] font-semibold text-purple-200 tabular-nums">
              {picked.length} selected
            </span>
            <button type="button" onClick={onClearBatch}
              className="inline-flex min-h-10 items-center px-1 text-content-subtle text-[0.5625rem] underline decoration-dotted hover:text-content lg:min-h-0 lg:px-0">
              Clear
            </button>
          </span>
        )}
      </div>
      {batchable && (
        <p className="m-0 text-content-subtle text-[0.5625rem]">
          Tick several prompts to generate them all in one run — same checkpoints,
          same settings, one image set per prompt.
        </p>
      )}

      <div className="flex flex-wrap items-stretch gap-1.5">
        {items.slice(0, INLINE).map((item) => {
          const p = normalizeSavedPrompt(item);
          const sel = selectedPrompt === p.prompt;
          const inBatch = picked.includes(p.prompt);
          // The card owns the border; checkbox and delete are OVERLAID buttons, siblings of the
          // reload button rather than nested inside it. Keep them visible without hover because
          // touchscreens have none.
          return (
            <div key={p.prompt}
              // shrink-0 preserves the intended tile width. Otherwise a tight flex row compresses
              // thumbnails, recreating the defect this redesign fixes. Tiles wrap rather than
              // shrink.
              className={`relative w-24 shrink-0 overflow-hidden rounded-lg border ${
                inBatch
                  ? 'border-purple-400 bg-purple-500/25'
                  : sel ? 'border-purple-400/60 bg-purple-500/20' : 'border-border bg-surface'}`}>
              <button type="button" onClick={() => onPick(p.prompt)} title={p.prompt}
                className="block w-full text-left">
                <span className="relative block">
                  {p.thumbnail ? (
                    <img src={datasetThumbUrl(
                      `/api/dataset/${p.thumbDatasetId ?? datasetId}/img/${encodeURIComponent(p.thumbnail)}`,
                      THUMB_SIDE)}
                      alt="" loading="lazy" decoding="async"
                      className="block h-32 w-24 object-cover" />
                  ) : (
                    <span className="flex h-32 w-24 items-center justify-center bg-app/60 px-1 text-center text-[0.5625rem] leading-snug text-content-subtle">
                      No image yet
                    </span>
                  )}
                  {p.count > 0 && (
                    <span className="absolute bottom-1 left-1 rounded bg-black/70 px-1 text-[0.5625rem] tabular-nums text-white/90">
                      {p.count}{p.liked ? ' 👍' : ''}
                    </span>
                  )}
                </span>
                {/*
                 * Clamp this SPAN, never the button: measured in Blink, -webkit-line-clamp has no
                 * effect on button because it rejects display:-webkit-box, letting the box grow
                 * with text. An inner span clamps correctly. Do not also add block because both
                 * utilities set display. Set h-9 (36px) as well: two py-1 paddings plus two 14px
                 * lines make an exact line boundary, preventing clipping through letters despite
                 * browser rounding.
                 */}
                <span className={`h-9 px-1 py-1 text-[0.625rem] leading-[0.875rem] line-clamp-2 ${
                  sel ? 'text-purple-200' : 'text-content-muted'}`}>
                  {p.prompt}
                </span>
              </button>
              {batchable && (
                <button type="button" role="checkbox" aria-checked={inBatch}
                  onClick={() => onToggleBatch(p.prompt)}
                  title={inBatch ? 'Remove this prompt from the batch' : 'Add this prompt to the batch'}
                  aria-label={inBatch ? 'Remove this prompt from the batch' : 'Add this prompt to the batch'}
                  className={`absolute left-1 top-1 flex h-10 w-10 items-center justify-center rounded bg-black/60 text-[0.6875rem] lg:h-5 lg:w-5 ${
                    inBatch ? 'text-purple-200' : 'text-white/70 hover:text-white'}`}>
                  <span aria-hidden>{inBatch ? '☑' : '☐'}</span>
                </button>
              )}
              {onDelete && (
                <button type="button"
                  onClick={() => {
                    const n = p.count ? ` and its ${p.count} test image(s)` : '';
                    if (window.confirm(`Delete this saved prompt${n}?`)) onDelete(p.prompt);
                  }}
                  title="Delete this saved prompt (and its test images)"
                  aria-label="Delete this saved prompt"
                  className="absolute right-1 top-1 flex h-10 w-10 items-center justify-center rounded bg-black/60 text-[0.6875rem] text-red-300/80 hover:bg-red-500/40 hover:text-red-200 lg:h-5 lg:w-5">
                  🗑
                </button>
              )}
            </div>
          );
        })}

        <button type="button" onClick={() => setBrowserOpen(true)}
          title="Search, read in full and manage every prompt you have launched a test with"
          className="flex min-h-[10rem] w-24 shrink-0 flex-col items-center justify-center gap-1 rounded-lg border border-dashed border-border bg-surface px-1 text-center text-[0.625rem] leading-snug text-content-muted hover:border-purple-400/60 hover:text-content">
          <span aria-hidden className="text-base">📚</span>
          Browse all
          <span className="tabular-nums font-semibold">{total}</span>
          {total > INLINE && (
            <span className="text-[0.5625rem] text-content-subtle">
              +{total - INLINE} more
            </span>
          )}
        </button>
      </div>

      {/*
       * Mount ONLY while open, rather than rendering hidden: it draws roughly 170 history rows and
       * reads toast context. Closed dialogs should impose neither cost on hosts.
       */}
      {browserOpen && (
        <SavedPromptsModal
          open onClose={() => setBrowserOpen(false)}
          items={items} datasetId={datasetId} selectedPrompt={selectedPrompt}
          onPick={onPick} onDelete={onDelete}
          batch={batch} onToggleBatch={onToggleBatch} onClearBatch={onClearBatch} />
      )}
    </div>
  );
}
