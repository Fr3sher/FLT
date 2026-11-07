/**
 * ⚙ Which model writes the motion — and how it samples.
 *
 * The dials live here and not on the panel for the same reason the model
 * does: they are wanted at the moment somebody wonders why a proposal wanders
 * or repeats itself, not permanently beside two buttons. Two temperatures on
 * purpose (✨ Auto invents from a still and wants room; ✨ Enrich rewrites what
 * was typed and must stay close to it) — one shared dial would break one of
 * them. Every value is clamped SERVER-side and the reply is what is shown, so
 * a 40 typed into a field reads back as 2.0 rather than pretending.
 *
 * How the pictures are READ has its own choice here too (2026-09-05, the
 * maintainer's method, widened to every picture on 2026-09-06): the writer's
 * vision model, or JoyCaption describing each still on its own — the start or
 * last frame, a frame guide, a reference picture, and a reference video as its
 * first, middle and last frame — and handing the descriptions to the writer
 * whole. It sits in this window because it changes what ✨ Auto and ✨ Enrich
 * are given, not what the panel renders — and because JoyCaption runs beside
 * ANY writer, GPT included, so it is not a model in the list.
 *
 * A window rather than a select on the panel: the list is only wanted at the
 * moment somebody wonders about it, and a dropdown of every model a machine has
 * pulled would sit there permanently next to two buttons that do not need it.
 *
 * The list is the PROVIDER's own (the same one every other picker in this app
 * reads), so a model pulled in Ollama a minute ago is simply there. An
 * unreachable server says so and keeps the current choice visible — a picker
 * that emptied itself would read as "you have no models".
 */
import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { apiFetch, putJson } from '@lds/plugin-sdk';
import { useToast } from '@lds/plugin-sdk';
import { useFocusTrap } from '@lds/plugin-sdk/ui';
import { motionDialsUrl, motionModelUrl, motionModelsUrl, motionObserverUrl } from './videoStudioApi';

/* One row per dial, in the order a person tunes them: the two temperatures
   first (the thing people actually reach for), then length, then the sampling
   shape. Bounds come from the server so the slider cannot draw a range the
   provider refuses. */
const DIAL_ROWS = [
  { key: 'temp_auto', label: '✨ Auto temperature', step: 0.05,
    hint: 'How far a proposal may stray from the still. Higher invents more, lower repeats itself.' },
  { key: 'temp_enhance', label: '✨ Enrich temperature', step: 0.05,
    hint: 'How far a rewrite may stray from what you typed. Kept low so Enrich stays yours.' },
  { key: 'max_tokens', label: 'Length (tokens)', step: 10,
    hint: 'The budget the writer gets. 500 fits H3’s three fields with room; past ~1000 a looping model just fills it.' },
  { key: 'top_p', label: 'Top-p', step: 0.05,
    hint: 'Nucleus sampling. Lower narrows the words considered at each step.' },
  { key: 'top_k', label: 'Top-k', step: 1,
    hint: 'Candidates per step. 20 keeps a small model from looping on the field labels.' },
  { key: 'min_p', label: 'Min-p', step: 0.01,
    hint: 'Drops candidates below this share of the top one. 0 = off.' },
  { key: 'presence_penalty', label: 'Presence penalty', step: 0.05,
    hint: 'Pushes the writer away from words it already used. 1.0 shipped.' },
];

