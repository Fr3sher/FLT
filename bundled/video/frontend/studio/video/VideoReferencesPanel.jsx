import { useEffect, useRef, useState } from 'react';
import { ArrowDown, ArrowUp, Image, Film, Library, Music, Scissors, Trash2 } from 'lucide-react';
import { postForm, postJson } from '@lds/plugin-sdk';
import { HelpBadge } from '@lds/plugin-sdk';
import { useToast } from '@lds/plugin-sdk';
import ReferenceLibraryPicker from './ReferenceLibraryPicker';
import ReferenceMediaPreview from './ReferenceMediaPreview';
import { librarySelectionBody, librarySelectionKey, referenceLibraryKey } from './referenceLibrary';
import { sourceUrl } from './videoStudioApi';
import { CUT_MAX_SECONDS, CUT_MIN_SECONDS, cutBody, cutDefaultDuration, cutInterval, moveReference, REFERENCE_DEFAULTS, REFERENCE_LIMITS, referenceFormatSize, referenceUrl, replaceReference, selectReferenceFormat, taggedReferences } from './videoReferences';

const MEDIA = [
  { kind: 'image', label: 'Images', accept: 'image/*', Icon: Image },
  { kind: 'video', label: 'Videos', accept: 'video/*', Icon: Film },
  { kind: 'audio', label: 'Audio', accept: 'audio/*', Icon: Music },
];
const BUTTON = 'min-h-10 rounded-md border border-border px-2 py-1 text-xs text-content-muted hover:text-content disabled:opacity-40 lg:min-h-0';
const INPUT = 'min-h-10 w-full rounded-md border border-border bg-surface px-2 text-xs text-content lg:min-h-0 lg:py-1.5';

/* ✂ Cut a reference video to the interval that matters (2026-09-06). The
   render reads a reference video up to the CLIP's length (the graph slices it
   there, and the H3 node trims to 17k+5 frames — measured in refutation), so
   only a cut shorter than the clip lightens the sequence: 107 frames instead
   of 175 for a 5 s cut behind a 7.3 s clip. The card says the threshold. Same
   words as the library's excerpt (Start · seconds, Duration · seconds,
   2–15 s), checked before the press. */
