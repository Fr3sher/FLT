// Saved prompts browses the full history BY IMAGE. A real installation had about 170 entries shown
// together as 32x40 thumbnails and roughly 30 prompt characters, while median prompt length was
// about 500. Of 167 entries, 62 shared their first 30 characters, including 19 identical prefixes,
// so only images distinguished cards. Match Civitai browser thumbnail sizing, giving remaining
// width to five expandable prompt lines. Search makes that history manageable, consistent with
// Bank, Canvas, Caption Lab and datasets. Like the recent strip, this management dialog supports
// reuse, batch selection and deletion. Offer batches only when onToggleBatch exists; callers such
// as Generate from the board without that handler must not show them.
import { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useToast } from '../../common/Toast';
import { useFocusTrap } from '../../../hooks/useFocusTrap';
import { HelpBadge } from '../../../help/HelpMode';
import { datasetThumbUrl } from '../../../utils/datasetThumbUrl';
import { filterSavedPrompts, normalizeSavedPrompt } from './savedPrompts';

// Request 384-pixel thumbnails for 144x192 CSS tiles. Rows load lazily, roughly four are visible
// at once, and inspecting the image is this dialog's purpose.
const THUMB_SIDE = 384;

/**
 * Dialog content WITHOUT the portal, exported separately for tests: renderToStaticMarkup cannot
 * render portals, so separating content makes it testable.
 */
