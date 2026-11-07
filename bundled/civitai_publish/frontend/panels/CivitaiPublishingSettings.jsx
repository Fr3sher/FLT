import { Card, INPUT_CLASS, SecretField } from '@lds/plugin-sdk/ui'

/* This product's settings share the same stored Civitai key as the core
   prompt browser and optional scraper, and choose which domain opens links. civitai.red is the same site and
   the same account behind a second domain, but the sign-in is per domain — a
   draft page opened on the domain you are not signed in on shows a 404 for
   your own model.

   `id="civitai-link-host"` is spelled out literally: it is the focus anchor of
   the plugin's `civitai.link_host` help topic, which the help contract scans
   this file for. */
const CIVITAI_TOKEN = {
  key: 'CIVITAI_API_KEY', label: 'Shared Civitai API key', testTarget: 'civitai',
  help: 'Create an API key in your Civitai account settings, then save it here. No second credential is stored for publishing.',
  guide: <a href="https://civitai.com/user/account" target="_blank" rel="noreferrer" className="text-sm underline">Open Civitai account settings</a>,
}

export default function CivitaiPublishingSettings(props) {
  return (
    <Card
      id="civitai-publishing"
      title="Civitai publishing"
      help="📤 Publish a checkpoint as a Civitai model page and post generated images under it — from a checkpoint's popover (◉ Canvas, run graph) and from the image viewer. The API key is shared with the Civitai prompt browser and optional Web scraping plug-in. Replacing or removing it here applies everywhere."
    >
      <SecretField field={CIVITAI_TOKEN} {...props} />
      <div>
        <label htmlFor="civitai-link-host" className="text-sm font-medium text-content">
          Open Civitai links on
        </label>
        <select id="civitai-link-host"
          value={props.config?.civitai?.link_host ?? 'civitai.com'}
          onChange={(e) => props.setField('civitai', 'link_host', e.target.value)}
          className={INPUT_CLASS}>
          <option value="civitai.com">civitai.com</option>
          <option value="civitai.red">civitai.red — the same site and account, second domain</option>
        </select>
        <p className="mt-1 text-xs text-content-muted">
          The API always talks to civitai.com. Pick the domain you are signed in on: a draft model page
          is private to its owner and the sign-in is per domain, so opened on the other one your own
          draft answers a 404.
        </p>
      </div>
    </Card>
  )
}
