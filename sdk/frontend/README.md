# LDS frontend SDK 1.15

This kit builds one complete plugin: its screens, controls, settings, setup
surfaces, help and update history travel with its backend. A contribution slot
places a feature in LDS; it is not a separate product.

The kit is provided as a versioned package. It does not require the LDS source
tree at build time. Install the supplied SDK package in the plugin's development
dependencies, keep the resulting lockfile, install the plugin's dependencies with
`npm ci`, then run:

```sh
lds-plugin-build --plugin . --out ui
```

The output directory must be empty. The plugin package declares its source entry
as `package.json` → `lds.entry` (default `frontend/index.js`). Its `plugin.json`
declares the distributed entry as `frontend: "ui/index.js"` and stylesheet as
`frontend_styles: ["ui/styles.css"]`. Include all generated chunks and assets in
the same package. Neither `node_modules` nor this build tool belongs in the
installed plugin. The packaging validator and signature are separate steps.

```js
import { definePlugin } from '@lds/plugin-sdk'
import { action } from '@lds/plugin-sdk/help'

export default definePlugin({
  id: 'publisher.feature',
  slots: {
    'setup.card': [{ id: 'feature', panel: () => import('./FeatureSetup.jsx') }],
  },
  help: [action('publisher-feature-help', 'Set up the feature', ['feature'],
    '/setup?step=install', 'getting-started', 'the-setup-wizard')],
})
```

The builder registers this descriptor with the version from its manifest. LDS
checks that the descriptor ID matches the package it is loading. An ordinary
plugin must use a publisher-qualified ID. Reserved short IDs require an official
package verified by the installation backend; a descriptor's own `official`
field grants nothing.

## Runtime services

`@lds/plugin-sdk` exports `apiFetch`, `postJson`, `putJson`, `patchJson`, `del`,
`postForm`, `useToast`, `HelpBadge`, `requestHelpTip`, `GlobalModelPicker`,
`installActionLabel`, `definePlugin`, `registerPlugin`, `runtime` and
`SDK_VERSION`. HTTP functions use LDS's real CSRF/retry implementation. Toast,
help and model selection use LDS's providers and contexts. `GlobalModelPicker`
accepts `section`, `field`, `slot`, `label`, `value` and `onSaved`; it saves the
same application setting from every contributing work screen.

`@lds/plugin-sdk/help` exports pure `action`, `setting` and `setupStep` topic
builders. `@lds/plugin-sdk/setup` exports readiness helpers and download-size
formatting. `@lds/plugin-sdk/camera-data` describes version 1 of the stored pose
format, so previously created images remain readable without the generating
plugin. These modules are importable in Node without a browser.

`@lds/plugin-sdk/ui` provides shared Settings controls (`Card`, `SecretField`, `TextField`,
`StatusBadge`, `ResetToDefault`), the catalog-driven `EngineCard`, shared input
and checkpoint-row classes, `useFocusTrap`, `useCapabilities`, `SettingsLink`,
`InstallRunner`, `KleinModelSetting` and persisted-photo attribution. Their
interaction rules and contexts belong to the host; the plugin still supplies
its own content, model choices, forms and business actions. EngineCard is the
common checkbox shell for both local and plugin engines, not the API engines'
cards or pricing logic. `@lds/plugin-sdk/data` contains the stable checkpoint
filename formatter used when presenting previously stored records.

## Plugin settings

Starting with API 1.12, LDS provides `/plugins/:pluginId/settings` from each
installed plugin's card. Contribute every product preference through
`settings.group`: credentials, models, paths, defaults and advanced options
belong there. A group's `section` is a logical category retained for compatibility;
it no longer inserts the group into general Settings. Core/shared services keep
their own settings, and task-specific controls remain in the work screen.

Use the SDK's pointer when an action depends on one of these preferences:

```jsx
import { SettingsLink } from '@lds/plugin-sdk/ui'

<SettingsLink pluginId="publisher.feature" focus="feature-model">
  Choose the model
</SettingsLink>
```

`pluginId` takes precedence over the legacy `section` prop. `focus` remains the
actual DOM ID of the field. A plugin using this route or prop declares
`compatibility.api: ">=1.12,<2"`; the host rejects older compatibility before
loading the package. Existing `SettingsLink section="local-tools"` links remain
valid for shared services. Declare old focused Settings routes through the help
topic's `app.legacyRoute` or `app.legacyRoutes` when relocating a field.

`TextField` is also available since API 1.12. Its props are `id`, `label`, `value`,
`onChange(value)`, `placeholder`, `help`, `warn` and `children`. It renders the
host's labeled text input and normalizes a missing value to an empty string;
the plugin decides how to validate and persist the supplied string.

The host mounts only the active owner's groups, offers Save/Discard and the
existing secret/probe helpers, and preserves stored values. An absent, disabled,
pending-change or failed plugin shows its lifecycle status instead of loading its
settings panel. The package manifest declares the matching API compatibility and owned settings.

Store diagnostics are available as a snapshot in `window.lds.loadProblems`,
with `{plugin, reason}` entries. Arbitrary exception detail is excluded.

Runtime API major 1 and SDK minor 7 or newer are required. A missing or incompatible
host produces an explicit error. React, `react/jsx-runtime`, `react-dom/client`
and the supported router hooks resolve to the host's instances. **Do not bundle
another React or create a copy of a host context.** The current router bridge
exports `Link`, `NavLink`, `useLocation`, `useNavigate`, `useParams` and
`useSearchParams`; `react-dom` exposes the host's portals and flush operation.
Imports outside this
public contract fail the build rather than silently depending on LDS internals.

