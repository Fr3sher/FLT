import { useCallback, useEffect, useRef, useState } from 'react';
import { Puzzle, RefreshCw, Trash2, Upload } from 'lucide-react';
import { apiFetch, fetchWithCsrfRetry, postJson, postForm, del } from '../api/fetchClient';
import { useToast } from '../components/common/Toast';
import { Card, SectionHeader } from '../components/settings/primitives';
import { pluginWhatsNew } from '../plugins/registry.js';
import { sortedEntries } from '../whatsNew.js';
import InstallRunner from '../components/setup/InstallRunner';
import { pendingLabel, pluginActive, pluginDesired, waitForPluginBoot } from '../plugins/lifecycle.js';
import { Link, useSearchParams } from 'react-router';
import { pluginSettingsPath } from './pluginSettings.js';
import Catalog, { InstallPlan } from './store/Catalog.jsx';
import { useCapabilities } from '../context/CapabilitiesContext';
import { productReadiness } from '../plugins/readiness.js';
import Library from './store/Library.jsx';
import Administration from './store/Administration.jsx';

// Store packages bring their screens, services and help together. The running
// registry remains authoritative until a prepared transaction restarts LDS.

const BTN = 'min-h-10 lg:min-h-0 rounded-md border border-border px-3 py-1.5 text-sm font-medium transition-colors hover:bg-surface-raised disabled:opacity-50';
const BTN_PRIMARY = BTN + ' border-primary bg-primary text-primary-foreground hover:bg-primary/90';

const STATE_LABEL = {
  loaded: 'Active now', disabled: 'Inactive', pending: 'Not active yet', error: 'Failed to load', incompatible: 'Incompatible', misplaced: 'Misplaced',
};

function stateClass(state) {
  if (state === 'loaded') return 'text-emerald-500';
  if (state === 'disabled') return 'text-content-muted';
  return 'text-amber-500';
}

