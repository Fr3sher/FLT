import { useEffect, useMemo, useRef, useState } from 'react';
import { Download, LockKeyhole, Search, ShoppingBag } from 'lucide-react';
import Presentation from './Presentation';

const BTN = 'min-h-10 rounded-md border border-border px-3 py-2 text-sm font-medium hover:bg-surface-raised disabled:opacity-50';

export default function Catalog({ catalog, installed, updatesOnly = false, busy, onPlan, onUnlock, selectedId = '', onClearSelection, loading = false, onRetry }) {
  const [search, setSearch] = useState('');
  const products = useMemo(() => (catalog?.products || []).filter((product) => {
    if (updatesOnly && !product.update_available) return false;
    if (selectedId && product.id !== selectedId) return false;
    const manifest = (product.recommended || product.releases?.[0])?.manifest || {};
    return `${manifest.name} ${manifest.description}`.toLowerCase().includes(search.toLowerCase());
  }), [catalog, search, updatesOnly, selectedId]);

  return <div className="space-y-4" data-store-catalog>
    {selectedId && <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-primary/40 p-3 text-sm">
      <p>The plugin selected in your setup plan</p>
      <button type="button" onClick={onClearSelection} className={BTN}>Show all plugins</button>
    </div>}
    <label className="flex min-h-11 items-center gap-2 rounded-lg border border-border bg-surface px-3">
      <Search className="h-4 w-4 text-content-muted" aria-hidden="true" />
      <input type="search" className="min-h-10 min-w-0 flex-1 bg-transparent py-2 text-sm outline-none"
        aria-label="Search plugins" placeholder="Find a plugin…" value={search} onChange={(event) => setSearch(event.target.value)} />
    </label>
    {(catalog?.status !== 'ready' || loading) && <div className="space-y-3 rounded-lg border border-border p-4 text-sm text-content-muted">
      <p role="status">{loading ? 'Connecting to the plugin catalog…' : catalog?.message || 'Connecting to the plugin catalog…'}</p>
      {catalog && onRetry && <button type="button" className={BTN} disabled={busy || loading} onClick={onRetry}>
        {loading ? 'Retrying catalog…' : 'Retry catalog'}
      </button>}
    </div>}
    <div className="grid gap-4 md:grid-cols-2">
      {products.map((product) => {
        const release = product.recommended || product.releases[0];
        const manifest = release.manifest;
        const local = installed.find((item) => item.id === product.id);
        const incompatible = release.compatibility_issues.length > 0;
        const pending = Boolean(local?.pending_action);
        const paid = release.price.kind === 'paid';
        const needsAdmin = catalog.can_manage === false && !pending && !incompatible;
        return <article key={product.id} data-store-product={product.id} className="flex min-w-0 flex-col rounded-xl border border-border bg-surface p-5">
          <Presentation key={manifest.version} release={release} />
          <div className="flex flex-wrap items-start justify-between gap-2">
            <h2 className="text-base font-semibold">{manifest.name}</h2>
            <span className="rounded-full bg-surface-raised px-2 py-1 text-xs text-content-muted">
              {local ? `Installed · ${local.installed_version || local.version}` : paid ? 'Paid plugin' : 'Free'}
            </span>
          </div>
          <p className="mt-1 text-xs text-content-muted">{manifest.publisher?.name || manifest.author} · {manifest.version}</p>
          <p className="mt-3 flex-1 text-sm leading-relaxed text-content-muted">{manifest.description}</p>
          {incompatible && <p className="mt-3 text-sm text-amber-500">{release.compatibility_issues[0].message}</p>}
          <details className="mt-3 text-sm">
            <summary className="min-h-10 cursor-pointer py-2 font-medium">Details and requirements</summary>
            <div className="space-y-2 border-t border-border pt-2 text-content-muted">
              {manifest.experience?.surfaces?.length > 0 && <p>Included in: {manifest.experience.surfaces.join(', ')}.</p>}
              {manifest.experience?.setup_hint && <p>{manifest.experience.setup_hint}</p>}
              {manifest.requires?.length > 0 && <p>Needs: {manifest.requires.join(', ')}</p>}
              {(manifest.models?.length > 0 || manifest.node_packs?.length > 0 || manifest.requirements) &&
                <p>Some functions need additional models or tools. These are configured separately after installation.</p>}
              {manifest.permissions?.length > 0 && <p>Access: {manifest.permissions.join(', ')}</p>}
              {manifest.license && <p>License: {manifest.license}</p>}
              {release.changelog?.length > 0 && <ul className="list-disc space-y-1 pl-5">{release.changelog.map((entry, i) => <li key={i}>{entry}</li>)}</ul>}
              {local?.error && <p className="text-amber-500">{local.error}</p>}
            </div>
          </details>
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <button type="button" className={BTN + ' inline-flex items-center gap-2'}
              disabled={busy || pending || incompatible || catalog.status !== 'ready' || (!catalog.can_manage && !(needsAdmin && onUnlock))}
              onClick={() => needsAdmin ? onUnlock?.() : onPlan(product.id, manifest.version)}>
              {needsAdmin ? <LockKeyhole className="h-4 w-4" aria-hidden="true" />
                : paid && !local ? <ShoppingBag className="h-4 w-4" aria-hidden="true" /> : <Download className="h-4 w-4" aria-hidden="true" />}
              {needsAdmin ? 'Unlock installation' : pending ? 'Change pending' : product.update_available ? 'Review update' : local ? 'Reinstall' : paid ? 'Review purchase' : 'Install'}
            </button>
            {local && <span className="text-xs text-content-muted">{local.active ? 'Active now' : 'Inactive'}</span>}
          </div>
        </article>;
      })}
    </div>
    {catalog && products.length === 0 && <p className="py-6 text-sm text-content-muted">
      {search ? 'No plugin matches your search.' : updatesOnly ? 'No compatible update is available in this catalog.'
        : catalog.status === 'ready' ? 'No plugin has been published in this catalog yet.' : 'Your installed plugins remain available in My plugins.'}
    </p>}
  </div>;
}