The two HTTP write contracts are deliberately distinct. `postJson` rejects on
HTTP/network failure. `postJsonResult(url, body, isForm)` returns an
`{ok:false, error, ...details}` envelope instead; forms that inspect `result.ok`
must use this version. Its third argument preserves multipart submissions.

## Shared training history and Cloud ownership

`@lds/plugin-sdk/training` supplies the existing host training progress, run
identity chips and history controller. `RunsHub({endpoint, continuation, render})`
owns polling and local history; the render callback receives its host controller.
`RunsHubContent({host, cloud})` renders that history and only offers cloud actions
when the plugin passes their callbacks. Installing Cloud adds the real rented-GPU
workflow, dense-model recipe, delivery panels, settings, help and update feed.
Disabling it retains readable previously saved runs and local continuation.

The same module exposes `postWithConfirmations` and
`retryConfirmableRefusals()` from the host's single refusal policy. Plugins must
not copy that admission loop or its marker list. The general `PluginSlot` and
`LocationEditor` controls are in `/ui`; a nested slot lets a complete product
accept another product's contribution without importing it.

Cloud owns its recipe selection, paid-launch estimates, billing-silence messages,
staging cleanup policy and launch display under its own `frontend/lib` and
`frontend/shared` directories. These do not enter the public SDK. Existing host
helpers for persisted history remain compatible; the plugin imports none of
their private files. `/data` provides small formatters for persisted paths,
sizes, run anchors and default values.

`@lds/plugin-sdk/links` exposes the host's outbound-link builders and disclosure.
Cloud asks `vastReferralId()` at render time, so forks can change the host's
single referral configuration without rebuilding a plugin or duplicating an ID.

## Video and shared workspace services

Video ships its Bank, Dataset, Studio, setup cards, capability decisions,
training controls and complete help/history together.
Live is a separate product with its own screens, installation and settings.
Its HLS playback dependency is locked and bundled with the product. The SDK
does not contain a video screen, video pipeline or video installation policy.

`/bank` forwards the host's bank layout preferences and lane-tab styling, and
formats the shared background-job ETA contract. `/ui` supplies existing bank
controls, folder selection, guide buttons, dial locks, the generated-image
viewer and Studio action bar. These wrappers render the actual host components;
they do not clone their context, lock memory or image action menus. The plugin
provides its own screen content and callbacks.

`/lineage` supplies host run cards, checkpoint pills, edges, geometry and popover
placement. Saved run identifiers remain readable regardless of the optional
execution product. `/inference` provides the shared Ollama exclusion hook and
notice, stale-answer checks, image-improvement action and settings restoration.
`/files` uses the host's download transport, which verifies the HTTP response
before saving a file. `/search` contains the versioned pure presentation helpers
for semantic-search readiness and query guidance used by both media banks.

Other libraries belong in the plugin's declared, locked `dependencies`.
For example, Camera ships its tree-shaken Lucide icons and uses the shared React
bridge. The builder rejects an output graph that contains another React/router
copy or source files outside the package and public SDK.

## Styling and loading

The SDK compiles the plugin's own `frontend` sources with its versioned Tailwind
3.4 theme. The application supplies reset, fonts and semantic CSS variables;
plugin CSS contains utilities and has preflight disabled. Keep this preset when
using the existing utility classes: arbitrary Tailwind versions with colliding
class names are not a supported styling contract. A plugin can include its own
namespaced CSS and assets, but must declare the resulting stylesheets.

LDS loads every declared stylesheet before evaluating the entry. CSS failure
prevents registration; module failure removes its contributions and styles.
Entries, chunks and styles use relative paths under the same server boot URL.
Disabling a plugin takes effect at Apply/restart and then loads none of its UI
or CSS. Do not overwrite an active package's files.

## Camera pilot and application profiles

Camera contributes `lightbox.action` on Gallery and Dataset, `setup.card`,
`setup.step`, its model settings and help topics.
Gallery's shared viewer also carries the action in Studio and Canvas. The Bank
exception remains documented because generated candidates go to a dataset or
the Gallery. No extra top-level screen is needed to package this workflow.

LDS defaults to `LDS_PLUGIN_BUILD_MODE=store`: the core build imports **no bundled
descriptor** and scans **no bundled classes**. Independently built products bring
their complete UI to a core that never compiled their sources. The explicit
`bundled` build mode remains a development profile. Legacy migration installs
the approved archives through the package lifecycle; it does not require the
host frontend to compile product code.

The frontend SDK is a compatibility contract for trusted installed code. It is
not a JavaScript sandbox, store identity system, signature verifier or payment
provider. Those responsibilities belong to the installation and store services.

SDK1.8 also exports pure `progressLabel(progress)` and `renderForJob(render, jobId)`
from `@lds/plugin-sdk/ui`. They preserve the common ComfyUI progress wording
and bind a progress record to its job. These formatters do not require a browser
host. Existing frontend runtime services retain their minimum host SDK1.7;
products using the API1.8 model-download or native Cloud contracts must declare
`compatibility.api >=1.8` in their manifest.

API 1.9: `improve.engine` / `improve.editor` provide complete optional image improvement. The shared inference module exposes active choices and historical labels; `/lora` contains shared LoRA normalization, and `ui.PromptOverrideField` edits global prompts.

API 1.10 adds `ui.H3LoraPicker` with an explicit product `apiBase`, and `/h3` for shared LoRA grouping and frame rules. Live and Video use these primitives while owning separate screens, installation and history.
