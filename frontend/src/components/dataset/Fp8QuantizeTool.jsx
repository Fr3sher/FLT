import { useEffect, useRef, useState } from 'react';
import { apiFetch } from '../../api/fetchClient';
import { postJson } from '../../hooks/useDataset';

/** Quantize a model you already have on this machine to the fp8 file ComfyUI loads.
 *
 * Same conversion the cloud lane runs on the pod at the end of a dense run — one
 * implementation, one format. This is the manual door for everything else: a
 * 26 GB bf16 full model downloaded from Hugging Face, a dense checkpoint from an
 * earlier run, a large finetune someone shared.
 *
 * The source is never touched: the output is written as `<name>_fp8.safetensors`
 * next to it. Everything the server refuses is refused BEFORE the click — the
 * plan call answers with a reason and the button stays disabled carrying it,
 * because the alternative is an error toast after the user committed.
 */
const fmtGB = (bytes) => (
  typeof bytes === 'number' && bytes > 0 ? `${(bytes / 1e9).toFixed(1)} GB` : '—'
);

export default function Fp8QuantizeTool({ suggestedPath = '', disabled = false }) {
  const [path, setPath] = useState(suggestedPath);
  const [plan, setPlan] = useState(null);
  const [status, setStatus] = useState(null);
  const [busy, setBusy] = useState(false);
  const pollRef = useRef(null);

  // Ask the server what this path would produce, debounced — it reads a few KB
  // of header, so it is cheap enough to run as the user types a path.
  useEffect(() => {
    const value = path.trim();
    if (!value) { setPlan(null); return undefined; }
    const timer = setTimeout(() => {
      postJson('/api/tools/fp8-quantize/plan', { path: value }).then(setPlan);
    }, 400);
    return () => clearTimeout(timer);
  }, [path]);

  const poll = () => {
    apiFetch('/api/tools/fp8-quantize/status')
      .then((r) => r.json())
      .then((state) => {
        setStatus(state);
        if (state?.status !== 'running') {
          clearInterval(pollRef.current);
          pollRef.current = null;
          setBusy(false);
        }
      })
      .catch(() => {});
  };

  useEffect(() => () => clearInterval(pollRef.current), []);

  const start = async () => {
    setBusy(true);
    // postJson never throws: a refusal comes back as { ok: false, error }.
    const res = await postJson('/api/tools/fp8-quantize', { path: path.trim() });
    if (!res?.ok) {
      setBusy(false);
      setStatus({ status: 'error', error: res?.error || 'Quantization could not start.' });
      return;
    }
    setStatus(res.status || { status: 'running' });
    clearInterval(pollRef.current);
    pollRef.current = setInterval(poll, 2000);
  };

  const running = status?.status === 'running' || busy;
  const canStart = !!plan?.ok && !running && !disabled;
  const result = status?.result || null;

  return (
    <div className="rounded-lg border border-sky-300/30 bg-sky-400/10 px-3 py-2 text-sky-50">
      <span className="font-semibold">Quantize an existing model to fp8</span>
      <p className="m-0 mt-1 text-sky-200/75 text-[0.6875rem] leading-relaxed">
        Turns a full-precision checkpoint on this machine into the ~10 GB fp8 file ComfyUI
        loads with the standard Load Diffusion Model node. The source file is never modified —
        the result is written next to it. This is not the same thing as the “quantize” training
        option, which only shrinks the model in memory while it trains and writes no file.
      </p>
      <div className="mt-1.5 flex flex-wrap items-center gap-2">
        <input type="text" value={path} onChange={(event) => setPath(event.target.value)}
          disabled={running || disabled}
          placeholder="Full path to a .safetensors model"
          aria-label="Path of the model file to quantize to fp8"
          className="flex-1 min-w-[12rem] rounded border border-sky-300/40 bg-app/70 px-2 py-1 text-content text-[0.75rem] font-mono disabled:opacity-50" />
        <button type="button" onClick={start} disabled={!canStart}
          className="px-2.5 py-1 rounded-lg bg-primary/20 border border-primary/40 text-white text-[0.75rem] font-semibold disabled:opacity-40">
          {running ? 'Quantizing…' : 'Quantize to fp8'}
        </button>
      </div>

      {plan && !plan.ok && path.trim() && (
        <p className="m-0 mt-1 text-amber-200 text-[0.6875rem]">⚠ {plan.error}</p>
      )}
      {plan?.ok && (
        <p className="m-0 mt-1 text-sky-200/80 text-[0.6875rem]">
          {plan.source_name} ({fmtGB(plan.source_bytes)}) → <span className="font-mono">{plan.destination_name}</span>
          {' '}(~{fmtGB(plan.estimated_bytes)}) · {plan.quantized_tensors} matrices quantized,
          {' '}{plan.kept_tensors} kept in full precision
          {plan.destination_exists ? ' · a file with that name already exists' : ''}
        </p>
      )}
      {running && (
        <p className="m-0 mt-1 text-sky-100 text-[0.6875rem]" role="status">
          Quantizing on the CPU{status?.total ? ` — ${status.done}/${status.total} tensors` : '…'}
        </p>
      )}
      {status?.status === 'done' && result && (
        <p className="m-0 mt-1 text-emerald-200 text-[0.6875rem]" role="status">
          ✓ <span className="font-mono">{status.destination_name}</span> written
          ({fmtGB(result.bytes_after)}) and re-opened successfully — {result.scaled_tensors} scaled
          tensors verified. Move or copy it into your ComfyUI diffusion-models folder to use it.
        </p>
      )}
      {status?.status === 'error' && (
        <p className="m-0 mt-1 text-rose-200 text-[0.6875rem]" role="alert">
          ✗ {status.error || 'Quantization failed.'} The source file was not modified.
        </p>
      )}
    </div>
  );
}
