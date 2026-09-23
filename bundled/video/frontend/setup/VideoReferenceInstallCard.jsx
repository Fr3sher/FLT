import { useEffect, useRef, useState } from 'react';
import { apiFetch, postJson } from '@lds/plugin-sdk';
import { VIDEO_INSTALL_LABELS } from '../lib/videoInstallLabels.js';
import { HelpBadge } from '@lds/plugin-sdk';
import { REFERENCE_BASES } from '../studio/video/VideoReferenceOptions';
import { referenceInstallPlan } from '../studio/video/videoReferenceInstall';

/** One selected reference profile: optional bases never ride into a grouped
 * first install, and shared H3 encoders/VAEs are only fetched when missing. */
export default function VideoReferenceInstallCard({ caps, onDone }) {
  const status = caps?.comfyui?.video_studio_reference;
  const [base, setBase] = useState('official');
  const [accel, setAccel] = useState('ref8');
  const [running, setRunning] = useState(false);
  const [actions, setActions] = useState(null);
  const [states, setStates] = useState({});
  const [message, setMessage] = useState('');
  const mounted = useRef(true);
  const timer = useRef(null);
  const failures = useRef(0);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; clearTimeout(timer.current); }; }, []);
  const plan = referenceInstallPlan(status, base, accel);
  const selection = actions ?? plan;
  const bases = status?.bases || REFERENCE_BASES;
  const coreMissing = (status?.missing_nodes || []).filter((n) => typeof n === 'string' && !n.startsWith('LDS'));
  const settle = (tracked, next) => {
    setStates(next);
    if (tracked.every((a) => ['success', 'error'].includes(next[a]?.state))) {
      setRunning(false);
      setMessage(tracked.some((a) => next[a]?.state === 'error')
        ? 'Some components need attention. Review the failed rows and retry.'
        : tracked.includes('h3_reference_nodes') ? 'Files installed. Restart ComfyUI to load the reference nodes, then refresh Setup.' : 'Downloads finished. Refreshing availability…');
      onDone?.(); return true;
    }
    return false;
  };
  const poll = async (tracked, prepared = {}) => {
    try {
      const data = await apiFetch(`/api/setup/install-all/status?actions=${tracked.join(',')}`);
      if (!mounted.current) return;
      const next = { ...(data.statuses || {}), ...prepared };
      if (tracked.some((a) => !['running', 'queued', 'success', 'error'].includes(next[a]?.state))) {
        setRunning(false);
        setMessage('The installer no longer has this preparation’s progress. Check the connection and retry.');
        return;
      }
      failures.current = 0;
      if (settle(tracked, next)) return;
    } catch (e) {
      if (!mounted.current) return;
      if (++failures.current >= 5) {
        setRunning(false);
        setMessage('Lost contact with the installer. Check the connection and retry.');
        return;
      }
      setMessage(e?.message || 'Could not read progress; trying again.');
    }
    if (mounted.current) timer.current = setTimeout(() => poll(tracked, prepared), 1500);
  };
  const install = async () => {
    if (!plan.length || running) return;
    clearTimeout(timer.current); failures.current = 0;
    setRunning(true); setActions(plan); setStates({}); setMessage('');
    try {
      const result = await postJson('/api/plugins/video/preparation', { actions: plan });
      if (!mounted.current) return;
      if (!Array.isArray(result?.plan) || !result.statuses) throw new Error('The installer returned no preparation plan. Retry.');
      setActions(result.plan);
      const prepared = Object.fromEntries(Object.entries(result.statuses).filter(([, state]) => ['success', 'error'].includes(state?.state)));
      if (!settle(result.plan, result.statuses)) poll(result.plan, prepared);
    }
    catch (e) { if (mounted.current) { setRunning(false); setMessage(e?.message || 'The install could not start.'); } }
  };
  if (!status) return null;
  return (
    <section className="mt-4 flex flex-col gap-2 rounded-xl border border-border bg-app p-3" data-probe-panel="setup-video-references">
      <h3 className="flex items-center gap-2 text-sm font-semibold text-content">Reference-to-video <HelpBadge topic="video-studio-reference-model" /></h3>
      <p className="text-xs text-content-muted">Choose one base and its reference acceleration. Existing H3 prompt encoders and decoders are shared. LightX reference LoRAs are about 1.96 GB each; VDN uses its own stage.</p>
      <div className="grid gap-2 sm:grid-cols-2">
        <label className="flex min-w-0 flex-col gap-1 text-xs text-content-muted">Reference base
          <select value={base} disabled={running} onChange={(e) => { setBase(e.target.value); if (e.target.value === 'fused') setAccel(''); setActions(null); setStates({}); setMessage(''); }} className="min-h-10 min-w-0 rounded-md border border-border bg-surface px-2 text-content">
            {bases.map((b) => <option value={b.id} key={b.id}>{b.label}</option>)}
          </select>
        </label>
        <label className="flex min-w-0 flex-col gap-1 text-xs text-content-muted">Acceleration
          <select value={accel} disabled={running || base === 'fused'} onChange={(e) => { setAccel(e.target.value); setActions(null); setStates({}); setMessage(''); }} className="min-h-10 rounded-md border border-border bg-surface px-2 text-content">
            <option value="ref4">Reference Turbo · 4 steps</option><option value="ref8">Reference Turbo · 8 steps</option><option value="vdn">VDN-H3 hybrid attention · 8 steps</option><option value="">None · dense sampling</option>
          </select>
        </label>
      </div>
      {base === 'fused' && <p className="break-words text-xs text-content-muted">Fused Turbo already includes acceleration. Reuse your {bases.find(b => b.id === 'fused')?.file} in ComfyUI models/diffusion_models; this weight has no automatic download.</p>}
      {accel === 'vdn' && <p className="text-xs text-content-muted">Install the <a href="https://github.com/Saganaki22/ComfyUI-VDN-H3" target="_blank" rel="noopener noreferrer" className="underline">ComfyUI-VDN-H3 node pack by Saganaki22</a> in ComfyUI, then restart it. The selected download below supplies the VDN stage; Sparse stays off.</p>}
      {selection.length > 0 && <ul className="space-y-1 text-xs text-content-muted">
        {selection.map((action) => <li key={action} className="break-words">{VIDEO_INSTALL_LABELS[action] || action}{states[action]?.state ? ` — ${states[action].state}` : ''}
          {states[action]?.error && <span className="block text-red-300">{states[action].error}</span>}</li>)}
      </ul>}
      <button type="button" disabled={!caps.comfyui.dir_valid || running || !plan.length} onClick={install} className="min-h-10 rounded-lg border border-primary px-3 py-2 text-xs font-semibold text-content disabled:opacity-40">
        {running ? 'Installing selected profile…' : plan.length ? `Install ${plan.length} missing component${plan.length === 1 ? '' : 's'}` : 'Selected profile files are installed'}
      </button>
      <p className="text-[0.6875rem] text-content-subtle">The reference helper ships with LDS and installs without pip changes. Restart ComfyUI after its installation. If core MiniMax reference nodes are missing, update ComfyUI too.</p>
      {!!coreMissing.length && <p className="break-words text-xs text-amber-200">Update ComfyUI to provide: {coreMissing.join(', ')}.</p>}
      {message && <p role="status" className="text-xs text-content-muted">{message}</p>}
    </section>
  );
}