export function SavedPromptsPanel({
  open, onClose, items, datasetId, selectedPrompt, onPick, onDelete,
  batch = null, onToggleBatch = null, onClearBatch = null,
}) {
  const toast = useToast();
  const ref = useRef(null);
  useFocusTrap(ref, open);
  const [query, setQuery] = useState('');
  const [expanded, setExpanded] = useState(() => new Set());
  // Lock background page scrolling while open, matching other dialogs such as CaptionLabPicker.
  useEffect(() => {
    if (!open) return undefined;
    const before = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = before; };
  }, [open]);

  const batchable = typeof onToggleBatch === 'function';
  const picked = Array.isArray(batch) ? batch : [];
  const shown = useMemo(() => filterSavedPrompts(items, query), [items, query]);

  if (!open) return null;

  const total = Array.isArray(items) ? items.length : 0;
  const copyPrompt = async (text) => {
    try {
      await navigator.clipboard.writeText(text);
      toast.success('Prompt copied');
    } catch {
      toast.error('Could not copy — select the text and copy it manually.');
    }
  };
  const toggleExpand = (p) => setExpanded((cur) => {
    const next = new Set(cur);
    if (next.has(p)) next.delete(p); else next.add(p);
    return next;
  });
  // Choosing a prompt closes the dialog: its job is done, and leaving launch setup hidden would
  // encourage configuring a run without seeing the newly filled field.
  const use = (p) => { onPick(p); onClose(); };

  return (
    <div className="fixed inset-0 z-[9999] bg-black/70 flex items-center justify-center p-4"
      onKeyDown={(e) => { if (e.key === 'Escape') { e.preventDefault(); onClose(); } }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      {/*
       * Mark both chrome and layer: the responsive probe measures touch targets and truncation
       * only INSIDE data-probe-chrome. An unmarked dialog is unmeasured, not verified clean.
       */}
      <div role="dialog" aria-modal="true" aria-label="Browse saved test prompts" ref={ref}
        data-probe-chrome="saved-prompts" data-probe-layer
        className="w-full max-w-4xl max-h-[88vh] rounded-2xl border border-border bg-surface-overlay p-4 flex flex-col gap-3 shadow-xl">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-content text-sm font-semibold flex items-center gap-1.5">
            <span aria-hidden>📚</span> Saved prompts
            <span className="text-content-subtle font-normal tabular-nums">({total})</span>
            <HelpBadge topic="studio-saved-prompts" />
          </h2>
          <button type="button" onClick={onClose} aria-label="Close"
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-border bg-app text-content-muted hover:text-content lg:h-8 lg:w-8">×</button>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <input type="search" value={query} onChange={(e) => setQuery(e.target.value)}
            aria-label="Search saved prompts"
            placeholder="Search your prompts… (e.g. bathroom mirror)"
            className="min-h-10 min-w-0 flex-1 rounded-lg border border-border bg-app/60 px-2.5 py-1.5 text-content text-[0.75rem] lg:min-h-0" />
          <span className="text-content-subtle text-[0.6875rem] tabular-nums" role="status">
            {query.trim() ? `${shown.length} of ${total}` : `${total} prompts`}
          </span>
          {batchable && picked.length > 0 && (
            <span className="flex items-center gap-1.5">
              <span className="rounded bg-purple-500/20 px-1.5 py-0.5 text-[0.6875rem] font-semibold text-purple-200 tabular-nums">
                {picked.length} selected
              </span>
              <button type="button" onClick={onClearBatch}
                className="inline-flex min-h-10 items-center px-1 text-content-subtle text-[0.6875rem] underline decoration-dotted hover:text-content lg:min-h-0 lg:px-0">
                Clear
              </button>
            </span>
          )}
        </div>
        {batchable && (
          <p className="m-0 text-content-subtle text-[0.6875rem] leading-snug">
            Tick several prompts to generate them all in one run — same checkpoints,
            same settings, one image set per prompt. Ticking writes nothing into the
            prompt field; “⤵ Use prompt” does that.
          </p>
        )}

        <div className="min-h-0 flex-1 overflow-y-auto flex flex-col gap-2 pr-1">
          {shown.map((item) => {
            const p = normalizeSavedPrompt(item);
            const sel = selectedPrompt === p.prompt;
            const inBatch = picked.includes(p.prompt);
            const isOpen = expanded.has(p.prompt);
            return (
              <div key={p.prompt}
                className={`flex gap-2.5 rounded-xl border p-2 ${
                  inBatch ? 'border-purple-400 bg-purple-500/15'
                    : sel ? 'border-purple-400/60 bg-purple-500/10' : 'border-border bg-surface'}`}>
                {p.thumbnail ? (
                  <img
                    src={datasetThumbUrl(
                      `/api/dataset/${p.thumbDatasetId ?? datasetId}/img/${encodeURIComponent(p.thumbnail)}`,
                      THUMB_SIDE)}
                    alt="" loading="lazy" decoding="async"
                    className="w-28 sm:w-36 h-40 sm:h-48 shrink-0 object-cover rounded-lg border border-border" />
                ) : (
                  // No thumbnail means this prompt never produced an image or its images were
                  // deleted. A large question mark adds no information; give the space to the
                  // remaining signal, the text.
                  <div className="w-28 sm:w-36 h-40 sm:h-48 shrink-0 rounded-lg border border-dashed border-border bg-app/40 flex items-center justify-center px-2 text-center text-content-subtle text-[0.625rem] leading-snug">
                    No image yet
                  </div>
                )}
                <div className="flex flex-col gap-1.5 min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[0.625rem] text-content-subtle">
                    {p.count > 0
                      ? <span className="tabular-nums">{p.count} test image{p.count > 1 ? 's' : ''}</span>
                      : <span className="rounded border border-border bg-app/60 px-1.5 py-px">never run</span>}
                    {p.liked && <span title="The thumbnail is an image you liked">👍 liked</span>}
                    {sel && <span className="text-purple-300">in the prompt field</span>}
                  </div>
                  {/*
                   * Clamp the SPAN, not the button. Browser measurements show Blink refuses
                   * display:-webkit-box on buttons, so line-clamp does nothing and prompts up to
                   * 2000 characters enlarge the row. An inner span clamps correctly.
                   */}
                  <button type="button" onClick={() => toggleExpand(p.prompt)}
                    title={isOpen ? 'Collapse the prompt' : 'Show the full prompt'}
                    className="m-0 min-h-10 text-left text-content text-[0.75rem] leading-snug lg:min-h-0">
                    <span className={`whitespace-pre-wrap break-words ${isOpen ? '' : 'line-clamp-5'}`}>
                      {p.prompt}
                    </span>
                  </button>
                  <div className="mt-auto flex flex-wrap items-center gap-1.5">
                    {batchable && (
                      <button type="button" role="checkbox" aria-checked={inBatch}
                        onClick={() => onToggleBatch(p.prompt)}
                        title={inBatch ? 'Remove this prompt from the batch' : 'Add this prompt to the batch'}
                        className={`px-2 py-1 min-h-10 lg:min-h-0 rounded border text-[0.6875rem] ${
                          inBatch
                            ? 'border-purple-400 bg-purple-500/25 text-purple-200'
                            : 'border-border bg-app text-content-muted hover:text-content'}`}>
                        <span aria-hidden>{inBatch ? '☑' : '☐'}</span> Batch
                      </button>
                    )}
                    <button type="button" onClick={() => copyPrompt(p.prompt)}
                      title="Copy this prompt"
                      className="px-2 py-1 min-h-10 lg:min-h-0 rounded border border-border bg-app text-content-muted text-[0.6875rem] hover:text-content">
                      📋 Copy
                    </button>
                    {onDelete && (
                      <button type="button"
                        onClick={() => {
                          const n = p.count ? ` and its ${p.count} test image(s)` : '';
                          if (window.confirm(`Delete this saved prompt${n}?`)) onDelete(p.prompt);
                        }}
                        title="Delete this saved prompt (and its test images)"
                        aria-label="Delete this saved prompt"
                        className="px-2 py-1 min-h-10 lg:min-h-0 rounded border border-border bg-app text-red-300/70 text-[0.6875rem] hover:text-red-300 hover:bg-red-500/15">
                        🗑 Delete
                      </button>
                    )}
                    <button type="button" onClick={() => use(p.prompt)}
                      title="Load this prompt into the prompt field"
                      className="ml-auto px-2.5 py-1 min-h-10 lg:min-h-0 rounded-lg bg-gradient-primary text-gray-950 text-[0.6875rem] font-semibold">
                      ⤵ Use prompt
                    </button>
                  </div>
                </div>
              </div>
            );
          })}

          {shown.length === 0 && (
            <p className="m-0 rounded-lg border border-border bg-surface px-3 py-6 text-center text-content-subtle text-[0.75rem]">
              {total === 0
                ? 'No saved prompts yet — the prompts you launch a test with are kept here.'
                : `No saved prompt contains every word of “${query.trim()}”.`}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

/*
 * Portal to body is required: the launch panel lives inside a sticky, scrollable aside. Sticky
 * creates a stacking context that traps any inner z-index below the app header, and at lg sizes
 * the aside's scrolling also clips the dialog. Before the fix, browser measurements showed
 * header/page fragments painted over it. CaptionLabPicker and Continue already use portals for the
 * same reason.
 */
export default function SavedPromptsModal(props) {
  if (!props.open) return null;
  return createPortal(<SavedPromptsPanel {...props} />, document.body);
}
