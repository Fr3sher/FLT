import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

const graph = fs.readFileSync(new URL('./RunLineageGraph.jsx', import.meta.url), 'utf8');
const cloud = fs.readFileSync(new URL('../../pages/CloudRunsPage.jsx', import.meta.url), 'utf8');
const panel = fs.readFileSync(new URL('./TrainingPanel.jsx', import.meta.url), 'utf8');
// The card, the pill and the edges are no longer private to this component —
// they were extracted so the LoRA Canvas draws with the SAME ones (a lookalike
// would drift the first time either surface was tweaked).
const nodes = fs.readFileSync(new URL('./lineageNodes.jsx', import.meta.url), 'utf8');
const edges = fs.readFileSync(new URL('./lineageEdges.jsx', import.meta.url), 'utf8');
const canvas = fs.readFileSync(new URL('../canvas/LineageCanvas.jsx', import.meta.url), 'utf8');

test('the drawing is shared with the canvas, not duplicated', () => {
  // Both surfaces IMPORT the card/pill/edges; neither declares its own.
  assert.match(graph, /import \{ GraphCard, CheckpointPill \} from '\.\/lineageNodes'/);
  assert.match(graph, /import \{ LineageEdgeDefs, LineageEdges \} from '\.\/lineageEdges'/);
  assert.match(canvas, /import \{ GraphCard, CheckpointPill \} from '\.\.\/dataset\/lineageNodes'/);
  assert.match(canvas, /import \{ LineageEdgeDefs, LineageEdges \} from '\.\.\/dataset\/lineageEdges'/);
  for (const src of [graph, canvas]) {
    assert.doesNotMatch(src, /function GraphCard\(/);
    assert.doesNotMatch(src, /function CheckpointPill\(/);
    assert.doesNotMatch(src, /linearGradient id="lds-edge-/);
  }
  assert.match(nodes, /export function GraphCard\(/);
  assert.match(nodes, /export function CheckpointPill\(/);
  assert.match(edges, /export function LineageEdgeDefs\(/);
  assert.match(edges, /export function LineageEdges\(/);
});

test('the canvas GENERATES through the Test Studio, it does not grow a second one', () => {
  // Slice 3 opened this up (the guard used to lock the canvas OUT of generation
  // so the earlier slices could not quietly grow half a feature). What is locked
  // now is the shape of the opening: the canvas mounts the Studio's panel and the
  // Studio's hooks. A canvas that re-declared a prompt field, a seed control or a
  // launch call would be the drift this whole design exists to prevent.
  const panel = fs.readFileSync(new URL('../canvas/CanvasGenerationPanel.jsx', import.meta.url), 'utf8');
  assert.match(panel, /import RunSetupPanel from '\.\.\/dataset\/studio\/RunSetupPanel'/);
  assert.match(panel, /useStudioForm/);
  assert.match(panel, /useCanvasStudio/);
  assert.doesNotMatch(panel, /<textarea/);          // the prompt field is PromptField's
  assert.doesNotMatch(panel, /rollSeed|nextSeed\(\)/);
  // The canvas ticks pills; the in-card graph keeps its own selection intact.
  assert.match(canvas, /onToggleSelect=\{\(\) => onTogglePick\(/);
  assert.match(graph, /onToggleSelect=\{\(pill\) => toggleCk\(/);
});

test('the canvas launch goes through ONE call site, so no setting can be dropped', () => {
  const hook = fs.readFileSync(new URL('../../hooks/useCanvasStudio.js', import.meta.url), 'utf8');
  const setup = fs.readFileSync(new URL('./studio/RunSetupPanel.jsx', import.meta.url), 'utf8');
  // RunSetupPanel owns genSettings in local state and passes it to studio.launch.
  // The canvas therefore swaps studio.launch — NOT the onLaunch handler, which
  // would have silently lost the global generation settings from a canvas run.
  assert.match(setup, /const onLaunch = async \(\) => \{/);
  assert.match(setup, /studio\.launch\(/);
  assert.doesNotMatch(setup, /onLaunchOverride/);
  assert.match(hook, /genSettings = \{\}/);
  assert.match(hook, /\.\.\.genSettings/);
  assert.match(hook, /\/api\/train\/canvas\/generate/);
});

test('the canvas refuses mixed families and deploys before generating — in the pure layer', () => {
  const rules = fs.readFileSync(new URL('../../utils/canvasGeneration.js', import.meta.url), 'utf8');
  // Both decisions are arithmetic a test can check without a browser (behaviour
  // covered in canvasGeneration.test.js); the component must USE them.
  assert.match(canvas, /from '\.\.\/\.\.\/utils\/canvasGeneration'/);
  assert.match(canvas, /describeCanvasLaunch\(picks\)/);
  assert.match(rules, /cannot run together/);
  assert.match(rules, /different base models/);
  assert.match(rules, /Deploy \$\{n\} checkpoint/);
  // A failed deploy ABORTS: half a comparison answers a different question.
  assert.match(canvas, /Deploy failed — nothing was generated/);
});

test('the canvas moves cards through the PURE placement layer, not by hand', () => {
  // The whole point of the layer is that "a new run moves nothing" is arithmetic
  // a test can check without a browser. A component that recomputed positions
  // inline would put that rule back out of reach.
  assert.match(canvas, /from '\.\.\/\.\.\/utils\/canvasPlacement'/);
  assert.match(canvas, /applyPlacement\(/);
  assert.match(canvas, /pinSnapshot\(/);
  assert.doesNotMatch(canvas, /function applyPlacement|function pinSnapshot/);
});

test('the canvas disambiguates the touch gesture with a long press', () => {
  // Dragging a card and panning the board are the same finger. Without an
  // explicit delay one of the two becomes impossible on a phone.
  assert.match(canvas, /LONG_PRESS_MS/);
  assert.match(canvas, /pointerType !== 'touch'/);
  assert.match(canvas, /cancelLongPress\(\)/);
});

test('✦ Tidy up exists and is wired to the page, not to a local reset', () => {
  const page = fs.readFileSync(new URL('../../pages/CanvasPage.jsx', import.meta.url), 'utf8');
  assert.match(canvas, /Tidy up/);
  assert.match(canvas, /onClick=\{onTidyUp\}/);
  // It clears the SERVER's memory of the lane; a client-only reset would come
  // back on the next reload.
  assert.match(page, /del\(`\/api\/dataset\/\$\{id\}\/canvas\/positions`\)/);
});

test('the graph draws checkpoint pills with a download link (reused endpoint)', () => {
  assert.match(graph, /CheckpointPill/);
  // download reuses the server-provided url — no url built in the component
  assert.match(graph, /href=\{openCk\.pill\.download_url\}/);
  // the popover uses the OPAQUE overlay surface, never the see-through surface
  assert.match(graph, /bg-surface-overlay/);
  assert.doesNotMatch(graph, /lds-ck-popover[^]*bg-surface\b(?!-overlay)/);
});

test('the graph opens for any run with a checkpoint, not only 2+ run lineages', () => {
  // button + body both gate on lineage OR a saved checkpoint
  assert.match(cloud, /run\.lineage\s*\|\|\s*run\.checkpoint_ready/);
  // single-run graph is labelled ◉ Graph, a real lineage stays 🌳 Lineage
  assert.match(cloud, /run\.lineage \? '🌳 Lineage' : '◉ Graph'/);
});

test('continue-from-checkpoint is cloud-only by default and allows terminal (done OR failed) runs', () => {
  // The rule lives in the JSX-free helper (behaviour covered by
  // lineageContinue.test.js); the graph must USE it, not re-implement one.
  const rule = fs.readFileSync(new URL('./lineageContinue.js', import.meta.url), 'utf8');
  assert.match(graph, /import \{ canContinueFromCheckpoint \} from '\.\/lineageContinue\.js'/);
  assert.match(graph, /canContinueFromCheckpoint\(node, pill, \{/);
  // still cloud-only with a run id, unless the mount opted into 'any'
  assert.match(graph, /continueSource = 'cloud'/);
  assert.match(rule, /node\.source === 'cloud'/);
  assert.match(rule, /node\.run_id != null/);
  // a 'done' run always; a failed/stopped run only when THIS pill is present
  assert.match(rule, /node\.status === 'done'/);
  assert.match(rule, /'error', 'error_pod_kept', 'stopped', 'failed'/);
  assert.match(rule, /pill\?\.download_url/);
});

test('the Runs hub keeps the CLOUD gate — it passes no continueSource', () => {
  // The invariant: the hub's popover must not change. It wires the handler and
  // nothing else, so the graph falls back to its 'cloud' default.
  assert.match(cloud, /onContinueCheckpoint=\{continueFromCheckpoint\}/);
  assert.doesNotMatch(cloud, /continueSource/);
});

test('the dataset panel offers the SAME pill gesture through its local flow', () => {
  // continueSource="any" + a handler that reuses the existing local dialog —
  // no second continue path, no duplicated backend call.
  assert.match(panel, /continueSource="any"/);
  assert.match(panel, /onContinueCheckpoint=\{checkpointMatchesTraining/);
  assert.match(panel, /const continueFromGraphCheckpoint = \(node, pill\) =>/);
  assert.match(panel, /setContinueInitialStep\(step\);\s*setContinueOpen\(true\);/);
  assert.match(panel, /initialFromStep=\{continueInitialStep\}/);
  // the plain Continue button clears the pill pick, so it still opens on latest
  assert.match(panel, /setContinueInitialStep\(null\); setContinueOpen\(true\)/);
  // ONE continue call site (the guarded helper picks the lane's hook inside it),
  // never a second continue request assembled somewhere else in the panel
  assert.equal((panel.match(/payload\.extraSteps/g) || []).length, 1);
  assert.equal((panel.match(/await runConfirmableTrainingRequest\(/g) || []).length, 1);
});

test('the LoRA manager opens the same graph component for the whole dataset', () => {
  assert.match(panel, /import RunLineageGraph from '\.\/RunLineageGraph'/);
  assert.match(panel, /◉ Graph/);
  assert.match(panel, /train\/lineage\?/);
  assert.match(panel, /<RunLineageGraph tree=\{datasetGraph\.tree\}/);
});

test('the manager opens on the GRAPH by default, with a persisted List toggle', () => {
  // Default view is the graph — the showcase surface; the list stays available.
  assert.match(panel, /localStorage\.getItem\('lds\.checkpointsView'\) === 'list' \? 'list' : 'graph'/);
  assert.match(panel, /setItem\('lds\.checkpointsView'/);
  // The graph and the flat list are each gated on the current view.
  assert.match(panel, /checkpointsView === 'graph' &&/);
  assert.match(panel, /checkpointsView === 'list' &&/);
  // ☰ List toggle exists alongside ◉ Graph.
  assert.match(panel, /☰ List/);
});

test('the dataset graph renders INLINE inside the manager (no body-portal modal)', () => {
  // The graph now lives inside the CheckpointPortal'd manager, which itself
  // renders into the VISIBLE sidebar host — so it never inherits the hidden
  // home container's display:none that forced the old modal to portal to <body>.
  assert.doesNotMatch(panel, /aria-label="Dataset run graph"/);
  assert.doesNotMatch(panel, /datasetGraph && createPortal\(/);
  // createPortal stays imported — CheckpointPortal still uses it.
  assert.match(panel, /import \{ createPortal \} from 'react-dom'/);
});

test('a pill can be imported straight from the graph, deployed pills say so', () => {
  // 📦 Import → loras/<family> uses the CSRF-safe postJson and the list's exact
  // payload (via lineageImportPayload); an already-deployed pill shows ✓ Deployed.
  assert.match(graph, /lineageImportPayload/);
  assert.match(graph, /train\/import/);
  assert.match(graph, /postJson\(`\/api\/dataset\/\$\{datasetId\}\/train\/import`/);
  assert.match(graph, /checkpointDeployed\(openCk\.pill\)/);
  assert.match(graph, /✓ Deployed/);
  // after a successful import the lineage is refetched so the pill flips testable
  assert.match(graph, /refetchTree/);
});

test('a preview thumbnail opens LARGE in a lightbox, distinct from the popover', () => {
  assert.match(graph, /onZoomPreview/);
  // clicking the thumbnail must NOT open the popover (its own action)
  assert.match(nodes, /e\.stopPropagation\(\); onZoomPreview/);
  assert.match(graph, /bigPreview/);
});

test('a persisted 🔍 Big-previews mode enlarges the generated tiles', () => {
  // Toggle + persistence in the graph, geometry threaded to the layout.
  assert.match(graph, /🔍 Big previews/);
  assert.match(graph, /localStorage\.getItem\('lds\.graphBigPreviews'\)/);
  assert.match(graph, /setItem\('lds\.graphBigPreviews'/);
  assert.match(graph, /buildLineageGraph\(shownTree, \{ bigPreviews \}\)/);
  // The pill sizes off the layout's per-mode geometry (pill.w/pill.h), not a const.
  assert.match(nodes, /width: pill\.w, height: pill\.h/);
});

test('the ◉ Graph button is the prominent (accent) view control', () => {
  // On the Runs hub the graph toggle wears the indigo accent, not a bare grey.
  assert.match(cloud, /border-indigo-400\/40 bg-indigo-500\/10 text-indigo-200/);
});

test('the pill delete aims at what the pill SHOWS — deployed copy vs training save', () => {
  // The route is NOT hardcoded in the component: it comes from the target the
  // helper picks off the pill's deployed state (both routes live in the helper,
  // unit-tested in lineagePreview.test.js).
  assert.match(graph, /const target = checkpointDeleteTarget\(node, pill\);/);
  assert.match(graph, /postJson\(`\/api\/dataset\/\$\{datasetId\}\/\$\{target\.path\}`, target\.body\)/);
  const helpers = fs.readFileSync(new URL('./lineagePreview.js', import.meta.url), 'utf8');
  assert.match(helpers, /checkpointDeployed\(pill\)/);            // ONE source of truth for "deployed"
  assert.match(helpers, /path: 'train\/checkpoint\/delete'/);      // deployed → the ComfyUI copy
  assert.match(helpers, /path: 'train\/run-checkpoint\/delete'/);  // otherwise → the run's save
  // The BUTTON says which of the two it would delete, right now.
  assert.match(graph, /\{deleting \? 'Deleting…' : target\.label\}/);
  assert.match(graph, /title=\{target\.title\}/);
  // Confirmed, with the ★ best-settings pin reaching the confirmation text.
  assert.match(graph, /describeCheckpointDelete\(node, pill, \{ bestSettingsLora \}\)/);
  assert.match(graph, /if \(!window\.confirm\(message\)\) return;/);
  // postJson THROWS on 400/409 — the server's own message must be shown, not eaten.
  assert.match(graph, /catch \(e\) \{\s*toast\.error\(e\?\.message \|\| 'Delete failed'\);/);
  // The pill must stop lying: same refetch path the import success uses, so a
  // just-undeployed pill flips to "not deployed" (next click aims at the save).
  assert.match(graph, /Undeployed from ComfyUI[^]*?refetchTree\(\)/);
});

test('undeploy is EXPLICIT and symmetric with deploy — and never confusable with delete', () => {
  const helpers = fs.readFileSync(new URL('./lineagePreview.js', import.meta.url), 'utf8');
  // ⏏ Undeploy sits next to "✓ Deployed", where 📦 Import sits when it isn't —
  // no longer only reachable through the retreat row.
  assert.match(graph, /✓<\/span> Deployed/);
  assert.match(graph, /⏏<\/span> \{deleting \? 'Undeploying…' : undeploy\.label\}/);
  assert.match(graph, /const undeploy = checkpointUndeployAction\(openCk\.node, openCk\.pill\);/);
  // It is DERIVED from the single delete target, so its label can never name one
  // file while the click posts another (the invariant of this popover).
  assert.match(helpers, /export function checkpointUndeployAction[^]*?checkpointDeleteTarget\(node, pill\)/);
  assert.match(helpers, /target\.kind !== 'deployed'\) return null;/);
  // The 🗑 retreat row is now reserved for the one destructive action: the save.
  assert.match(graph, /!target \|\| target\.kind !== 'save'\) return null;/);
  // Undeploy is presented as REVERSIBLE — the save survives and can be re-deployed.
  assert.match(helpers, /Reversible: the training save is kept/);
});

test('the lineage payload carries the deployed copy name from the testable map', () => {
  const svc = fs.readFileSync(new URL('../../../../backend/app/services/cloud_training.py', import.meta.url), 'utf8');
  // Same map that sets `testable` also names the deployed file — no second
  // source. Both now live in ONE annotator, shared with the Checkpoints panel,
  // so the two surfaces can never disagree on what is deployed.
  assert.match(svc, /def annotate_deployed_checkpoints\(/);
  assert.match(svc, /ck\['testable'\] = step in testable/);
  assert.match(svc, /ck\['deployed_filename'\] = names\.get\(/);
  assert.match(svc, /annotate_deployed_checkpoints\(rec\.dataset_id, rec\.family,/);
  // …resolved to the form the deployed-delete route whitelists.
  assert.match(svc, /def _deletable_deploy_names/);
  assert.match(svc, /lt\.list_imported_checkpoints\(cfg\.LOCAL_USER, dataset_id, family=family\)/);
});

test('the dataset panel feeds the graph the ★ best-settings pin', () => {
  assert.match(panel, /bestSettingsLora=\{ds\.data\?\.best_settings\?\.lora_filename \|\| null\}/);
  const tree = fs.readFileSync(new URL('./RunLineageTree.jsx', import.meta.url), 'utf8');
  assert.match(tree, /bestSettingsLora=\{bestSettingsLora\}/);
});
