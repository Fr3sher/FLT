/**
 * ⚖ LoRA bench — judge a LoRA you downloaded, without building a dataset.
 *
 * Three stacked steps (pick a file → confirm its activation word → sweep its
 * strength) and a results grid. Stacked rather than side-by-side because this is
 * read on a phone as often as on a desktop: at 400 px every step is full width
 * and nothing scrolls sideways except the grid, which says so.
 *
 * It generates through the Test Studio's engine — the run is created by
 * `lora_test_studio.create_run` with a strict SUBSET of its parameters, and it
 * is polled and cancelled through `/api/studio/run/<id>/…`. There is no second
 * generation path here, and there must not become one: if a "bench this LoRA"
 * shortcut is ever wanted from the Canvas, it is a link to this page.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { HelpBadge } from '../help/HelpMode';
import { apiFetch, postJson } from '../api/fetchClient';
import { useCapabilities } from '../context/CapabilitiesContext';
import {
  SWEEP_CAVEAT, bestStrength, cellsAt, filterLoras, groupByFamily, isLowConfidence,
  launchBlocker, runCheckpoint, scoreAt, strengthsOf, toggleStrength, triggerNotice,
} from './bench/benchModel';

const STRENGTH_CHOICES = [0.2, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.2, 1.5];
const POLL_MS = 2500;
const fmt = (v) => (Number.isInteger(v) ? v.toFixed(1) : String(v));

export default function BenchPage() {
  const { caps } = useCapabilities();
  const [data, setData] = useState(null);
  const [query, setQuery] = useState('');
  const [picked, setPicked] = useState(null);
  const [info, setInfo] = useState(null);
  const [trigger, setTrigger] = useState('');
  const [noTrigger, setNoTrigger] = useState(false);
  const [strengths, setStrengths] = useState([0.4, 0.6, 0.8, 1.0]);
  const [prompt, setPrompt] = useState('');
  const [seed, setSeed] = useState('');
  const [runId, setRunId] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const runIdRef = useRef(null);
  runIdRef.current = runId;

  const refresh = useCallback(async () => {
    const qs = runIdRef.current ? `?run=${encodeURIComponent(runIdRef.current)}` : '';
    const body = await apiFetch(`/api/bench/status${qs}`);
    if (body) setData(body);
    return body;
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const run = data && data.run;
  const running = !!(run && run.pending > 0);
  // Poll only while something is rendering — a bench that finished must not keep
  // a tab awake (same rule the Studio follows).
  useEffect(() => {
    if (!runId || !running) return undefined;
    const t = setInterval(() => { refresh(); }, POLL_MS);
    return () => clearInterval(t);
  }, [runId, running, refresh]);

  const pick = async (entry) => {
    setPicked(entry); setError(null); setInfo(null); setTrigger(''); setNoTrigger(false);
    const body = await apiFetch(
      `/api/bench/trigger?filename=${encodeURIComponent(entry.filename)}`);
    if (body) { setInfo(body); setTrigger(body.trigger || ''); }
  };

  const notice = useMemo(() => triggerNotice(info), [info]);
  const groups = useMemo(
    () => groupByFamily(filterLoras(data && data.loras, query), data && data.families),
    [data, query]);
  const scores = (data && data.scores) || [];
  // Scores follow the run ON SCREEN, not the file selected in the picker: open
  // an earlier bench of another LoRA and the picker still shows whatever you
  // clicked last, so scoring against it would star a strength measured for a
  // different file.
  const shown = runCheckpoint(run);
  const best = shown ? bestStrength(scores, shown) : null;
  const thin = shown ? isLowConfidence(scores, shown) : false;
  const blocker = launchBlocker({
    filename: picked && picked.filename, strengths, trigger, noTrigger,
    running, gpuBusy: data && data.gpu_busy,
  });

  const launch = async () => {
    setBusy(true); setError(null);
    try {
      const body = await postJson('/api/bench/run', {
        filename: picked.filename, strengths, trigger, no_trigger: noTrigger,
        prompt: prompt.trim() || undefined,
        seed: seed.trim() ? Number(seed.trim()) : undefined,
      });
      if (body && body.run_id) {
        setRunId(body.run_id);
        runIdRef.current = body.run_id;
        setSeed(String(body.seed));
        await refresh();
      }
    } catch (e) {
      setError((e && e.message) || 'Could not start the bench run.');
    } finally { setBusy(false); }
  };

  const rate = async (cellId, rating) => {
    await postJson(`/api/dataset/lora-test/image/${cellId}/rate`, { rating });
    await refresh();
  };

  const cancel = async () => {
    if (!runId) return;
    await postJson(`/api/studio/run/${runId}/cancel`, {});
    await refresh();
  };

  if (!caps.studio_visible) {
    return (
      <div className="rounded-xl border border-border bg-surface p-8 text-center">
        <h1 className="text-lg font-semibold text-content">LoRA bench</h1>
        <p className="mt-2 text-sm text-content-muted">
          LoRA bench renders through ComfyUI — configure it in Settings.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4 pb-8">
      <header className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <h1 className="text-lg font-semibold text-content">
          <span aria-hidden>⚖</span> LoRA bench
        </h1>
        <HelpBadge topic="page-bench" />
        <p className="w-full text-sm text-content-muted">
          Test a LoRA you downloaded — no dataset, no training. Pick a file already in
          ComfyUI, then sweep its strength on one prompt.
        </p>
      </header>

      {error && (
        <p role="alert" className="rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-300">
          {error}
        </p>
      )}
      {data && data.gpu_busy && (
        <p role="status" className="rounded-lg border border-amber-400/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-200">
          {data.gpu_busy}
        </p>
      )}

      {/* ---- 1. the file ------------------------------------------------ */}
      <section className="rounded-xl border border-border bg-surface p-3 sm:p-4">
        <h2 className="text-sm font-semibold text-content">1 · Pick a LoRA</h2>
        {data && data.loras.length === 0 ? (
          // The first screen someone with a fresh download sees. "Nothing to
          // show" would be a dead end: name the folders the app reads.
          <p className="mt-2 text-sm text-content-muted">{data.folder_hint}</p>
        ) : (
          <>
            <label className="sr-only" htmlFor="bench-search">Search LoRA files</label>
            <input id="bench-search" type="search" value={query} placeholder="Search by file name…"
              onChange={(e) => setQuery(e.target.value)}
              className="mt-2 w-full rounded-lg border border-border bg-surface-raised px-3 py-2 text-sm text-content" />
            <div className="mt-2 max-h-64 overflow-y-auto flex flex-col gap-2">
              {groups.map((g) => (
                <div key={g.family}>
                  <p className="text-[0.625rem] uppercase tracking-wide text-content-subtle">
                    {g.label} · models/loras/{g.folder}
                  </p>
                  <ul className="mt-1 flex flex-col gap-1">
                    {g.loras.map((l) => (
                      <li key={l.filename}>
                        <button type="button" onClick={() => pick(l)}
                          aria-pressed={!!picked && picked.filename === l.filename}
                          className={`w-full text-left rounded-lg px-2 py-1.5 text-sm break-all ${
                            picked && picked.filename === l.filename
                              ? 'bg-primary/20 text-content outline outline-1 outline-primary/60'
                              : 'text-content-muted hover:bg-surface-raised'}`}>
                          {l.name}
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
              {groups.length === 0 && (
                <p className="text-sm text-content-subtle">No file matches “{query}”.</p>
              )}
            </div>
          </>
        )}
      </section>

      {/* ---- 2. the activation word -------------------------------------- */}
      {picked && (
        <section className="rounded-xl border border-border bg-surface p-3 sm:p-4">
          <h2 className="text-sm font-semibold text-content">2 · Activation word</h2>
          <label className="sr-only" htmlFor="bench-trigger">Activation word</label>
          <input id="bench-trigger" type="text" value={trigger} disabled={noTrigger}
            onChange={(e) => setTrigger(e.target.value)}
            placeholder="e.g. zoeydoll"
            className="mt-2 w-full rounded-lg border border-border bg-surface-raised px-3 py-2 text-sm text-content disabled:opacity-40" />
          <p className={`mt-2 text-xs ${notice.state === 'metadata' ? 'text-content-muted' : 'text-amber-300'}`}>
            {notice.text}
          </p>
          {info && info.candidates && info.candidates.length > 0 && (
            <div className="mt-2">
              <p className="text-[0.6875rem] text-content-subtle">
                Most frequent training tags — often, but not always, the activation word.
                Nothing here is filled in for you: the top tag of a character LoRA is
                routinely a generic one.
              </p>
              <div className="mt-1 flex flex-wrap gap-1">
                {info.candidates.map((c) => (
                  <button key={c.tag} type="button" disabled={noTrigger}
                    onClick={() => setTrigger(c.tag)}
                    className="rounded-full border border-border px-2 py-0.5 text-[0.6875rem] text-content-muted hover:bg-surface-raised disabled:opacity-40">
                    {c.tag} <span className="text-content-subtle tabular-nums">×{c.count}</span>
                  </button>
                ))}
              </div>
            </div>
          )}
          <label className="mt-3 flex items-start gap-2 text-xs text-content-muted">
            <input type="checkbox" checked={noTrigger} className="mt-0.5"
              onChange={(e) => { setNoTrigger(e.target.checked); if (e.target.checked) setTrigger(''); }} />
            <span>This LoRA has no activation word (a style or utility LoRA usually has none).</span>
          </label>
        </section>
      )}

      {/* ---- 3. the sweep ------------------------------------------------ */}
      {picked && (
        <section className="rounded-xl border border-border bg-surface p-3 sm:p-4">
          <h2 className="text-sm font-semibold text-content">3 · Strength sweep</h2>
          <div className="mt-2 flex flex-wrap gap-1">
            {STRENGTH_CHOICES.map((v) => (
              <button key={v} type="button"
                onClick={() => setStrengths((cur) => toggleStrength(cur, v, data ? data.max_strengths : 8))}
                aria-pressed={strengths.includes(v)}
                className={`rounded-lg px-2 py-1 text-xs tabular-nums ${
                  strengths.includes(v)
                    ? 'bg-primary/20 text-content outline outline-1 outline-primary/60'
                    : 'text-content-muted hover:bg-surface-raised'}`}>
                {fmt(v)}
              </button>
            ))}
          </div>
          <label className="mt-3 block text-xs text-content-muted" htmlFor="bench-prompt">Prompt</label>
          <textarea id="bench-prompt" rows={2} value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="Leave empty for a plain close-up portrait with the activation word."
            className="mt-1 w-full rounded-lg border border-border bg-surface-raised px-3 py-2 text-sm text-content" />
          <div className="mt-3 flex flex-wrap items-end gap-2">
            <div className="min-w-0">
              <label className="block text-xs text-content-muted" htmlFor="bench-seed">Seed</label>
              <input id="bench-seed" type="text" inputMode="numeric" value={seed}
                onChange={(e) => setSeed(e.target.value.replace(/[^0-9]/g, ''))}
                placeholder="random"
                className="mt-1 w-28 rounded-lg border border-border bg-surface-raised px-2 py-1.5 text-sm text-content tabular-nums" />
            </div>
            <p className="text-xs text-content-subtle">
              {strengths.length} image{strengths.length === 1 ? '' : 's'} · same prompt, same seed
            </p>
            <button type="button" disabled={!!blocker || busy} onClick={launch}
              title={blocker || undefined}
              className="ml-auto rounded-lg bg-gradient-primary px-3 py-1.5 text-sm font-semibold text-white disabled:opacity-40">
              <span aria-hidden>🚀</span> Run bench
            </button>
          </div>
          {blocker && <p className="mt-2 text-xs text-amber-300">{blocker}</p>}
        </section>
      )}

      {/* ---- results ----------------------------------------------------- */}
      {run && (
        <section className="rounded-xl border border-border bg-surface p-3 sm:p-4">
          <div className="flex flex-wrap items-baseline gap-2">
            <h2 className="text-sm font-semibold text-content">Results</h2>
            {running && (
              <span role="status" className="text-xs text-content-muted">
                {run.pending} left…
              </span>
            )}
            {running && (
              <button type="button" onClick={cancel}
                className="ml-auto rounded-lg border border-border px-2 py-1 text-xs text-content-muted hover:bg-surface-raised">
                Stop
              </button>
            )}
          </div>
          {/* Wide content scrolls inside its own box; the page body never does. */}
          <div className="mt-2 overflow-x-auto">
            <div className="flex items-start gap-2">
              {strengthsOf(run).map((s) => {
                const cells = cellsAt(run, s);
                const score = shown ? scoreAt(scores, shown, s) : null;
                return (
                  <div key={s} className={`shrink-0 rounded-lg p-1 ${
                    best === s ? 'bg-amber-400/10 outline outline-1 outline-amber-400/50' : ''}`}>
                    <p className="text-center text-[0.6875rem] tabular-nums text-content-muted">
                      {fmt(s)}{best === s && <span title="Best so far" aria-label="best so far"> ★</span>}
                    </p>
                    {cells.map((c) => (
                      <div key={c.id} className="mt-1 w-28 sm:w-36">
                        {c.filename ? (
                          // The CELL's own dataset id, not the run's first
                          // entry: the image route is id-scoped, and reading it
                          // off the row that owns the file cannot go stale.
                          <img alt={`Rendered at strength ${fmt(s)}`}
                            src={`/api/dataset/${c.dataset_id}/img/${encodeURIComponent(c.filename)}`}
                            className="w-full rounded-md" />
                        ) : (
                          // A failed cell carries the reason ComfyUI gave; show
                          // it rather than a mute box — an empty square in a
                          // strength sweep otherwise reads as "the LoRA broke
                          // here", which is the wrong conclusion.
                          <div title={c.error || undefined}
                            className="flex aspect-[9/16] w-full items-center justify-center rounded-md border border-border px-1 text-center text-[0.625rem] text-content-subtle">
                            {c.status === 'failed' ? (c.error || 'failed') : '…'}
                          </div>
                        )}
                        {c.filename && (
                          <div className="mt-1 flex justify-center gap-1">
                            <button type="button" aria-label={`Like strength ${fmt(s)}`}
                              aria-pressed={c.rating === 1}
                              onClick={() => rate(c.id, c.rating === 1 ? 0 : 1)}
                              className={`rounded px-1 text-xs ${c.rating === 1 ? 'bg-emerald-500/25' : 'hover:bg-surface-raised'}`}>👍</button>
                            <button type="button" aria-label={`Dislike strength ${fmt(s)}`}
                              aria-pressed={c.rating === -1}
                              onClick={() => rate(c.id, c.rating === -1 ? 0 : -1)}
                              className={`rounded px-1 text-xs ${c.rating === -1 ? 'bg-red-500/25' : 'hover:bg-surface-raised'}`}>👎</button>
                          </div>
                        )}
                      </div>
                    ))}
                    {score && score.voted > 0 && (
                      <p className="mt-1 text-center text-[0.625rem] tabular-nums text-content-subtle">
                        {score.voted}/{score.images} voted
                        {score.low_confidence && <span className="text-amber-400" title="Few votes — low reliability"> ⚠</span>}
                      </p>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
          {thin && (
            <p className="mt-2 text-xs text-amber-300">
              Fewer than 3 votes on every strength — the ★ is a hint, not a ranking yet.
            </p>
          )}
          {/* The limit stays visible. A ranking is not a verdict. */}
          <p className="mt-2 text-xs text-content-subtle">{SWEEP_CAVEAT}</p>
        </section>
      )}

      {/* ---- history ----------------------------------------------------- */}
      {data && data.runs.length > 0 && (
        <section className="rounded-xl border border-border bg-surface p-3 sm:p-4">
          <div className="flex flex-wrap items-baseline gap-2">
            <h2 className="text-sm font-semibold text-content">Earlier benches</h2>
            <button type="button"
              onClick={async () => { await postJson('/api/bench/clear', {}); setRunId(null); runIdRef.current = null; await refresh(); }}
              className="ml-auto rounded-lg border border-border px-2 py-1 text-xs text-content-muted hover:bg-surface-raised">
              Clear bench history
            </button>
          </div>
          <ul className="mt-2 flex flex-col gap-1">
            {data.runs.map((r) => (
              <li key={r.run_id}>
                <button type="button"
                  onClick={() => { setRunId(r.run_id); runIdRef.current = r.run_id; refresh(); }}
                  className="w-full rounded-lg px-2 py-1.5 text-left text-xs text-content-muted hover:bg-surface-raised">
                  <span className="break-all text-content">{r.label}</span>
                  {' · '}{r.strengths.map(fmt).join(' / ')}
                  {' · '}{r.done}/{r.total} done
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
