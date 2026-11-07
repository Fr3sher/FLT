import { useEffect, useRef, useState } from 'react';
import { apiFetch, postJson } from '@lds/plugin-sdk';

function Prepare({ action, label, onRefresh, restart = true }) {
  const [state, setState] = useState(null);
  const [error, setError] = useState('');
  const timer = useRef(null);
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; clearTimeout(timer.current); }; }, []);
  const poll = async () => {
    try {
      const result = await apiFetch(`/api/setup/install/${action}/status`);
      if (!mounted.current) return;
      setState(result.state);
      if (result.state === 'error') setError(result.error || result.log?.at(-1) || 'Installation failed. Retry.');
      else if (result.state === 'success') onRefresh?.();
      else if (['running', 'queued'].includes(result.state)) timer.current = setTimeout(poll, 1500);
      else { setState('error'); setError('Installation progress unavailable. Retry.'); }
    } catch (e) { if (mounted.current) { setState('error'); setError(e.message); } }
  };
  const start = async () => {
    setState('running'); setError('');
    try { await postJson(`/api/setup/install/${action}`, {}); if (mounted.current) poll(); }
    catch (e) { if (mounted.current) { setState('error'); setError(e.message); } }
  };
  return <div className="text-xs text-content-muted">
    {state === 'success' ? <span>{restart ? 'Installed — restart ComfyUI after your renders finish, then refresh.' : 'Download complete — refresh availability.'}</span>
      : <button type="button" onClick={start} disabled={['running', 'queued'].includes(state)} className="min-h-10 text-primary underline disabled:opacity-50">{['running', 'queued'].includes(state) ? 'Preparing…' : label}</button>}
    {error && <p role="alert" className="break-words text-red-300">{error}</p>}
  </div>;
}

export default function VideoPerformanceOptions({ options, value, onChange, referenceMode, onRefresh }) {
  const status = options?.performance || {};
  const remote = options?.reference?.remote;
  const fused = referenceMode ? value.base === 'fused' : !!value.fused;
  const select = 'min-h-10 w-full min-w-0 rounded-md border border-border bg-app px-2 text-xs text-content';
  const enableAttention = (patch) => onChange({ ...patch, sparse: '', ...(value.accel === 'vdn' ? { accel: '', steps: '' } : {}) });
  const needs = (key, selected) => selected && !remote && status[key]?.available === false;
  return <div className="flex min-w-0 flex-col gap-2 border-t border-border pt-3" data-testid="video-performance">
    <h3 className="text-sm font-semibold text-content">Performance</h3>
    {!referenceMode && <label className="flex min-h-10 items-center gap-2 text-sm text-content">
      <input type="checkbox" checked={fused} onChange={(e) => onChange({ fused: e.target.checked, accel: '', eros: false, light: false, steps: '' })} />
      H3 Fused Turbo
    </label>}
    {fused && <p className="text-xs text-content-muted">Turbo is already merged; no acceleration LoRA. Auto uses 8 steps.</p>}
    {needs('fused', fused) && <p role="status" className="break-words text-xs text-amber-200">Place your Fused weight in ComfyUI models/diffusion_models, then refresh: {status.fused.filename}. No automatic download is configured for this weight.</p>}
    <label className="flex flex-col gap-1 text-xs text-content-muted">H3 attention
      <select aria-label="H3 attention" className={select} value={value.h3_attention || 'auto'} onChange={(e) => e.target.value === 'sage' ? enableAttention({ h3_attention: 'sage' }) : onChange({ h3_attention: e.target.value })}>
        <option value="auto">Automatic · existing backend</option><option value="native">Native · PyTorch</option><option value="sage">H3 SageAttention</option>
      </select>
    </label>
    <label className="flex min-h-10 items-center gap-2 text-xs text-content">
      <input type="checkbox" checked={!!value.h3_spectrum} onChange={(e) => e.target.checked ? enableAttention({ h3_spectrum: true }) : onChange({ h3_spectrum: false })} /> Spectrum · forecast intermediate steps
    </label>
    <p className="text-[0.6875rem] text-content-subtle">Sage and Spectrum can run together. They turn off Sparse and VDN. Spectrum can change detail and motion; compare the result with the same seed.</p>
    <label className="flex flex-col gap-1 text-xs text-content-muted">Video decoding
      <select aria-label="Video decoding" className={select} value={value.h3_video_vae || 'fp16'} onChange={(e) => onChange({ h3_video_vae: e.target.value })}>
        <option value="fp16">FP16 VAE</option><option value="int8">INT8 VAE · less weight memory</option>
      </select>
    </label>
    <label className="flex flex-col gap-1 text-xs text-content-muted">MP4 recording
      <select aria-label="MP4 recording" className={select} value={value.h3_video_writer || 'native'} onChange={(e) => onChange({ h3_video_writer: e.target.value })}>
        <option value="native">Native writer</option><option value="fast">Fast H.264 · veryfast / CRF 16</option>
      </select>
    </label>
    <p className="text-[0.6875rem] text-content-subtle">Fast recording keeps audio and completes the MP4 before making it playable. It speeds up saving, not sampling.</p>
    {needs('sage', value.h3_attention === 'sage') && <><p role="status" className="text-xs text-amber-200">{status.sage.hint}</p><Prepare action={status.sage.action} label="Install H3 attention switch" onRefresh={onRefresh} /></>}
    {needs('spectrum', value.h3_spectrum) && <Prepare action={status.spectrum.action} label="Install Spectrum" onRefresh={onRefresh} />}
    {needs('int8', value.h3_video_vae === 'int8') && <Prepare action={status.int8.action} label="Download INT8 video VAE" restart={false} onRefresh={onRefresh} />}
    {needs('fast', value.h3_video_writer === 'fast') && <Prepare action={status.fast.action} label="Install fast MP4 writer" onRefresh={onRefresh} />}
    {onRefresh && <button type="button" className="min-h-10 rounded-md border border-border px-2 text-xs text-content-muted" onClick={onRefresh}>Refresh performance availability</button>}
  </div>;
}