export function InstallPlan({ plan, busy, onConfirm, onCancel, onAcquire }) {
  const panelRef = useRef(null);
  useEffect(() => {
    // The review sits above the catalog, often outside the viewport of the
    // clicked card. Move to each new plan, without stealing focus on busy updates.
    const panel = panelRef.current;
    if (!panel) return;
    panel.scrollIntoView({ block: 'center' });
    panel.focus({ preventScroll: true });
  }, [plan]);
  const purchase = plan.purchase_required?.length > 0;
  return <section ref={panelRef} role="region" aria-label="Review plugin installation" tabIndex={-1} className="space-y-4 rounded-xl border border-primary/40 bg-surface p-5" data-store-plan>
    <h2 className="text-lg font-semibold">{purchase ? 'Review your plugins' : 'Ready to install'}</h2>
    <ul className="divide-y divide-border">
      {plan.packages.map(({ manifest, action, will_enable: willEnable, previous_version: previousVersion, reason, remains_disabled: remainsDisabled }) => <li key={manifest.id} className="py-3">
        <p className="font-medium">{manifest.name} <span className="text-sm text-content-muted">{manifest.version}</span></p>
        <p className="mt-1 text-sm text-content-muted">{action === 'enable' ? 'Enable the installed plugin' : previousVersion && previousVersion !== manifest.version ? `Replace installed version ${previousVersion}` : 'Download this complete plugin'}{willEnable ? ' and activate it after restarting.' : '.'}</p>
        {reason === 'compatibility_update' && <p className="mt-1 text-sm text-content-muted">This update is needed for the selected plugins to work together. {remainsDisabled ? 'This plugin will stay disabled.' : 'Its activation setting is kept.'}</p>}
        {manifest.permissions?.length > 0 && <p className="mt-1 text-xs text-content-muted">Access: {manifest.permissions.join(', ')}</p>}
      </li>)}
    </ul>
    <p className="text-sm text-content-muted">Your data is kept. The current features stay available until you apply the changes and restart LDS.</p>
    {purchase && <p role="status" className="text-sm text-content-muted">Open Purchases to connect this installation, activate a license or review the purchase terms for: {plan.purchase_required.join(', ')}.</p>}
    {plan.paid_packages?.length > 0 && !purchase && <p className="text-sm text-content-muted">Your acquisition is linked. Download eligibility for these versions will be verified before preparing the installation.</p>}
    <div className="flex flex-wrap gap-2">
      <button type="button" disabled={busy || purchase} className={BTN + ' border-primary bg-primary text-primary-foreground'} onClick={onConfirm}>{busy ? 'Preparing…' : 'Confirm installation'}</button>
      {purchase && onAcquire && <button type="button" disabled={busy} className={BTN} onClick={() => onAcquire(plan.purchase_required[0])}>Open purchases</button>}
      <button type="button" disabled={busy} className={BTN} onClick={onCancel}>Cancel</button>
    </div>
  </section>;
}
