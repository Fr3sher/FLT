/**
 * Test Studio page — routes /studio (standalone) and /dataset/studio/:id
 * (legacy, pre-filled with a dataset).
 *
 * Reads the dataset id from the URL (`:id` param) OR the `?dataset=` query
 * param and passes it as `preselectDataset` to StudioShell: a blank page if
 * neither is set, otherwise that LoRA is pre-checked in the picker.
 *
 * The workspace stays mounted while ComfyUI is busy or unreachable. Each
 * lane checks readiness when generating; history does not require a live GPU.
 */
import { useParams, useSearchParams } from 'react-router';
import { Clapperboard, FlaskConical, Puzzle, Radio } from 'lucide-react';
import StudioShell from '../components/dataset/studio/StudioShell';
import { PluginPanel } from '../plugins/PluginSlot.jsx';
import { contributions } from '../plugins/registry.js';
import UnavailablePluginPage from './UnavailablePluginPage.jsx';

// The image lane is the core's; every other tab is a plugin's `studio.tab`
// contribution (`{ id, label, badge?, icon?, panel }` — the video plugin brings
// their complete lanes). A descriptor cannot import lucide-react, so it names
// its icon; unknown names get the plugin piece.
const LANE_ICONS = { clapperboard: Clapperboard, radio: Radio };
const IMAGE_TAB = { id: 'image', label: 'Images', icon: FlaskConical };
function studioTabs() {
  return [IMAGE_TAB, ...contributions('studio.tab', 'studio').map((t) => ({
    id: t.id, label: t.label, badge: t.badge, icon: LANE_ICONS[t.icon] || Puzzle,
    plugin: t.plugin, panel: t.panel,
  }))];
}
const LANES = () => studioTabs().map((t) => t.id);

/* The two things a LoRA can be, tested in the same place.
 *
 * A tab rather than a second page, because "test the LoRA I just trained" is
 * ONE intention and the medium is a property of the LoRA, not of the errand.
 * The lanes share nothing below this line: an image LoRA and a video LoRA live
 * in different tables, render through different pipelines, and the video one
 * queues a single clip where the image one runs a grid — so each lane is its
 * own subtree, mounted and unmounted whole. That is deliberate: it means the
 * video panel cannot leak state into the studio that was here first.
 *
 * `?lane=video` opens straight on it (What's-new and the help topic both use
 * it); the choice is otherwise remembered, because whoever is testing video
 * LoRAs today will be testing video LoRAs in ten minutes. */
const LANE_KEY = 'lds.studio.lane';

function readLane(param) {
  if (param) return param;
  try {
    const saved = window.localStorage.getItem(LANE_KEY);
    if (LANES().includes(saved)) return saved;
  } catch {
    /* private mode, or storage disabled — the default is a fine answer */
  }
  return 'image';
}

export default function StudioPage() {
  const { id } = useParams();
  const [sp, setSp] = useSearchParams();
  // /dataset/studio/:id (legacy), or /studio?dataset=… (launcher), or nothing (standalone).
  const preselectDataset = id || sp.get('dataset') || null;
  const preselectFamily = sp.get('family') || null;
  // `?base=` — the base model to open on, as ComfyUI's loader names it. Sent by
  // the full-model card in Checkpoints & LoRAs: arriving there means "test THIS
  // model", and a full model that is not preselected is a model you have to go
  // and find in a dropdown among every checkpoint on the machine. It also
  // re-seeds CFG/steps, which is the point for an undistilled base — the
  // family's few-step defaults render mush on one.
  const preselectBase = sp.get('base') || null;

  const lane = readLane(sp.get('lane'));
  const tabs = studioTabs();
  // A lane a plugin no longer contributes (remembered from a session with it
  // on) falls back to the image lane rather than a blank page.
  const pluginTab = lane === 'image' ? null : tabs.find((t) => t.id === lane && t.panel) || null;
  const pickLane = (next) => {
    const nextParams = new URLSearchParams(sp);
    nextParams.set('lane', next);
    setSp(nextParams);
    try {
      window.localStorage.setItem(LANE_KEY, next);
    } catch { /* nothing to remember it with — the tab still switches */ }
  };

  // pb-24: StudioActionBar is a fixed bottom bar (Run button + section shortcuts) —
  // leaves room so it never covers the last row of results.
  return (
    <div className="pb-24">
      {/* Not a probe panel: the fill check reads a panel's children as stacked
          ROWS, and these are equal tabs side by side — each one a share
          of the bar, which the check reports as a row two-thirds empty. The bar
          is still measured for overflow like the rest of the page, and its
          buttons carry the finger-sized idiom (min-h-10 lg:min-h-0). */}
      <div className={`mb-2 ${tabs.length > 2 ? 'grid grid-cols-2 sm:flex' : 'flex'} rounded-xl border border-border bg-surface p-0.5`}>
        {tabs.map(({ id, label, icon: Icon, badge }) => (
          <button key={id} type="button" onClick={() => pickLane(id)}
            aria-pressed={lane === id} data-testid={`studio-lane-${id}`}
            className={`flex min-w-0 flex-1 items-center justify-center gap-1 rounded-lg px-1 py-1.5 text-xs sm:text-sm font-semibold min-h-10 lg:min-h-0 ${
              lane === id ? 'bg-primary text-white' : 'text-content-muted hover:text-content'}`}>
            <Icon aria-hidden="true" className="h-4 w-4" />{label}
            {badge && (
              <span className="ml-0.5 rounded-full border border-current px-1.5 text-[0.625rem] font-semibold uppercase leading-4 tracking-wide opacity-80">
                {badge}
              </span>
            )}
          </button>
        ))}
      </div>
      {pluginTab ? (
        <PluginPanel panelKey={`${pluginTab.plugin}:${pluginTab.id}:studio`} importer={pluginTab.panel}
          datasetId={preselectDataset} />
      ) : lane !== 'image' ? <UnavailablePluginPage label="This Studio lane" /> : (
        <StudioShell preselectDataset={preselectDataset} preselectFamily={preselectFamily}
          preselectBase={preselectBase} />
      )}
    </div>
  );
}
