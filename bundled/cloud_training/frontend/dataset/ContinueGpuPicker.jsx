import { useEffect, useState } from 'react';

// The continuation uses the same live tiers and price cap as a fresh launch.
// Only hourly prices are shown: the checkpoint's remaining work is different
// from the fresh-run duration estimated by the offers endpoint.
export default function ContinueGpuPicker({ datasetId, trainType, variant,
  trainingMode = 'lora', value, onChange, busy = false }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setData(null);
    setError(null);
    onChange(null);
    const qs = new URLSearchParams({ training_mode: trainingMode });
    if (trainType) qs.set('train_type', trainType);
    if (variant) qs.set('variant', variant);
    (async () => {
      try {
        const response = await fetch(`/api/dataset/${datasetId}/train/cloud/offers?${qs}`, {
          credentials: 'include',
        });
        const body = await response.json();
        if (!response.ok || body.ok === false) {
          throw new Error(body.error || body.hint || `Could not load GPU offers (HTTP ${response.status})`);
        }
        if (alive) setData(body);
      } catch (err) {
        if (alive) setError(err.message || 'Could not load GPU offers');
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, [datasetId, trainType, variant, trainingMode, reload, onChange]);

  const tiers = data?.tiers || [];
  return (
    <div className="flex flex-col gap-1.5 rounded-lg border border-border bg-surface-raised p-2.5">
      <label className="flex items-center gap-2 flex-wrap text-[0.75rem] text-content">
        <span className="w-28 shrink-0">Cloud GPU</span>
        <select aria-label="Cloud GPU for the continuation" value={value || ''}
          disabled={busy || loading || !tiers.length}
          onChange={(event) => onChange(event.target.value || null)}
          className="min-w-0 max-w-full flex-1 px-2 py-1 rounded-lg border border-border bg-surface text-content disabled:opacity-40">
          <option value="">{loading ? 'Loading GPU offers…' : 'Choose a GPU…'}</option>
          {tiers.map((tier) => (
            <option key={tier.gpu_name} value={tier.gpu_name}>
              {tier.gpu_name}{tier.gpu_ram_gb ? ` · ${tier.gpu_ram_gb} GB` : ''}
              {tier.dph_total != null ? ` · $${Number(tier.dph_total).toFixed(3)}/h` : ''}
            </option>
          ))}
        </select>
      </label>
      {error && <span role="alert" className="text-red-300 text-[0.6875rem]">{error}</span>}
      {!loading && !error && !tiers.length && (
        <span className="text-amber-300 text-[0.6875rem]">
          No GPU available{data?.max_price_per_hour != null ? ` under $${data.max_price_per_hour}/h` : ''}.
          {' '}Refresh offers or adjust the price cap in Cloud training settings.
        </span>
      )}
      <div className="flex items-center gap-2 text-[0.6875rem]">
        <span className="text-content-subtle">Live hourly prices; availability is checked again at launch.</span>
        <button type="button" disabled={busy || loading} onClick={() => setReload((n) => n + 1)}
          className="ml-auto shrink-0 text-indigo-300 disabled:opacity-40">Refresh offers</button>
      </div>
    </div>
  );
}