export default function MotionModelDialog({ onClose, onSaved }) {
  const toast = useToast();
  const dialogRef = useRef(null);
  useFocusTrap(dialogRef);
  const [state, setState] = useState(null);
  const [picked, setPicked] = useState(null);
  const [busy, setBusy] = useState(false);
  // {dials, defaults, bounds} from the server; `dials` is what the sliders edit.
  const [dialsState, setDialsState] = useState(null);
  // {current, options, joycaption: {ok, detail}} — how reference videos are read.
  const [observerState, setObserverState] = useState(null);
  const [observer, setObserver] = useState(null);
  const dials = dialsState?.dials || null;
  const setDial = (key, value) =>
    setDialsState((cur) => (cur ? { ...cur, dials: { ...cur.dials, [key]: value } } : cur));

  useEffect(() => {
    apiFetch(motionModelsUrl())
      .then((d) => { setState(d); setPicked(d?.current || ''); })
      .catch(() => setState({ models: [], reachable: false, current: '' }));
    apiFetch(motionDialsUrl())
      .then((d) => setDialsState(d))
      .catch(() => setDialsState(null));   // no dials block: the model half still works
    apiFetch(motionObserverUrl())
      .then((d) => { setObserverState(d); setObserver(d?.current || 'vision'); })
      .catch(() => setObserverState(null));   // no reference block either: the rest still works
  }, []);

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape' && !busy) onClose?.(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [busy, onClose]);

  useEffect(() => {
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = previous; };
  }, []);

  const save = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const r = await putJson(motionModelUrl(), { model: picked || '' });
      if (dials && !isGpt) {
        // The reply is the clamped truth; a 40 typed into temperature comes
        // back as 2.0 and the sliders show THAT before the window closes.
        const kept = await putJson(motionDialsUrl(), { dials });
        setDialsState((cur) => (cur ? { ...cur, dials: kept.dials } : cur));
      }
      if (observerState && observer && observer !== observerState.current) {
        // Saved only when it changed: the setting is the maintainer's to test,
        // and a Save that re-wrote it every time would hide a failed switch.
        const kept = await putJson(motionObserverUrl(), { observer });
        setObserverState((cur) => (cur ? { ...cur, current: kept.observer } : cur));
        toast.info(kept.observer === 'joycaption'
          ? 'Pictures, frames and reference videos will be read by JoyCaption.'
          : 'Pictures, frames and reference videos go back to the writer’s vision model.');
      }
      onSaved?.(r.model || '');
      toast.success(r.model
        ? `✨ Motion will be written by ${r.model === state?.chatgpt?.choice ? 'GPT (ChatGPT subscription)' : r.model}.`
        : '✨ Motion goes back to the provider’s own vision model.');
      onClose?.();
    } catch (err) {
      toast.error(err?.message || 'That choice could not be saved.');
    } finally {
      setBusy(false);
    }
  };

  const models = state?.models || [];
  const isGpt = picked === (state?.chatgpt?.choice || 'chatgpt-subscription');
  const joyReady = observerState?.joycaption?.ok === true;

  // Match the Studio's other dialogs: its fixed action bar sits at 9960.
  // A body portal escapes ancestors, but still needs to sit above that bar.
  return createPortal(
    <div ref={dialogRef} role="dialog" aria-modal="true" aria-label="Model that writes the motion"
      data-probe-layer
      className="fixed inset-0 z-[9990] flex items-center justify-center bg-black/80 p-2 sm:p-4"
      onMouseDown={(e) => { if (e.target === e.currentTarget && !busy) onClose?.(); }}>
      <form onSubmit={save}
        className="flex w-full max-w-md max-h-[92vh] flex-col overflow-hidden rounded-xl border border-border bg-surface-overlay shadow-2xl">
        <header className="shrink-0 space-y-1 border-b border-border p-4">
          <h2 className="text-base font-bold text-content">⚙ Model that writes the motion</h2>
          <p className="text-sm text-content-muted">
            Used by ✨ Auto and ✨ Enrich. Its own setting: the image passes keep
            the model you gave them.
          </p>
          {state && (
            <p className="text-xs text-content-subtle">
              {isGpt ? 'Through your ChatGPT subscription' : `Through ${state.label || 'your local LLM'}`}
              {(isGpt ? state.chatgpt?.connected : state.reachable) ? '' : ' — not connected right now'}
            </p>
          )}
        </header>

        <div className="min-h-0 flex-1 space-y-1.5 overflow-y-auto overscroll-contain p-3 sm:p-4">
          {state?.chatgpt && (
            <label className="flex min-h-10 cursor-pointer items-start gap-2 rounded-lg border border-border bg-surface-raised px-3 py-2 text-sm text-content has-[:checked]:border-sky-400/70 has-[:checked]:bg-sky-500/10">
              <input type="radio" name="motion-model" className="mt-0.5"
                checked={isGpt} onChange={() => setPicked(state.chatgpt.choice)} />
              <span className="min-w-0">
                <span className="font-semibold">GPT — ChatGPT subscription</span>
                <span className="block text-xs text-content-muted">
                  {state.chatgpt.connected
                    ? `Connected · ${state.chatgpt.model}. Uses the same subscription as image generation.`
                    : 'Connect ChatGPT in Plugins → API image engines → Settings to use this option.'}
                </span>
                <span className="block text-xs text-content-muted">
                  The frame and your instructions are sent to ChatGPT. No local model needed.
                </span>
              </span>
            </label>
          )}

          <label className="flex cursor-pointer items-start gap-2 rounded-lg border border-border bg-surface-raised px-3 py-2 text-sm text-content has-[:checked]:border-sky-400/70 has-[:checked]:bg-sky-500/10">
            <input type="radio" name="motion-model" className="mt-0.5"
              checked={!picked} onChange={() => setPicked('')} />
            <span className="min-w-0">
              <span className="font-semibold">The provider’s own vision model</span>
              <span className="block text-xs text-content-muted">
                Whatever the image passes use. Nothing extra to keep in step.
              </span>
            </span>
          </label>

          {models.map((m) => (
            <label key={m}
              className="flex cursor-pointer items-start gap-2 rounded-lg border border-border bg-surface-raised px-3 py-2 text-sm text-content has-[:checked]:border-sky-400/70 has-[:checked]:bg-sky-500/10">
              <input type="radio" name="motion-model" className="mt-0.5"
                checked={picked === m} onChange={() => setPicked(m)} />
              <span className="min-w-0 break-all">{m}</span>
            </label>
          ))}

          {state && !models.length && (
            <p className="rounded-lg border border-dashed border-border px-3 py-4 text-xs text-content-muted">
              {state.reachable
                ? 'No model listed — pull one in your local LLM and reopen this.'
                : 'The server did not answer, so its models could not be listed. Your current choice is kept.'}
            </p>
          )}

          {observerState && (
            <section className="mt-3 space-y-1.5 border-t border-border pt-3" data-testid="reference-observer">
              <h3 className="text-sm font-semibold text-content">Pictures, frames and reference videos</h3>
              <p className="text-xs text-content-muted">
                How the start frame, a last frame, the frame guides, the reference pictures
                and the reference videos are read before the writer sees them.
              </p>
              <label className="flex min-h-10 cursor-pointer items-start gap-2 rounded-lg border border-border bg-surface-raised px-3 py-2 text-sm text-content has-[:checked]:border-sky-400/70 has-[:checked]:bg-sky-500/10">
                <input type="radio" name="reference-observer" className="mt-0.5"
                  checked={observer === 'vision'} onChange={() => setObserver('vision')} />
                <span className="min-w-0">
                  <span className="font-semibold">Vision model</span>
                  <span className="block text-xs text-content-muted">
                    The writer’s own vision model describes a still in a few sentences — its
                    reasoning switched off, with a local model — and sums a video up from two
                    frames of the visible portion.
                  </span>
                </span>
              </label>
              <label className={`flex min-h-10 items-start gap-2 rounded-lg border border-border bg-surface-raised px-3 py-2 text-sm text-content has-[:checked]:border-sky-400/70 has-[:checked]:bg-sky-500/10 ${joyReady ? 'cursor-pointer' : 'cursor-not-allowed opacity-60'}`}>
                <input type="radio" name="reference-observer" className="mt-0.5" disabled={!joyReady}
                  checked={observer === 'joycaption'} onChange={() => setObserver('joycaption')} />
                <span className="min-w-0">
                  <span className="font-semibold">JoyCaption</span>
                  <span className="block text-xs text-content-muted">
                    Every still is described on its own by JoyCaption — a frame or a picture
                    in one description, a video as its first, middle and last frame — and
                    handed whole to the writer, which reads the movement between a video’s
                    three. Explicit content is described as it is, nothing softened or
                    replaced. JoyCaption loads when a frame, the references, the writer or the
                    clip length change — about 20 s per described frame on a 24 GB card; the
                    descriptions are kept for ten minutes, like the vision read.
                  </span>
                  {joyReady && observerState.joycaption?.weights_cached === false && (
                    <span className="block text-xs text-amber-200">
                      First press downloads JoyCaption’s ~7 GB model; it is kept afterwards.
                    </span>
                  )}
                  {!joyReady && (
                    <span className="block text-xs text-amber-200">
                      Not available here{observerState.joycaption?.detail ? ` — ${observerState.joycaption.detail}` : ''}.
                      Install JoyCaption from Setup → Captioning.
                    </span>
                  )}
                </span>
              </label>
            </section>
          )}

          {dials && !isGpt && (
            <section className="mt-3 space-y-2 border-t border-border pt-3" data-testid="motion-dials">
              <div className="flex items-center justify-between gap-2">
                <h3 className="text-sm font-semibold text-content">How it writes</h3>
                <button type="button"
                  onClick={() => setDialsState((cur) => (cur ? { ...cur, dials: { ...cur.defaults } } : cur))}
                  className="min-h-10 rounded-md px-2 text-xs text-content-muted underline decoration-dotted hover:text-content lg:min-h-0"
                  title="Back to the shipped values">
                  ↺ Defaults
                </button>
              </div>
              {DIAL_ROWS.map(({ key, label, hint, step }) => {
                const [lo, hi] = dialsState.bounds[key];
                const v = dials[key];
                return (
                  <label key={key} className="block rounded-lg border border-border bg-surface-raised px-3 py-2 text-sm text-content">
                    <span className="flex items-center justify-between gap-2">
                      <span className="font-medium">{label}</span>
                      <input type="number" value={v} min={lo} max={hi} step={step}
                        onChange={(e) => setDial(key, e.target.value === '' ? v : Number(e.target.value))}
                        aria-label={`${label} (number)`}
                        className="w-20 rounded border border-border bg-app/60 px-1.5 py-0.5 text-right tabular-nums text-content" />
                    </span>
                    <input type="range" value={v} min={lo} max={hi} step={step}
                      onChange={(e) => setDial(key, Number(e.target.value))}
                      aria-label={label} className="mt-1 w-full" />
                    <span className="block text-xs text-content-muted">{hint}</span>
                  </label>
                );
              })}
            </section>
          )}
        </div>

        <div className="shrink-0 border-t border-border p-3">
          <div className="flex flex-wrap justify-end gap-2">
            <button type="button" onClick={onClose} disabled={busy}
              className="min-h-10 rounded-md border border-border px-3 py-1.5 text-sm text-content-muted hover:bg-surface-raised hover:text-content disabled:opacity-50 lg:min-h-0">
              Cancel
            </button>
            <button type="submit" disabled={busy || picked === null}
              className="min-h-10 rounded-md bg-gradient-primary px-4 py-1.5 text-sm font-semibold text-gray-950 disabled:opacity-50 lg:min-h-0">
              {busy ? 'Saving…' : 'Save'}
            </button>
          </div>
        </div>
      </form>
    </div>,
    document.body,
  );
}
