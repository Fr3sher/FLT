import { HelpBadge } from '@lds/plugin-sdk';
import { referenceBaseMissing } from './videoPerformance.js';

export const REFERENCE_BASES = [
  { id: 'official', label: 'MiniMax H3 Reference · INT8', hint: 'Original reference model, about 21 GB.' },
  { id: 'light', label: 'MiniMax H3 Reference · W4A8', hint: 'About 12.5 GB on disk. Lower weight memory; compare identity and detail on your references.' },
  { id: 'eros', label: '10Eros Reference · INT8', hint: 'A third-party finetune, about 22.5 GB. Its appearance may change an identity test.' },
];
const REF_ACCEL = [
  { id: 'ref4', label: 'LightX2V Reference · 4 steps', steps: 4 },
  { id: 'ref8', label: 'LightX2V Reference · 8 steps', steps: 8 },
  { id: 'vdn', label: 'VDN-H3 hybrid attention · 8 steps', steps: 8,
    hint: 'OpenVDN hybrid attention via ComfyUI-VDN-H3. Sparse is off; compare reference fidelity and motion. One GPU per video.' },
];

export default function VideoReferenceOptions({ options, value, onChange, onRefresh, performance }) {
  const bases = options?.bases || REFERENCE_BASES;
  const accels = options?.accelerations || REF_ACCEL;
  const base = bases.find((b) => b.id === value.base);
  const accel = accels.find((a) => a.id === value.accel);
  const remote = options?.remote;
  const select = 'min-h-10 w-full rounded-md border border-border bg-app px-2 py-1 text-xs text-content lg:min-h-0';
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2 text-sm font-semibold text-content">Reference model <HelpBadge topic="video-studio-reference-model" /></div>
      <label className="flex flex-col gap-1 text-xs text-content-muted">Base
        <select value={value.base} onChange={(e) => onChange({ base: e.target.value, fused: false, ...(e.target.value === 'fused' ? { accel: '', steps: '' } : {}) })} className={select}>
          {bases.map((b) => <option key={b.id} value={b.id}>{b.label}{!remote && b.available === false ? ' — needs Setup' : ''}</option>)}
        </select>
      </label>
      <p className="text-[0.6875rem] text-content-subtle">{base?.hint || REFERENCE_BASES.find((b) => b.id === value.base)?.hint}</p>
      <label className="flex flex-col gap-1 text-xs text-content-muted">Reference acceleration
        <select disabled={value.base === 'fused'} value={value.accel || ''} onChange={(e) => onChange({ accel: e.target.value, steps: '', ...(e.target.value === 'vdn' ? { h3_attention: 'native', h3_spectrum: false, sparse: '' } : {}) })} className={select}>
          <option value="">Off · dense reference model</option>
          {accels.map((a) => <option key={a.id} value={a.id}>{a.label}{!remote && a.available === false ? ' — needs Setup' : ''}</option>)}
        </select>
      </label>
      <p className="text-[0.6875rem] text-content-subtle">{accel?.hint || (value.accel ? 'A distillation made for reference conditioning. Compare its speed and fidelity with the dense model.' : 'Use the undistilled reference base for comparison.')}</p>
      {value.accel === 'vdn' && <p className="text-[0.6875rem] text-content-subtle">Use the VDN stage from Setup and the <a href="https://github.com/Saganaki22/ComfyUI-VDN-H3" target="_blank" rel="noopener noreferrer" className="underline">ComfyUI-VDN-H3 pack by Saganaki22</a>. Its Turbo adapter replaces LightX acceleration.</p>}
      <label className="flex flex-col gap-1 text-xs text-content-muted">Reference image detail
        <select value={value.imageSize} onChange={(e) => onChange({ imageSize: e.target.value })} className={select}>
          <option value="match">Match output size</option>
          <option value="max">More reference detail · higher memory use</option>
        </select>
      </label>
      <p className="text-[0.6875rem] text-content-subtle">More detail keeps references up to a 2048 px short edge. Every reference adds work at every sampling step.</p>
      {remote && <p className="text-xs text-content-muted">Prepare the rented GPU above to install this model and acceleration there.</p>}
      {!remote && (referenceBaseMissing(base, value, performance) || accel?.available === false) && (
        <div role="status" className="rounded-lg border border-amber-400/40 bg-amber-400/10 p-2 text-xs text-amber-200">
          The selected reference profile needs files or nodes. Open Plugins → Video lane → Settings → Preparation to install them, then refresh this panel.
          {!!options?.missing_nodes?.length && <p className="mt-1 break-words">{options.missing_nodes.map((n) => typeof n === 'string' ? n : n.label || n.class_type || n.name).filter(Boolean).join(', ')}</p>}
        </div>
      )}
      {onRefresh && <button type="button" onClick={onRefresh} className="min-h-10 rounded-md border border-border px-2 py-1 text-xs text-content-muted hover:text-content lg:min-h-0">Refresh availability</button>}
    </div>
  );
}