export function PluginRow({ plugin, restart, onToggle, onRemove, onInstalled, busy, caps, capsKnown = false }) {
  const requires = plugin.requires || [];
  const news = sortedEntries(pluginWhatsNew(plugin.id));
  const desired = pluginDesired(plugin);
  const pending = pendingLabel(plugin);
  const removing = plugin.pending_action === 'remove';
  const packagePending = ['install', 'update', 'remove'].includes(plugin.pending_action);
  const readiness = pluginActive(plugin) && capsKnown ? productReadiness(plugin.id, caps) : [];
  return (
    <li id={'plugin-row-' + plugin.id} data-plugin-id={plugin.id} className="flex flex-col gap-2 border-t border-border py-3 first:border-t-0 md:flex-row md:items-start md:gap-4">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium">{plugin.name}</span>
          <span className="text-xs text-content-muted">{plugin.version}</span>
          <span className="rounded border border-border px-1.5 py-0.5 text-[0.65rem] uppercase tracking-wide text-content-muted">
            {plugin.official ? 'LDS' : plugin.bundled ? 'Included' : 'External'}
          </span>
          <span className={'text-xs font-medium ' + stateClass(plugin.state)}>{pluginActive(plugin) ? 'Active now' : STATE_LABEL[plugin.state] || plugin.state}</span>
        </div>
        {pending && <p className="mt-2 rounded-md border border-primary/30 bg-primary/10 px-2 py-1 text-sm text-content" data-plugin-pending>{pending}</p>}
        {plugin.description && <p className="mt-1 text-sm text-content-muted">{plugin.description}</p>}
        {pluginActive(plugin) && plugin.package_contract?.experience && <div className="mt-3 space-y-2">
          <div className="flex flex-wrap gap-2">
            {plugin.package_contract.experience.entrypoints.map(entry => <Link key={entry.path} to={entry.path} className={BTN}>{entry.label}</Link>)}
            {plugin.package_contract.experience.setup && <Link to={plugin.package_contract.experience.setup.path} className={BTN}>
              {plugin.package_contract.experience.setup.label}
            </Link>}
          </div>
          {plugin.package_contract.experience.setup_hint && <p className="text-sm text-content-muted">{plugin.package_contract.experience.setup_hint}</p>}
        </div>}
        {plugin.error && <p className="mt-1 text-xs text-amber-500">{plugin.error}</p>}
        {pluginActive(plugin) && !capsKnown && <p className="text-xs text-content-muted">Checking configured components…</p>}
        {readiness.length > 0 && <details className="mt-2 text-sm" data-plugin-readiness>
          <summary className="min-h-10 cursor-pointer py-2 font-medium">Configured components · {readiness.filter(row => row.state === 'ready').length}/{readiness.length} ready</summary>
          <ul className="space-y-2 rounded-md border border-border p-3">
            {readiness.map((row, index) => <li key={index}>
              <span className="font-medium">{row.label}</span>{' · '}
              <span className={row.state === 'ready' ? 'text-emerald-500' : 'text-content-muted'}>
                {{ ready: 'Ready', pending: 'Waiting for the local service', setup: 'Needs setup', unknown: 'Check unavailable' }[row.state]}
              </span>
              {(row.note || row.what) && <p className="mt-1 text-xs text-content-muted">{row.note || row.what}</p>}
            </li>)}
          </ul>
        </details>}
        {plugin.disabled_by && plugin.disabled_by.length > 0 && (
          <p className="mt-1 text-xs text-content-muted">Off because it needs: {plugin.disabled_by.join(', ')}</p>
        )}
        {requires.length > 0 && <p className="mt-1 text-xs text-content-muted">Requires: {requires.join(', ')}</p>}
        {plugin.permissions && plugin.permissions.length > 0 && (
          <p className="mt-1 text-xs text-content-muted">Declares: {plugin.permissions.join(', ')}</p>
        )}
        {plugin.environment && (
          <div className="mt-3 space-y-2 rounded-md border border-border p-3 [&_button]:min-h-10 lg:[&_button]:min-h-0">
            <p className="text-sm font-medium">Python environment · {plugin.environment.ready ? 'Ready' : 'Needs installation'}</p>
            <p className="text-xs text-content-muted">Installs this plugin’s CPU dependencies in its own environment. Installation logs appear here; keep LDS open until it finishes.</p>
            {plugin.environment.reason && <p className="text-xs text-content-muted">{plugin.environment.reason}</p>}
            {plugin.environment.can_install && (
              <InstallRunner action={plugin.environment.action}
                buttonLabel={plugin.environment.ready ? 'Repair Python environment' : 'Install Python environment'}
                onDone={onInstalled} />
            )}
          </div>
        )}
        {news.length > 0 && (
          <details className="mt-2" data-probe-reading>
            <summary className="min-h-10 cursor-pointer py-2 text-sm font-medium lg:min-h-0">
              What’s new in {plugin.name}
            </summary>
            <ol className="max-h-96 space-y-4 overflow-y-auto rounded-md border border-border p-3">
              {news.map((entry) => (
                <li key={entry.id} className="break-words text-sm">
                  <time className="text-xs text-content-muted" dateTime={entry.date}>{entry.date}</time>
                  <p className="font-medium">{entry.title}</p>
                  <p className="mt-1 text-content-muted">{entry.blurb}</p>
                </li>
              ))}
            </ol>
          </details>
        )}
      </div>
      <div className="flex shrink-0 flex-wrap items-center gap-2">
        <Link to={pluginSettingsPath(plugin.id)} className={BTN}>Settings</Link>
        {plugin.state !== 'misplaced' && plugin.state !== 'incompatible' && (
          <button type="button" className={BTN} disabled={busy || removing}
            onClick={() => onToggle(plugin, !desired)}
            aria-pressed={desired}>
            {plugin.pending_action === 'enable' || plugin.pending_action === 'disable' ? 'Undo change' : desired ? 'Turn off' : 'Turn on'}
          </button>
        )}
        {!plugin.bundled && (
          <button type="button" className={BTN} disabled={busy || packagePending}
            title={packagePending ? 'Apply the pending package change before removing this plugin' : 'Remove this plugin (its data is kept for reinstalling)'}
            onClick={() => onRemove(plugin)}>
            <span className="inline-flex items-center gap-1"><Trash2 aria-hidden="true" className="h-3.5 w-3.5" /> Remove</span>
          </button>
        )}
      </div>
      {restart && <span className="sr-only">{restart.how}</span>}
    </li>
  );
}

