export default function Administration({ value, onChange, onUnlock, checking, rejected }) {
  return <section id="plugin-administration" aria-labelledby="plugin-administration-title"
    className="space-y-3 rounded-lg border border-primary/40 bg-primary/5 p-4 text-sm">
    <h2 id="plugin-administration-title" className="font-semibold">Plugin installation is locked</h2>
    <p>This browser does not have permission to install or update plugins. This also applies when connecting from another computer on your local network.</p>
    <p className="text-content-muted">On the computer running LDS, open its localhost address using the same port. If an admin token is configured, enter it below even when connecting locally.</p>
    <details>
      <summary className="min-h-10 cursor-pointer py-2 font-medium">Set up installation from another computer</summary>
      <ol className="list-decimal space-y-2 pl-5 text-content-muted">
        <li>On the computer running LDS, generate a random token of at least 32 characters. With Python, run:
          <pre className="mt-2 overflow-x-auto rounded-md bg-surface p-3 text-xs"><code>{'python -c "import secrets; print(secrets.token_urlsafe(32))"'}</code></pre>
        </li>
        <li>Set <code>LDS_PLUGIN_ADMIN_TOKEN</code> to that token in the LDS startup environment, or add <code>LDS_PLUGIN_ADMIN_TOKEN=your-token</code> to its <code>.env</code> file. For Docker or a service, set it in the container or service environment.</li>
        <li>Restart LDS when no jobs are running, return to this page and enter the same token below.</li>
      </ol>
      <p className="mt-3 text-content-muted">Installing plugins runs code on the LDS computer. Keep this token private and use a trusted connection. Running LDS with sudo does not unlock this browser.</p>
    </details>
    <form onSubmit={onUnlock} className="space-y-2">
      <label htmlFor="plugin-admin-token" className="block font-medium">Plugin admin token</label>
      <div className="flex flex-wrap items-center gap-2">
        <input id="plugin-admin-token" type="password" autoComplete="off" required minLength={32}
          value={value} onChange={event => onChange(event.target.value)}
          aria-describedby="plugin-admin-token-hint" aria-invalid={rejected || undefined}
          className="min-h-10 min-w-0 flex-1 rounded border border-border bg-surface px-3" />
        <button type="submit" disabled={checking}
          className="min-h-10 rounded-md border border-primary bg-primary px-3 py-2 font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
          {checking ? 'Checking token…' : 'Unlock plugin changes'}
        </button>
      </div>
      <p id="plugin-admin-token-hint" className="text-xs text-content-muted">Use the separate plugin admin token, not an API key or the app access token. It is kept only until this page is reloaded.</p>
      {rejected && <p role="alert" className="text-amber-500">This token was not accepted. Check that it matches LDS_PLUGIN_ADMIN_TOKEN on the LDS computer and restart LDS after configuring it.</p>}
    </form>
  </section>;
}
