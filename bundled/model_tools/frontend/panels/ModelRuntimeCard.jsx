import { useCallback, useEffect, useRef, useState } from 'react';
import { apiFetch } from '@lds/plugin-sdk';
import { InstallRunner } from '@lds/plugin-sdk/ui';

export function ModelRuntimeState({ runtime, error, loading, onRefresh, installationState }) {
  const environment = runtime?.environment;
  const installerNeedsAttention = ['queued', 'running', 'error'].includes(installationState);
  const compact = runtime?.ready && environment?.ready && !error && !installerNeedsAttention;
  return <section className="space-y-3 rounded-lg border border-border p-3" aria-label="Model tools CPU engine">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <h3 className="text-sm font-semibold text-content">CPU engine</h3>
      <span className="text-xs text-content-muted">{loading ? 'Checking…' : runtime?.ready ? 'Ready' : 'Not ready'}</span>
    </div>
    <p className="text-sm text-content-muted">Install Python, PyTorch and NumPy for local quantization and LoRA merging. Both tools share this plugin’s isolated engine. No GPU or other plugin is required.</p>
    {error && <p role="alert" className="text-sm text-error">{error}</p>}
    {runtime?.ready && <p className="text-sm text-content">PyTorch {runtime.torch_version} · CPU checked · {runtime.source === 'override' ? 'selected Python override' : 'Model tools managed engine'}</p>}
    {runtime?.reason && <p className="text-sm text-content-muted">{runtime.reason}</p>}
    {runtime?.source === 'override' && <p className="text-xs text-content-muted">The saved Python override stays selected. To use the managed engine, clear the override below and save changes.</p>}
    <div className="flex flex-wrap items-start gap-2">
      {environment?.action && (environment.can_install || installerNeedsAttention) && <details open={!compact}
        className="min-w-0 flex-1 space-y-2">
        <summary className="cursor-pointer text-xs text-content">Repair and installation logs</summary>
        <InstallRunner action={environment.action}
          buttonLabel={environment.ready ? 'Repair CPU engine' : 'Install CPU engine'} onDone={onRefresh} />
      </details>}
      <button type="button" className="rounded-md border border-border px-3 py-1.5 text-xs text-content disabled:opacity-50"
        disabled={loading} onClick={onRefresh}>Check again</button>
    </div>
    {environment && !environment.can_install && !environment.ready && environment.reason && <p className="text-xs text-content-muted">{environment.reason}</p>}
  </section>;
}

export default function ModelRuntimeCard() {
  const [runtime, setRuntime] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [installationState, setInstallationState] = useState(null);
  const mounted = useRef(false);
  const load = useCallback(async (refresh = false) => {
    setLoading(true);
    try {
      const value = await apiFetch(`/api/tools/model-runtime${refresh ? '?refresh=1' : ''}`);
      const installation = value.environment?.action
        ? await apiFetch(`/api/setup/install/${value.environment.action}/status`).catch(() => null) : null;
      if (mounted.current) { setRuntime(value); setInstallationState(installation?.state || null); setError(null); }
    } catch (err) {
      if (mounted.current) { setRuntime(null); setError(err.message || 'Could not check the CPU engine. Try again.'); }
    } finally {
      if (mounted.current) setLoading(false);
    }
  }, []);
  useEffect(() => { mounted.current = true; load(); return () => { mounted.current = false; }; }, [load]);
  return <ModelRuntimeState runtime={runtime} error={error} loading={loading} installationState={installationState}
    onRefresh={() => load(true)} />;
}