function ReferenceCut({ reference, clipSeconds, disabled, onCut }) {
  const total = Number(reference.duration) || 0;
  const [open, setOpen] = useState(false);
  const [start, setStart] = useState('0');
  const [duration, setDuration] = useState(String(cutDefaultDuration(total)));
  const check = cutInterval(reference, start, duration);
  const original = Number(reference.cut_source_duration);
  const errorId = `reference-cut-error-${String(reference.name).replace(/[^A-Za-z0-9]/g, '')}`;
  if (!open) {
    return (
      <div className="flex flex-wrap items-center gap-2 text-[0.6875rem] text-content-subtle">
        <button type="button" className={BUTTON} disabled={disabled || total < CUT_MIN_SECONDS + 0.05} onClick={() => setOpen(true)}
          data-testid="reference-cut-open" aria-label={`Cut ${reference.tag}`}><Scissors className="mr-1 inline h-3.5 w-3.5" />Cut</button>
        <HelpBadge topic="video-reference-cut" />
        <span className="min-w-0">
          {reference.cut_from ? `Cut to ${total.toFixed(1)} s` : `${total.toFixed(1)} s`}
          {reference.cut_from && Number.isFinite(original) && original > 0 ? ` of ${original.toFixed(1)} s` : ''}
          {Number.isFinite(clipSeconds) && clipSeconds > 0
            ? `. The render reads it up to the clip’s ${clipSeconds.toFixed(1)} s: a cut shorter than that lightens the render, a longer one changes nothing.`
            : '. The render reads it up to the clip’s length: only a cut shorter than the clip lightens the render.'}
        </span>
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-1 rounded-md border border-border p-2" data-testid="reference-cut">
      <p className="text-[0.6875rem] text-content-subtle">
        Keep this interval of the video ({CUT_MIN_SECONDS}–{CUT_MAX_SECONDS} s); the rest is dropped. Times start at the beginning of this copy.
        {Number.isFinite(clipSeconds) && clipSeconds > 0 ? ` Only a cut shorter than the clip (${clipSeconds.toFixed(1)} s) lightens the render.` : ''}
      </p>
      <div className="grid grid-cols-2 gap-2">
        <label className="flex min-w-0 flex-col gap-1 text-xs text-content-muted">Start · seconds
          <input type="number" aria-label={`Start seconds for ${reference.tag}`} min="0" step="0.1" value={start} disabled={disabled}
            aria-invalid={!!check.error} aria-describedby={check.error ? errorId : undefined}
            onChange={(e) => setStart(e.target.value)} className={INPUT} /></label>
        <label className="flex min-w-0 flex-col gap-1 text-xs text-content-muted">Duration · seconds
          <input type="number" aria-label={`Duration seconds for ${reference.tag}`} min={CUT_MIN_SECONDS} max={CUT_MAX_SECONDS} step="0.1" value={duration} disabled={disabled}
            aria-invalid={!!check.error} aria-describedby={check.error ? errorId : undefined}
            onChange={(e) => setDuration(e.target.value)} className={INPUT} /></label>
      </div>
      {check.error && <p id={errorId} role="alert" className="text-[0.6875rem] text-amber-200">{check.error}</p>}
      <div className="flex flex-wrap gap-2">
        <button type="button" className={BUTTON} disabled={disabled || !!check.error} data-testid="reference-cut-apply"
          onClick={() => onCut(check.start, check.duration)}>Cut to {check.error ? '…' : `${check.duration.toFixed(1)} s`}</button>
        <button type="button" className={BUTTON} disabled={disabled} onClick={() => setOpen(false)}>Cancel</button>
      </div>
    </div>
  );
}

export default function VideoReferencesPanel({ value, limits, disabled, onInsertTag, identitiesOnly = false }) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [libraryTarget, setLibraryTarget] = useState(null);
  const uploading = useRef(false);
  const mounted = useRef(true);
  const generation = useRef(0);
  const latest = useRef(value);
  latest.current = value;
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; generation.current += 1; if (uploading.current) latest.current.setStaging(false); };
  }, []);
  const refs = value.references;
  const rows = taggedReferences(refs);
  const cap = identitiesOnly ? { image: Infinity, video: 0, audio: 0 } : { ...REFERENCE_LIMITS, ...limits };
  const change = (name, patch) => value.setReferences((list) => list.map((r) => r.name === name ? { ...r, ...patch } : r));
  // The clip's length in seconds, the threshold under which a cut lightens the render.
  const clipSeconds = Math.max(0, ((Number(value.settings?.frames) || REFERENCE_DEFAULTS.frames) - 1) / 24);
  const remove = (name) => value.setReferences((list) => list.filter((r) => r.name !== name));

  const stage = async (kind, picks) => {
    if (uploading.current || disabled) return [];
    const mine = ++generation.current;
    const signature = latest.current.references.map((r) => r.name).join('|');
    const current = () => mounted.current && generation.current === mine && latest.current.references.map((r) => r.name).join('|') === signature;
    uploading.current = true;
    setBusy(true); value.setStaging(true);
    setNotice('');
    const room = Math.max(0, cap[kind] - latest.current.references.filter((r) => r.kind === kind).length);
    const seen = new Set(latest.current.references.map(referenceLibraryKey));
    const unique = picks.filter((p) => { if (!p.key) return true; if (seen.has(p.key)) return false; seen.add(p.key); return true; });
    const selected = unique.slice(0, room);
    const done = [];
    const errors = [];
    if (unique.length < picks.length) errors.push('References already added were skipped.');
    if (selected.length < unique.length) errors.push(`Only ${cap[kind]} ${kind} references fit; ${unique.length - selected.length} skipped.`);
    try {
      for (const pick of selected) {
        if (!current()) break;
        try {
          const r = await pick.send();
          if (!current()) break;
          if (!r?.reference?.name) throw new Error('The server returned no reference.');
          done.push({ ...r.reference, key: pick.key || r.reference.name });
        } catch (e) { errors.push(`${pick.label || kind}: ${e?.message || 'Could not prepare this reference.'}`); }
      }
      if (!current()) { if (mounted.current) setNotice('The inputs changed while preparing. Choose the references again for this setup.'); return []; }
      if (done.length) latest.current.setReferences((list) => [...list, ...done]);
      if (errors.length) setNotice(errors.join(' '));
      return done.map((r) => r.key);
    } finally { if (generation.current === mine) { uploading.current = false; if (mounted.current) setBusy(false); latest.current.setStaging(false); } }
  };
  const upload = (kind, files) => stage(kind, Array.from(files || []).map((file) => ({
    label: file.name, send: () => {
      const form = new FormData(); form.append('file', file); form.append('kind', kind);
      if (kind === 'video') form.append('include_audio', 'false');
      return postForm(referenceUrl(), form);
    },
  })));
  const adoptLibrary = (kind, selections) => stage(kind, selections.map((selection) => ({
    key: librarySelectionKey(kind, selection), label: selection.item.label,
    send: () => postJson(referenceUrl(), librarySelectionBody(kind, selection)),
  })));
  const prepareGuide = async (which, send, key) => {
    if (uploading.current || disabled) return [];
    const mine = ++generation.current;
    const previous = latest.current[which]?.image;
    const previousRefs = latest.current.references.map((r) => r.name).join('|');
    uploading.current = true; setBusy(true); value.setStaging(true);
    try {
      const r = await send();
      if (!mounted.current || generation.current !== mine || latest.current[which]?.image !== previous
        || latest.current.references.map((r) => r.name).join('|') !== previousRefs) return [];
      if (!r.image) throw new Error('The server returned no guide image.');
      latest.current.update({ [which]: { image: r.image, ratio: r.ratio } });
      return [key];
    } catch (e) { if (mounted.current) toast.error(e?.message || 'The guide could not be prepared.'); return []; }
    finally { if (generation.current === mine) { uploading.current = false; if (mounted.current) setBusy(false); latest.current.setStaging(false); } }
  };
  const guide = (which, file) => {
    if (!file) return;
    const form = new FormData(); form.append('image', file);
    return prepareGuide(which, () => postForm(sourceUrl(), form));
  };
  // ✂ A staged video cut to an interval: the server prepares a new reference
  // from the staged copy and the card swaps it in place — same tag, same
  // role, same format choice. Never while another preparation runs.
  const cut = async (reference, start, duration) => {
    if (uploading.current || disabled) return;
    const mine = ++generation.current;
    uploading.current = true; setBusy(true); value.setStaging(true); setNotice('');
    try {
      const r = await postJson(referenceUrl(), cutBody(reference, start, duration));
      if (!mounted.current || generation.current !== mine) return;
      if (!r?.reference?.name) throw new Error('The server returned no reference.');
      if (!latest.current.references.some((x) => x.name === reference.name)) { setNotice(`${reference.tag} was removed while it was being cut.`); return; }
      latest.current.setReferences((list) => replaceReference(list, reference.name, r.reference));
      setNotice(`${reference.tag} cut to ${Number(r.reference.duration).toFixed(1)} s.`);
    } catch (e) { if (mounted.current) setNotice(`${reference.tag}: ${e?.message || 'The video could not be cut.'}`); }
    finally { if (generation.current === mine) { uploading.current = false; if (mounted.current) setBusy(false); latest.current.setStaging(false); } }
  };
  const guideTarget = libraryTarget === 'firstFrame' || libraryTarget === 'endFrame';
  const libraryPicker = libraryTarget && <ReferenceLibraryPicker key={libraryTarget} kind={guideTarget ? 'image' : libraryTarget}
    targetLabel={guideTarget ? `${libraryTarget === 'firstFrame' ? 'first' : 'last'} frame guide` : undefined}
    limit={guideTarget ? 1 : Math.max(0, cap[libraryTarget] - refs.filter((r) => r.kind === libraryTarget).length)}
    heldKeys={guideTarget ? [] : refs.map(referenceLibraryKey)} disabled={busy || disabled} onClose={() => setLibraryTarget(null)}
    onAdd={(selections) => guideTarget
      ? prepareGuide(libraryTarget, () => postJson(sourceUrl(), { library_source: selections[0].item.source, frame: selections[0].frame }), librarySelectionKey('image', selections[0]))
      : adoptLibrary(libraryTarget, selections)} />;

  return (
    <section data-probe-panel="video-studio-references" className="flex min-w-0 flex-col gap-3 rounded-xl border border-border bg-surface p-3">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-sm font-semibold text-content">References</h2>
        <HelpBadge topic={identitiesOnly ? 'video-first-frame-refmods' : 'video-studio-references'} />
        <span className="text-xs text-content-subtle">{identitiesOnly ? 'Identity images · start and end frames are optional.' : 'One clip combining all your reference images, videos and audio.'}</span>
      </div>
      <p className="text-xs text-content-muted">{identitiesOnly ? 'Images added here are automatically encoded as identity RefMods. Give each a role and name its tag in the motion. No start or end frame is required: the prompt describes the scene. Add a start or end frame only to fix its composition. Remove all references to generate without RefMods.' : 'Keep a person, outfit or object from pictures, borrow motion from a video, or use an audio reference. Give each a role, then name its tag in the motion.'}</p>
      <div className={`grid gap-2 ${identitiesOnly ? 'grid-cols-1' : 'grid-cols-3'}`}>
        {MEDIA.filter(row => !identitiesOnly || row.kind === 'image').map(({ kind, label, accept, Icon }) => {
          const count = refs.filter((r) => r.kind === kind).length;
          return (
            <div key={kind} className="flex min-w-0 flex-col gap-1 rounded-lg border border-dashed border-border p-1">
              <label className={`relative flex min-h-20 min-w-0 flex-col items-center justify-center gap-1 rounded-md px-1 py-2 text-xs text-content ${busy || disabled || count >= cap[kind] ? 'opacity-50' : 'cursor-pointer hover:bg-surface-raised'}`}>
              <Icon aria-hidden="true" className="h-4 w-4" />
              <span>{label} · {count}{Number.isFinite(cap[kind]) ? `/${cap[kind]}` : ''}</span>
              <span className="text-content-muted">Upload</span>
              <input type="file" aria-label={`Add reference ${label.toLowerCase()}`} accept={accept} multiple
                disabled={busy || disabled || count >= cap[kind]}
                className="absolute inset-0 w-full cursor-pointer opacity-0"
                onChange={(e) => { upload(kind, e.target.files); e.target.value = ''; }} />
              </label>
              <button type="button" data-testid={`reference-library-${kind}`} aria-label={`Choose ${kind} references from library`} disabled={busy || disabled || count >= cap[kind]} aria-expanded={libraryTarget === kind}
                className={`${BUTTON} flex min-w-0 items-center justify-center gap-1`} onClick={() => setLibraryTarget(libraryTarget === kind ? null : kind)}><Library aria-hidden="true" className="h-3.5 w-3.5 shrink-0" />Library</button>
            </div>
          );
        })}
      </div>
      {!guideTarget && libraryPicker}
      {!identitiesOnly && <p className="text-[0.6875rem] text-content-subtle">Videos: 2–15 s, prepared at 24 fps. Audio: 0.2–15 s. Video sound is off until you include it below. H3 uses video frames from the beginning of each reference, up to the generated clip length.</p>}
      <div role="status" aria-live="polite" className="text-xs text-content-muted">{busy ? 'Preparing references…' : notice}</div>
      <div className="min-w-0 space-y-2">
        {rows.map((r) => {
          const siblings = rows.filter((x) => x.kind === r.kind);
          const at = siblings.findIndex((x) => x.name === r.name);
          return (
            <article key={r.name} className="flex min-w-0 flex-col gap-2 rounded-lg border border-border bg-app p-2 sm:flex-row" data-testid="video-reference">
              <div className="flex w-full shrink-0 items-center justify-center sm:w-32">
                {r.kind === 'audio' ? <audio src={referenceUrl(r.name)} controls preload="metadata" className="h-10 w-full min-w-0" aria-label={r.role || r.tag} />
                  : <ReferenceMediaPreview kind={r.kind} src={referenceUrl(r.name)} label={r.tag} description={r.role || r.source_label} />}
              </div>
              <fieldset disabled={busy || disabled} className="flex min-w-0 flex-1 flex-col gap-2 disabled:opacity-60">
                <div className="flex flex-wrap items-center gap-1">
                  {[r.tag, r.audioTag].filter(Boolean).map((tag) => <button key={tag} type="button" className={`${BUTTON} font-mono text-primary`} onClick={() => onInsertTag(tag)} title="Insert this tag in the motion">{tag}</button>)}
                  {r.duration > 0 && <span className="text-[0.6875rem] text-content-subtle">{Number(r.duration).toFixed(1)} s</span>}
                  <span className="ml-auto flex gap-1">
                    <button type="button" className={BUTTON} disabled={at === 0} aria-label={`Move ${r.tag} earlier`} onClick={() => value.setReferences((list) => moveReference(list, r.name, -1))}><ArrowUp className="h-3.5 w-3.5" /></button>
                    <button type="button" className={BUTTON} disabled={at === siblings.length - 1} aria-label={`Move ${r.tag} later`} onClick={() => value.setReferences((list) => moveReference(list, r.name, 1))}><ArrowDown className="h-3.5 w-3.5" /></button>
                    <button type="button" className={BUTTON} aria-label={`Remove ${r.tag}`} onClick={() => remove(r.name)}><Trash2 className="h-3.5 w-3.5" /></button>
                  </span>
                </div>
                {r.source_label && <p className="break-words text-[0.6875rem] text-content-subtle">{r.source_label}{r.frame ? ` · ${r.frame} frame` : Number.isFinite(r.start_seconds) ? ` · from ${r.start_seconds} s` : ''}</p>}
                <label className="flex flex-col gap-1 text-xs text-content-muted">Role of {r.tag}
                  <input value={r.role || ''} maxLength={500} onChange={(e) => change(r.name, { role: e.target.value })} placeholder={r.kind === 'image' ? 'e.g. main character, red outfit, background' : r.kind === 'video' ? 'e.g. camera movement or dance to follow' : 'e.g. voice, rhythm or ambience'} className="min-h-10 w-full rounded-md border border-border bg-surface px-2 text-xs text-content lg:min-h-0 lg:py-1.5" />
                </label>
                {r.kind === 'video' && <label className="flex min-h-10 items-center gap-2 text-xs text-content-muted lg:min-h-0"><input type="checkbox" checked={!!r.include_audio} disabled={r.has_audio === false} onChange={(e) => change(r.name, { include_audio: e.target.checked })} />{r.has_audio === false ? 'This video has no audio track' : 'Include this video’s sound as an audio reference'}</label>}
                {r.kind === 'video' && <>
                  <div className="flex items-center gap-1">
                    <label className="flex min-h-10 flex-1 cursor-pointer items-center gap-2 text-xs text-content-muted lg:min-h-0">
                      <input type="checkbox" aria-label={`Use ${r.tag} format for output`} checked={r.use_format === true}
                        onChange={(e) => { const checked = e.target.checked; value.setReferences((list) => selectReferenceFormat(list, r.name, checked)); }} />
                      <span>Use this video’s format for output{referenceFormatSize(r) && <span className="ml-1 text-content-subtle">· {referenceFormatSize(r)}</span>}</span>
                    </label>
                    <HelpBadge topic="video-reference-format" />
                  </div>
                  {r.use_format === true && <p className="text-[0.6875rem] text-content-subtle">Keeps this video’s proportions. Resolution still follows Render.</p>}
                  <ReferenceCut key={r.name} reference={r} clipSeconds={clipSeconds} disabled={busy || disabled} onCut={(start, duration) => cut(r, start, duration)} />
                </>}
              </fieldset>
            </article>
          );
        })}
      </div>
      <p className="text-[0.6875rem] text-content-subtle">Tags follow the order within each media type. Moving a reference updates its tags in your prompt; removing one marks its old mentions for you to edit.</p>
      {/* Open when a guide is actually set: ⏭ Continue arms the first frame
          guide, and a picture that decides the render must not sit behind a
          closed summary (2026-09-07). Toggling it stays the reader's. */}
      {!identitiesOnly && <details open={!!(value.firstFrame || value.endFrame)} className="rounded-lg border border-border p-2">
        <summary className="min-h-10 cursor-pointer text-xs font-semibold text-content lg:min-h-0">First and last frame guides · optional
          {value.firstFrame?.continues ? ` · ⏭ continuing clip #${value.firstFrame.continues}` : ''}</summary>
        <p className="my-2 text-xs text-content-muted">These pictures anchor the beginning or ending in time. They are separate from the identity references above.</p>
        <div className="grid gap-2 sm:grid-cols-2">
          {['firstFrame', 'endFrame'].map((which) => <div key={which} className="flex min-w-0 flex-col gap-2 rounded-md border border-border p-2">
            <label className="text-xs text-content-muted">{which === 'firstFrame' ? 'First frame guide' : 'Last frame guide'}
              <input type="file" accept="image/*" disabled={busy || disabled} className="mt-2 w-full min-w-0 text-xs" onChange={(e) => { guide(which, e.target.files?.[0]); e.target.value = ''; }} />
            </label>
            <button type="button" className={BUTTON} disabled={busy || disabled} aria-expanded={libraryTarget === which} onClick={() => setLibraryTarget(libraryTarget === which ? null : which)} aria-label={`Choose ${which === 'firstFrame' ? 'first' : 'last'} frame guide from library`}>Library</button>
            {value[which] && <>
              <ReferenceMediaPreview src={`${sourceUrl()}?image=${encodeURIComponent(value[which].image)}`} label={which === 'firstFrame' ? 'First frame guide' : 'Last frame guide'} />
              <button type="button" disabled={busy || disabled} className={BUTTON} onClick={() => value.update({ [which]: null })}>
                {value[which].continues ? `⏭ Last frame of clip #${value[which].continues} · Remove` : '✓ Guide ready · Remove'}
              </button>
            </>}
          </div>)}
        </div>
        {guideTarget && <div className="mt-3">{libraryPicker}</div>}
      </details>}
    </section>
  );
}