export default function PluginsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const toast = useToast();
  const { caps, known: capsKnown, refresh: refreshCaps } = useCapabilities();
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [applying, setApplying] = useState(false);
  const [applyError, setApplyError] = useState('');
  const [consent, setConsent] = useState(null);
  const [tab, setTab] = useState(() => ['discover', 'installed', 'updates', 'purchases'].includes(searchParams.get('tab'))
    ? searchParams.get('tab') : 'discover');
  const [catalog, setCatalog] = useState(null);
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [storePlan, setStorePlan] = useState(null);
  const [purchaseId, setPurchaseId] = useState('');
  const [adminToken, setAdminToken] = useState('');
  const [adminDraft, setAdminDraft] = useState('');
  const fileRef = useRef(null);
  const restartAbort = useRef(null);
  const scrolledPlugin = useRef('');
  const catalogRequest = useRef(null);
  const catalogAdminToken = useRef('');
  const requestedPlugin = searchParams.get('plugin') || '';
  const requestedTab = searchParams.get('tab');
  useEffect(() => {
    if (['discover', 'installed', 'updates', 'purchases'].includes(requestedTab)) setTab(requestedTab);
  }, [requestedTab]);
  useEffect(() => {
    if (tab === 'installed' && requestedPlugin && data && scrolledPlugin.current !== requestedPlugin) {
      const element = document.getElementById('plugin-row-' + requestedPlugin);
      if (element) { element.scrollIntoView({ block: 'nearest' }); scrolledPlugin.current = requestedPlugin; }
    }
  }, [tab, requestedPlugin, data]);

  const load = useCallback(async () => {
    try {
      const next = await apiFetch('/api/plugins/', { cache: 'no-store' });
      if (next.boot_id && window.lds?.bootId && next.boot_id !== window.lds.bootId) {
        window.location.reload();
        return;
      }
      setData(next);
      setError('');
    } catch (e) {
      setError(e?.message || 'Could not read the plugin list.');
    }
  }, []);

  const loadCatalog = useCallback(async () => {
    // A completed mutation may still hold the callback for an older token.
    if (adminToken !== catalogAdminToken.current) return;
    const request = {};
    catalogRequest.current = request;
    setCatalogLoading(true);
    try {
      // A catalog outage belongs to this panel, not LDS's shared connection
      // indicator. Keep the usual API error handling for every other request.
      const response = await fetchWithCsrfRetry('/api/plugins/store/catalog', { cache: 'no-store',
        headers: adminToken ? { 'X-LDS-Plugin-Admin': adminToken } : {} });
      if (!response.ok) throw new Error('Catalog request failed');
      const next = await response.json();
      if (!next || !Array.isArray(next.products) || typeof next.status !== 'string') throw new Error('Invalid catalog response');
      if (request === catalogRequest.current) setCatalog(next);
    } catch {
      if (request === catalogRequest.current) setCatalog(previous => ({ status: 'unavailable',
        products: previous?.products || [],
        message: 'The plugin catalog could not be loaded. Check your connection and retry. Your installed plugins remain available in My plugins.' }));
    } finally {
      if (request === catalogRequest.current) setCatalogLoading(false);
    }
  }, [adminToken]);
  const unlockAdministration = (event) => {
    event.preventDefault();
    catalogAdminToken.current = adminDraft;
    catalogRequest.current = null;
    // Old permissions must not survive a change of credentials, even while the
    // new request is pending. Product descriptions remain safe to browse.
    setCatalog(previous => previous ? { ...previous, status: 'unavailable', can_manage: false } : null);
    if (adminToken === adminDraft) loadCatalog();
    else setAdminToken(adminDraft);
  };
  const adminOptions = { headers: adminToken ? { 'X-LDS-Plugin-Admin': adminToken } : {} };
  const mutation = (url, body) => postJson(url, body, adminOptions);
  const upload = (form) => postForm('/api/plugins/install', form, adminOptions);

  const planInstall = async (id, version) => {
    setBusy(true);
    try {
      setStorePlan(await mutation('/api/plugins/store/plan', { id, version }));
    } catch (e) {
      toast.error(e?.message || 'Could not prepare this installation.');
    } finally { setBusy(false); }
  };
  const installFromStore = async () => {
    setBusy(true);
    try {
      await mutation('/api/plugins/store/install', { id: storePlan.requested, version: storePlan.version, plan_id: storePlan.plan_id });
      setStorePlan(null);
      setTab('installed');
      await load();
      await loadCatalog();
      toast.success('Plugins downloaded. Apply the changes to use them.');
    } catch (e) { toast.error(e?.message || 'Installation could not be prepared.'); }
    finally { setBusy(false); }
  };

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    loadCatalog();
    return () => { catalogRequest.current = null; };
  }, [loadCatalog]);
  useEffect(() => () => restartAbort.current?.abort(), []);

  const apply = async () => {
    setBusy(true);
    setApplying(true);
    setApplyError('');
    const controller = new AbortController();
    restartAbort.current = controller;
    try {
      const result = await mutation('/api/plugins/apply', {});
      if (!result.ok || !result.restarting) throw new Error(result.error || 'The restart could not be started.');
      await waitForPluginBoot(result.boot_id || data?.boot_id, { signal: controller.signal });
      window.location.reload();
    } catch (e) {
      if (!controller.signal.aborted) setApplyError(e?.message || 'Could not restart LDS.');
    } finally {
      if (!controller.signal.aborted) {
        setBusy(false);
        setApplying(false);
      }
    }
  };

  const toggle = async (plugin, on) => {
    setBusy(true);
    try {
      await mutation(`/api/plugins/${encodeURIComponent(plugin.id)}/${on ? 'enable' : 'disable'}`, {});
      setApplyError('');
      await load();
    } catch (e) {
      toast.error(e?.message || 'Could not change the plugin.');
    } finally {
      setBusy(false);
    }
  };

  const remove = async (plugin) => {
    if (!window.confirm(`Remove ${plugin.name} after restarting? Its data will be kept and reused when you reinstall it.`)) return;
    setBusy(true);
    try {
      await del(`/api/plugins/${encodeURIComponent(plugin.id)}`, adminOptions);
      setApplyError('');
      await load();
    } catch (e) {
      toast.error(e?.message || 'Could not remove the plugin.');
    } finally {
      setBusy(false);
    }
  };

  const inspect = async (file) => {
    if (!file) return;
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const res = await upload(fd);
      setConsent({ file, manifest: res.manifest, install_dir: res.install_dir,
        can_install: res.can_install === true,
        compatibility_issues: Array.isArray(res.compatibility_issues) ? res.compatibility_issues : [] });
    } catch (e) {
      toast.error(e?.message || 'That archive is not a plugin.');
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  const confirmInstall = async (replace = false) => {
    if (!consent?.can_install) return;
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append('file', consent.file);
      fd.append('confirm', '1');
      if (replace) fd.append('replace', '1');
      await upload(fd);
      toast.success(`${consent.manifest.name} is ready to apply. Restart LDS to use it.`);
      setConsent(null);
      setApplyError('');
      await load();
    } catch (e) {
      if (/already installed/i.test(e?.message || '') && !replace) {
        if (window.confirm(`${consent.manifest.name} is already installed. Replace it?`)) return confirmInstall(true);
        return;
      }
      toast.error(e?.message || 'Install failed.');
    } finally {
      setBusy(false);
    }
  };

  const plugins = data?.plugins || [];
  const bundled = plugins.filter((p) => p.bundled);
  const external = plugins.filter((p) => !p.bundled);
  const restart = data?.restart;
  const pendingRestart = Boolean(data?.pending_restart);

  return (
    <div className="mx-auto max-w-4xl space-y-6 px-4 py-6" data-probe-panel="plugins" data-probe-content="plugin-store">
      <div className="space-y-2">
        <SectionHeader eyebrow="Plugins" title="Plugin store"
          description="Add the tools you need. Each plugin brings its features, interface and help together." />
        <p className="flex flex-wrap items-center gap-2 text-xs text-content-muted">
          <Puzzle aria-hidden="true" className="h-3.5 w-3.5" />
          Your data stays with LDS when a plugin is updated or removed.
        </p>
      </div>

      <div role="tablist" aria-label="Plugin store sections" className="flex flex-wrap gap-2 border-b border-border pb-3"
        onKeyDown={(event) => {
          const keys = ['discover', 'installed', 'updates', 'purchases'];
          let next;
          if (event.key === 'ArrowRight') next = (keys.indexOf(tab) + 1) % keys.length;
          if (event.key === 'ArrowLeft') next = (keys.indexOf(tab) + keys.length - 1) % keys.length;
          if (event.key === 'Home') next = 0;
          if (event.key === 'End') next = keys.length - 1;
          if (next === undefined) return;
          event.preventDefault();
          setTab(keys[next]);
          document.getElementById(`store-tab-${keys[next]}`)?.focus();
        }}>
        {[['discover', 'Discover'], ['installed', 'My plugins'], ['updates', 'Updates'], ['purchases', 'Purchases']].map(([key, label]) =>
          <button key={key} type="button" role="tab" tabIndex={tab === key ? 0 : -1} aria-selected={tab === key} aria-controls={`store-${key}`} id={`store-tab-${key}`}
            className={tab === key ? BTN_PRIMARY : BTN} onClick={() => setTab(key)}>{label}</button>)}
      </div>

      {catalog?.can_manage === false && <Administration value={adminDraft} onChange={setAdminDraft}
        onUnlock={unlockAdministration} checking={catalogLoading}
        rejected={Boolean(adminToken) && adminToken === adminDraft && !catalogLoading && catalog.status === 'ready'} />}

      {storePlan && <InstallPlan plan={storePlan} busy={busy} onConfirm={installFromStore} onCancel={() => setStorePlan(null)}
        onAcquire={id => { setPurchaseId(id); setStorePlan(null); setTab('purchases'); }} />}

      {error && <p className="rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm">{error}</p>}
      {data?.lifecycle_errors?.length > 0 && (
        <div role="alert" className="space-y-1 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm">
          <p className="font-medium">Some plugin changes could not be applied.</p>
          {data.lifecycle_errors.map((item, index) => <p key={index}>{typeof item === 'string' ? item : `${item.id}: ${item.error || item.reason}`}</p>)}
        </div>
      )}

      {(pendingRestart || applying) && restart && (
        <div className="space-y-3 rounded-md border border-primary/40 bg-primary/10 p-4 text-sm" data-probe-panel="plugin-apply">
          <div className="flex flex-wrap items-center gap-3">
            <div role="status" aria-live="polite" className="flex min-w-0 flex-1 basis-64 items-start gap-2">
              <RefreshCw aria-hidden="true" className={'mt-0.5 h-4 w-4 shrink-0' + (applying ? ' animate-spin' : '')} />
              <div>
                <p className="font-medium">{applying ? 'Restarting LDS…' : 'Changes ready to apply'}</p>
                <p className="mt-1 text-content-muted">{applying ? 'Waiting for the new server. This page will reload when it is ready.' : 'Your choices are saved. The current features stay available until LDS restarts.'}</p>
              </div>
            </div>
            {restart.can_apply && <button type="button" className={BTN_PRIMARY + ' shrink-0'} disabled={busy} onClick={apply}>Apply and restart</button>}
          </div>
          {!restart.can_apply && <p className="text-content-muted">{restart.how}</p>}
          {applyError && <p role="alert" className="text-amber-500">{applyError}</p>}
        </div>
      )}

      {['discover', 'updates'].includes(tab) && <div role="tabpanel" id={`store-${tab}`} aria-labelledby={`store-tab-${tab}`}>
        <Catalog catalog={catalog} installed={plugins} updatesOnly={tab === 'updates'} busy={busy || catalogLoading} onPlan={planInstall}
          loading={catalogLoading} onRetry={loadCatalog}
          onUnlock={() => document.getElementById('plugin-admin-token')?.focus()}
          selectedId={tab === 'discover' ? requestedPlugin : ''} onClearSelection={() => {
            const next = new URLSearchParams(searchParams); next.delete('plugin'); setSearchParams(next, { replace: true });
          }} />
      </div>}
      {tab === 'purchases' && <div role="tabpanel" id="store-purchases" aria-labelledby="store-tab-purchases">
        <Library key={purchaseId} catalog={catalog} initialPluginId={purchaseId} adminToken={adminToken}
          onPlan={planInstall} onChanges={() => { load(); loadCatalog(); }} />
      </div>}

      {tab === 'installed' && <div role="tabpanel" id="store-installed" aria-labelledby="store-tab-installed" className="space-y-5">
      {data?.transactions?.length > 0 && <details className="rounded-lg border border-border p-4 text-sm"
        open={data.transactions[0].phase === 'rolled_back'}>
        <summary className="min-h-10 cursor-pointer py-2 font-medium">Installation history</summary>
        <ul className="divide-y divide-border">{data.transactions.map(item => <li key={item.id} className="py-3">
          <p className="font-medium">{item.plugins.map(plugin => `${plugin.id}${plugin.version ? ` ${plugin.version}` : ''}`).join(', ')}</p>
          <p className="text-content-muted">{item.phase === 'committed' ? 'Applied successfully.' : item.phase === 'rolled_back'
            ? 'Installation did not complete. Your previous plugins and data were restored.' : 'Waiting for the installation to finish.'}</p>
          {item.reason && <p className="mt-1 text-content-muted">{item.reason}</p>}
        </li>)}</ul>
      </details>}
      {window.lds?.loadProblems?.length > 0 && <div role="alert" className="rounded-lg border border-amber-500/40 p-4 text-sm">
        <p className="font-medium">Some plugin interfaces did not load.</p>
        {window.lds.loadProblems.map((item) => <p key={item.plugin}>{item.plugin}: {item.reason}</p>)}
        <button type="button" className={BTN + ' mt-3'} onClick={() => window.location.reload()}>Reload interfaces</button>
      </div>}
      {bundled.length > 0 && <Card title="Included plugins" id="plugins-bundled"
        help="These ship in every release and are replaced by every update. Turn off what you do not use.">
        {bundled.length === 0
          ? <p className="text-sm text-content-muted">This build bundles no plugin yet.</p>
          : <ul>{bundled.map((p) => <PluginRow key={p.id} plugin={p} caps={caps} capsKnown={capsKnown} restart={restart} onToggle={toggle} onRemove={remove} onInstalled={() => { load(); refreshCaps(true); }} busy={busy} />)}</ul>}
      </Card>}

      <Card title="Installed plugins" id="plugins-external" help="Your plugins are kept across LDS updates.">
        {external.length === 0
          ? <p className="text-sm text-content-muted">No plugin installed yet.</p>
          : <ul>{external.map((p) => <PluginRow key={p.id} plugin={p} caps={caps} capsKnown={capsKnown} restart={restart} onToggle={toggle} onRemove={remove} onInstalled={() => { load(); refreshCaps(true); }} busy={busy} />)}</ul>}
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <label className={BTN + ' inline-flex cursor-pointer items-center gap-1'}>
            <Upload aria-hidden="true" className="h-3.5 w-3.5" /> Install from a ZIP
            <input ref={fileRef} type="file" accept=".ldsplugin,.zip,application/zip" className="sr-only"
              onChange={(e) => inspect(e.target.files && e.target.files[0])} disabled={busy} />
          </label>
          <span className="text-xs text-content-muted">The archive is inspected first; nothing is written until you confirm.</span>
        </div>
      </Card>
      </div>}

      {consent && (
        <Card title={`Install ${consent.manifest.name}?`} id="plugins-consent">
          <dl className="grid grid-cols-1 gap-x-4 gap-y-1 text-sm sm:grid-cols-[max-content_1fr]">
            <dt className="text-content-muted">Id</dt><dd>{consent.manifest.id} · v{consent.manifest.version}</dd>
            <dt className="text-content-muted">Author</dt><dd>{consent.manifest.author || '—'}</dd>
            <dt className="text-content-muted">License</dt><dd>{consent.manifest.license || '—'}</dd>
            <dt className="text-content-muted">Description</dt><dd>{consent.manifest.description || '—'}</dd>
            <dt className="text-content-muted">Requires</dt><dd>{(consent.manifest.requires || []).join(', ') || 'nothing'}</dd>
            <dt className="text-content-muted">Python packages</dt>
            <dd>{consent.manifest.requirements ? `a requirements file, installed into the plugin's own environment` : 'none'}</dd>
            <dt className="text-content-muted">Model files</dt>
            <dd>{consent.manifest.models?.length ? consent.manifest.models.map((m) => m.key).join(', ') : 'none'}</dd>
            <dt className="text-content-muted">ComfyUI node packs</dt>
            <dd>{consent.manifest.node_packs?.length ? consent.manifest.node_packs.map((pack) =>
              `${pack.pack} (${pack.installation ? 'installation available in plugin setup' : 'separate setup'})`).join(', ') : 'none'}</dd>
            <dt className="text-content-muted">Declares</dt><dd>{(consent.manifest.permissions || []).join(', ') || 'nothing'}</dd>
            <dt className="text-content-muted">Installs to</dt><dd className="break-all">{consent.install_dir}</dd>
          </dl>
          {!consent.can_install && <div role="alert" className="mt-3 rounded-lg border border-amber-500/40 p-3 text-sm">
            <p className="font-medium">This plugin cannot be installed in the current app configuration.</p>
            {consent.compatibility_issues.length > 0
              ? <ul className="mt-2 list-disc space-y-1 break-words pl-5">
                {consent.compatibility_issues.map((issue, index) => <li key={`${issue.field}-${index}`}>{issue.message}</li>)}
              </ul>
              : <p className="mt-2 text-content-muted">Compatibility could not be checked. Reload this page after updating LDS.</p>}
          </div>}
          <p className="mt-3 text-xs text-content-muted">
            A plugin runs inside the app with the app's own trust — it can read your datasets, your keys and use your GPU.
            Install only what you trust.
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <button type="button" className={BTN_PRIMARY} disabled={busy || !consent.can_install} onClick={() => confirmInstall(false)}>Install</button>
            <button type="button" className={BTN} disabled={busy} onClick={() => setConsent(null)}>Cancel</button>
          </div>
        </Card>
      )}

      {(data?.misplaced?.length > 0 || data?.invalid?.length > 0 || data?.stale?.length > 0) && (
        <Card title="Needs attention" id="plugins-attention">
          <ul className="space-y-1 text-sm">
            {(data.misplaced || []).map((m) => (
              <li key={'m-' + m.dir}><span className="font-medium">{m.dir}</span>: {m.reason}</li>
            ))}
            {(data.invalid || []).map((m) => (
              <li key={'i-' + m.dir}><span className="font-medium">{m.dir}</span>: {m.reason}</li>
            ))}
            {(data.stale || []).map((id) => (
              <li key={'s-' + id}><span className="font-medium">{id}</span>: switched off in the settings, but no plugin of that name is installed.</li>
            ))}
          </ul>
        </Card>
      )}

    </div>
  );
}
