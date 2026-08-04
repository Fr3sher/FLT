import { useEffect, useRef, useState } from 'react';
import { apiFetch } from '../../api/fetchClient';
import { postJson } from '../../hooks/useDataset';

/** Quantize a model that is already on Hugging Face, without downloading it.
 *
 * Getting the fp8 file from a delivered 26 GB master means pulling 26 GB down
 * and pushing 10 GB back — an hour of home bandwidth for under a minute of
 * arithmetic. This rents a cheap machine for a few minutes to do that round trip
 * on a datacentre link; the user then downloads only the ~10 GB result.
 *
 * The cost and the hard duration cap are shown BEFORE anything is rented, the
 * same contract as a training run.
 */
const fmtGB = (bytes) => (
  typeof bytes === 'number' && bytes > 0 ? `${(bytes / 1e9).toFixed(1)} GB` : '—'
);

export default function CloudQuantizeButton({ repoId, filename = null, disabled = false }) {
  const [plan, setPlan] = useState(null);
  const [state, setState] = useState(null);
  const [asked, setAsked] = useState(false);
  const pollRef = useRef(null);

  useEffect(() => () => clearInterval(pollRef.current), []);

  const poll = () => {
    apiFetch('/api/cloud/quantize/status')
      .then((r) => r.json())
      .then((s) => {
        setState(s);
        if (s?.status !== 'running' && s?.status !== 'provisioning') {
          clearInterval(pollRef.current);
          pollRef.current = null;
        }
      })
      .catch(() => {});
  };

  const askPlan = async () => {
    setAsked(true);
    setPlan(await postJson('/api/cloud/quantize/plan', { repo_id: repoId, filename }));
  };

  const start = async () => {
    // The price shown above is what the user agreed to. Renting re-searches the
    // market, so it travels with the request: a machine that costs materially
    // more than the estimate is reported, never rented behind the user's back.
    const res = await postJson('/api/cloud/quantize', {
      repo_id: repoId, filename, quoted_price_per_hour: plan?.price_per_hour,
    });
    if (!res?.ok) {
      setState({ status: 'error', error: res?.error || 'Could not start.' });
      return;
    }
    setState(res.status || { status: 'provisioning' });
    clearInterval(pollRef.current);
    pollRef.current = setInterval(poll, 5000);
  };

  const running = state?.status === 'running' || state?.status === 'provisioning';
  // What was actually rented — not necessarily the machine that was quoted, since
  // renting re-searches the market.
  const rented = [state?.gpu_name, state?.price_per_hour ? `$${state.price_per_hour}/h` : null]
    .filter(Boolean).join(', ');
  if (!repoId) return null;

  return (
    <div className="mt-1.5">
      {!asked && (
        <button type="button" onClick={askPlan} disabled={disabled}
          title="Rent a machine for a few minutes to build the fp8 file directly in this repository"
          className="rounded-md border border-sky-300/50 bg-sky-400/10 px-2.5 py-1 font-semibold hover:bg-sky-400/20 disabled:opacity-40">
          ☁ Quantize to fp8 in the cloud…
        </button>
      )}
      {asked && plan && !plan.ok && (
        <p className="m-0 opacity-90">⚠ {plan.error}</p>
      )}
      {asked && plan?.ok && !running && state?.status !== 'done' && (
        <div className="rounded-md border border-sky-300/40 bg-sky-400/10 px-2.5 py-1.5">
          <p className="m-0">
            Rents one machine at ${plan.price_per_hour}/h for about {plan.estimated_minutes} min
            (~${plan.estimated_cost}), hard-stopped and destroyed after {plan.max_minutes} min.
            It downloads <span className="font-mono">{plan.weight_name}</span> ({fmtGB(plan.source_bytes)}),
            writes <span className="font-mono">{plan.output_name}</span> (~{fmtGB(plan.output_bytes_typical)})
            into the same repository, and shuts down. You download only the small one.
          </p>
          {plan.storage?.fits === false && (
            <p className="m-0 mt-1 text-amber-200">
              ⚠ Your private Hugging Face storage looks about {fmtGB(plan.storage.shortfall_bytes)} short
              for the new file — free space first, or the upload will be refused.
            </p>
          )}
          <button type="button" onClick={start} disabled={disabled}
            className="mt-1 rounded-md border border-primary/50 bg-primary/20 px-2.5 py-1 font-semibold text-white hover:bg-primary/30 disabled:opacity-40">
            Rent and quantize
          </button>
        </div>
      )}
      {running && (
        <p className="m-0" role="status">
          ☁ {state.status === 'provisioning'
            ? 'Renting a machine…'
            : `Converting on the rented machine${rented ? ` (${rented})` : ''}…`}
          {' '}It is destroyed automatically, at the latest after {plan?.max_minutes || 60} min.
        </p>
      )}
      {state?.status === 'done' && (
        <p className="m-0 text-emerald-200" role="status">
          ✓ <span className="font-mono">{state.output_name}</span> is now in the repository
          ({fmtGB(state.result?.bytes_after)}) and the machine has been destroyed.
        </p>
      )}
      {state?.status === 'error' && (
        <p className="m-0 text-rose-200" role="alert">✗ {state.error}</p>
      )}
    </div>
  );
}
