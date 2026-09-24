// react-frontend/src/components/dataset/studio/StudioSection.jsx
/**
 * StudioSection is a reusable collapsible group for the 320px settings rail. Format, Sampling,
 * Detail, Engine and Negative expand independently and persist by localStorage storageKey.
 * Accessible button header uses aria-expanded, aria-controls and a chevron as a non-color
 * indicator. Props: title, defaultOpen=true, storageKey, anchorId, children. Optional anchorId
 * sets the DOM ID and listens for global studio:reveal from bottom shortcuts, opening BEFORE
 * scrolling instead of landing on a collapsed header.
 */
import { useEffect, useState } from 'react';

export default function StudioSection({ title, defaultOpen = true, storageKey, anchorId, children }) {
  const [open, setOpen] = useState(() => {
    if (!storageKey) return defaultOpen;
    try {
      const v = localStorage.getItem(storageKey);
      return v === null ? defaultOpen : v === 'true';
    } catch {
      return defaultOpen;
    }
  });

  useEffect(() => {
    if (!anchorId) return undefined;
    const onReveal = (e) => { if (e.detail === anchorId) setOpen(true); };
    window.addEventListener('studio:reveal', onReveal);
    return () => window.removeEventListener('studio:reveal', onReveal);
  }, [anchorId]);

  const toggle = () => setOpen((prev) => {
    const next = !prev;
    if (storageKey) { try { localStorage.setItem(storageKey, String(next)); } catch { /* private mode */ } }
    return next;
  });

  // Stable ID for aria-controls between the chevron and panel.
  const bodyId = `studio-section-${String(storageKey || title).replace(/\W+/g, '-')}`;

  return (
    <div id={anchorId} className="rounded-lg border border-border bg-surface px-3 py-2 scroll-mt-16">
      <button
        type="button"
        onClick={toggle}
        aria-expanded={open}
        aria-controls={bodyId}
        className="flex w-full items-center justify-between gap-2 text-left"
      >
        <span className="text-content-muted text-[0.625rem] uppercase tracking-wide font-semibold">
          {title}
        </span>
        <span aria-hidden className="text-content-muted text-[0.75rem] leading-none">
          {open ? '▼' : '▶'}
        </span>
      </button>
      {open && (
        <div id={bodyId} className="border-t border-white/10 pt-2 mt-2 flex flex-col gap-2.5">
          {children}
        </div>
      )}
    </div>
  );
}
