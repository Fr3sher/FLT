import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

const dialog = fs.readFileSync(new URL('./ContinueDialog.jsx', import.meta.url), 'utf8').replace(/\r\n/g, '\n');
const panel = fs.readFileSync(new URL('./TrainingPanel.jsx', import.meta.url), 'utf8').replace(/\r\n/g, '\n');
const hub = fs.readFileSync(new URL('../runs/RunsHub.jsx', import.meta.url), 'utf8').replace(/\r\n/g, '\n');
const hook = fs.readFileSync(new URL('../../hooks/useDataset.js', import.meta.url), 'utf8').replace(/\r\n/g, '\n');

const read = rel => fs.readFileSync(new URL(rel, import.meta.url), 'utf8').replace(/\r\n/g, '\n');
const cloud = read('../../../../bundled/cloud_training/frontend/CloudRunsHub.jsx');
const controller = read('../runs/useRunsHubContinue.js');
const lane = read('../../../../bundled/cloud_training/frontend/dataset/cloudTraining.js');

test('the dialog resolves a flexible-continue payload (steps, checkpoint, overrides)', () => {
  // fromStep is null only when the newest checkpoint is chosen — the in-place resume.
  assert.match(dialog, /fromStep:\s*isEarlier\s*\?\s*fromStep\s*:\s*null/);
  assert.match(dialog, /extraSteps:\s*extraNum/);
  assert.match(dialog, /overrides:\s*Object\.keys\(overrides\)\.length/);
  assert.match(dialog, /resumeMode,/);
  assert.match(dialog, /stateBundleId:\s*resumeMode === 'full_state'/);
  // safe subset only — cadence + preview prompts, never rank/base/optimizer.
  assert.match(dialog, /overrides\.save_every/);
  assert.match(dialog, /overrides\.sample_every/);
  assert.match(dialog, /overrides\.sample_prompts/);
  // its own help topic (registered in helpRegistry)
  assert.match(dialog, /topic="continue-training"/);
});

test('both hubs open the shared ContinueDialog', () => {
  assert.match(panel, /import ContinueDialog from '\.\/ContinueDialog'/);
  assert.match(panel, /<ContinueDialog/);
  assert.match(hub, /import ContinueDialog from '\.\.\/dataset\/ContinueDialog\.jsx'/);
  assert.match(hub, /<ContinueDialog \{\.\.\.dialog\}/);
});

test('local continue still routes through the guarded, accumulating request helper', () => {
  assert.match(panel, /runConfirmableTrainingRequest/);
  assert.match(panel, /\(continueOpts\) => \{/);
  assert.match(panel, /if \(pluginLane\) \{[\s\S]*?pluginLane\.resume\(payload/);
  assert.match(panel, /return ds\.continueTraining\(/);
  assert.match(panel, /fromStep:\s*payload\.fromStep,\s*overrides:\s*payload\.overrides/);
  assert.match(panel, /resumeMode:\s*payload\.resumeMode,\s*stateBundleId:\s*payload\.stateBundleId/);
  assert.match(panel, /confirmableRetryFlag\(error, 'Continue anyway \(force\)'\)/);
});

test('cloud continue posts the run, extra steps, chosen checkpoint and overrides', () => {
  assert.match(cloud, /from_step:\s*payload\.fromStep/);
  assert.match(cloud, /overrides:\s*payload\.overrides/);
  assert.match(cloud, /extra_steps:\s*payload\.extraSteps/);
  assert.match(cloud, /resume_mode:\s*payload\.resumeMode \|\| 'weights_only'/);
});

test('the continue hook forwards from_step and overrides only when present', () => {
  assert.match(hook, /opts\.fromStep\s*!=\s*null\s*\?\s*\{\s*from_step:\s*opts\.fromStep\s*\}/);
  assert.match(hook, /opts\.overrides\s*\?\s*\{\s*overrides:\s*opts\.overrides\s*\}/);
  assert.match(hook, /resume_mode:\s*opts\.resumeMode \|\| 'weights_only'/);
  assert.match(hook, /opts\.stateBundleId\s*\?\s*\{\s*state_bundle_id:\s*opts\.stateBundleId\s*\}/);
});

test('full state is selectable only for a verified exact local bundle', () => {
  assert.match(dialog, /defaultResumeMode\(selectedCheckpoint, lane\)/);
  assert.match(dialog, /aria-label="Training state to restore"/);
  assert.match(dialog, /value="full_state"/);
  assert.match(dialog, /disabled=\{!fullStateAvailable\}/);
  assert.match(dialog, /value="weights_only"/);
  assert.match(dialog, /\{fullStateReason && \(/);
});

test('the quick previous-run prompt opens the explicit Continue dialog', () => {
  assert.match(panel, /if \(mode === 'continue'\)/);
  assert.match(panel, /setContinueOpen\(true\)/);
  assert.doesNotMatch(panel, /resolveResume\('resume'\)/);
  assert.match(panel, /resolveResume\('continue'\)/);
});

test('the dialog offers the LR factor knob and sends it only as a real reduction', () => {
  // a factor selector in the safe-overrides section, with its resulting-value hint
  assert.match(dialog, /LR_FACTOR_CHOICES/);
  assert.match(dialog, /half \(polish\)/);
  assert.match(dialog, /tenth \(gentle finish\)/);
  assert.match(dialog, /aria-label="Learning rate for the continuation"/);
  // keep-current (1) and adaptive (Prodigy) runs never send lr_factor
  assert.match(dialog, /!trajectoryLocked\s*&&\s*lrFactor\s*!==\s*1\s*&&\s*!isAdaptiveLR/);
  assert.match(dialog, /overrides\.lr_factor\s*=\s*lrFactor/);
  // Prodigy disables the control with a reason rather than hiding it silently
  assert.match(dialog, /isAdaptiveLR\s*=\s*String\(settings\.optimizer\s*\|\|\s*''\)\.startsWith\('prodigy'\)/);
  assert.match(dialog, /disabled=\{isAdaptiveLR \|\| trajectoryLocked\}/);
  // the hint shows the resulting rate (→ 5e-5) computed from the run's current LR
  assert.match(dialog, /fmtLR\(currentLR\s*\*\s*lrFactor\)/);
});

test('full state locks trajectory-changing cadence, timestep and LR controls', () => {
  assert.match(dialog, /trajectoryLocked\s*=\s*resumeMode === 'full_state'/);
  assert.match(dialog, /!trajectoryLocked\s*&&\s*saveEvery\s*!==\s*inheritedSave/);
  assert.match(dialog, /!trajectoryLocked\s*&&\s*sampleEvery\s*!==\s*inheritedSampleEvery/);
  assert.match(dialog, /disabled=\{trajectoryLocked\}\s*aria-label="Checkpoint frequency"/);
  assert.match(dialog, /disabled=\{trajectoryLocked\}\s*aria-label="Preview sample frequency"/);
  assert.match(dialog, /!trajectoryLocked.*overrides\.timestep_type\s*=\s*timestep/s);
  assert.match(dialog, /disabled=\{trajectoryLocked\}[\s\S]*aria-label="Timestep weighting/);
  assert.match(dialog, /Full state keeps the learning rate, timestep trajectory and save\/preview cadence exact/);
});

test('both hubs feed the dialog the run optimizer + current LR for the hint', () => {
  assert.match(panel, /optimizer:\s*adv\?\.optimizer,\s*learning_rate:\s*adv\?\.learning_rate/);
  assert.match(controller, /optimizer:\s*target\.settings\?\.optimizer/);
  assert.match(controller, /learning_rate:\s*target\.settings\?\.lr/);
});

test('the dialog can open on a specific checkpoint (◉ Graph "continue from here")', () => {
  // opt-in prop, resolved by the unit-tested rule (lineageContinue.test.js):
  // the requested step when it is a real save, else the newest.
  assert.match(dialog, /initialFromStep\s*=\s*null/);
  assert.match(dialog, /initialResumeStep\(initialFromStep, steps\)/);
  assert.match(dialog, /import \{ initialResumeStep, resolveInitialLane, submitBlockedReason \} from '\.\/lineageContinue\.js'/);
});

test('the dialog can offer the LANE (local vs cloud), opt-in and reasoned', () => {
  // opt-in prop: absent → no picker at all (the Runs hub keeps today's dialog)
  assert.match(dialog, /lanes = null/);
  assert.match(dialog, /\{lanes && \(/);
  assert.match(dialog, /resolveInitialLane\(where, lanes\)/);
  // both lanes rendered as radios, a closed one disabled WITH its reason shown
  assert.match(dialog, /aria-label="Where to run the continuation"/);
  assert.match(dialog, /💻 Local/);
  assert.match(dialog, /☁ Cloud/);
  assert.match(dialog, /disabled=\{off\}/);
  assert.match(dialog, /laneState\(lane\)\.reason/);
  // The chosen lane rides the payload, and a blocked lane can't be submitted.
  // Asserted as "the field is in the object" rather than "the field is followed
  // by that exact comment": the adjacency version broke the day a second field
  // was added next to it, which said nothing about the lane at all.
  assert.match(dialog, /onResolve\(\{[\s\S]*?\blane,\r?\n/);
  assert.match(dialog, /disabled=\{busy \|\| latest === 0 \|\| laneBlocked/);
});

test('a full model can choose HOW its 26 GB reaches the pod, priced', () => {
  // Opt-in like the lane picker: absent → no picker, and the backend keeps its
  // own default (the Hugging Face copy), which is what shipped before.
  assert.match(dialog, /transportPlan = null/);
  assert.match(dialog, /\{transportPlan && \(/);
  assert.match(dialog, /initialTransport\(transportPlan\)/);
  assert.match(dialog, /aria-label="How the checkpoint reaches the pod"/);
  // Both roads always rendered; a closed one disabled WITH its reason.
  assert.match(dialog, /TRANSPORTS\.map/);
  assert.match(dialog, /disabled=\{off\}/);
  // A closed road explains itself ON SCREEN, not in a `title` tooltip that no
  // screenshot, touch screen or screen reader ever surfaces.
  assert.match(dialog, /closedRoads\(transportPlan\)\.map/);
  assert.match(dialog, /is unavailable: \{reason\}/);
  // The numbers, and where they came from — the reason this picker exists.
  assert.match(dialog, /transportSummary\(transportOption\(transportPlan\.options, transport\)\)/);
  assert.match(dialog, /rateNote\(transportOption\(transportPlan\.options, transport\)\)/);
  // The choice rides the payload, and a closed road cannot be submitted.
  assert.match(dialog, /transport: transportPlan \? transport : undefined/);
  assert.match(dialog, /\|\| transportReason/);
});

test('the Runs hub fetches that plan and sends the chosen road', () => {
  assert.match(controller, /initialFromStep: initialStep, lanes, transportPlan/);
  assert.match(cloud, /\/api\/dataset\/train\/cloud\/resume-plan/);
  assert.match(cloud, /payload\.transport \? \{ transport: payload\.transport \}/);
  // A missing forecast must never block the resume: the roads still exist and
  // the backend still refuses the impossible one with its reason.
  assert.match(controller, /setTransportPlan\(null\)/);
  assert.match(controller, /cloud\.plan\(run\)[\s\S]*?\.catch\(\(\) =>/);
});

test('the Runs hub offers the picker too, with its own lane rule', () => {
  // It used to pass no `lanes` (a deliberate scope choice) and silently
  // relaunched a pod — Continue opened from the Runs page gave no choice at all.
  assert.match(controller, /const lanes = target \? \{ local, cloud: remote \|\| \{/);
  assert.match(controller, /available: false, reason: 'Cloud training is disabled in this install\.'/);
  assert.match(controller, /explicitRunContinuation\(run, \{ lane: 'local' \}\)/);
  // the hub's guards differ from the panel's (many datasets, machine-wide local
  // single-flight), so they live in their own unit-tested rule
  assert.match(cloud, /runsHubContinueLanes\(run/);
  assert.match(controller, /localContinuationAvailability\(target/);
});

test('the dataset panel routes the chosen lane to the matching call', () => {
  // ONE dialog, two hooks — no third resume path, same guarded request helper
  // (the lane is normalised through preflightLane.js now — same rule, one place,
  // because the preflight gate needs it too)
  assert.match(panel, /const lane = laneOfPayload\(payload\)/);
  assert.match(panel, /pluginLanes\.find\(\(l\) => l\.id === lane/);
  assert.match(panel, /pluginLane\.resume\(payload/);
  assert.match(panel, /if \(lane !== 'local'\) return \{ ok: false, error: 'This training plugin is disabled\.'/);
  assert.match(panel, /return ds\.continueTraining\(/);
  assert.match(panel, /lanes=\{continueLanes\}/);
  assert.match(panel, /where=\{continueSource\?\.source \|\| laneOfStep\(continueInitialStep\)\}/);
  // each lane carries its own honest reason, cloud reusing the app's single source
  assert.match(lane, /Cloud training needs a vast\.ai API key/);
  assert.match(panel, /Local training needs ai-toolkit/);
  assert.match(lane, /reason \? \{ available: false, reason \}/);
});

test('the cloud lane posts the local checkpoint to the continue-local endpoint', () => {
  assert.match(lane, /train\/cloud\/continue-local/);
  // it reuses the local payload shape (selection + safe overrides + from_step)
  assert.match(lane, /async resume\(payload, \{ ds, base, variant, trainType, opts, toast \}\)/);
  assert.match(hook, /opts\.fromStep != null \? \{ from_step: opts\.fromStep \} : \{\}/);
  assert.doesNotMatch(hook, /continueTrainingInCloud/);
  assert.match(panel, /contributions\('training\.continue\.lane', 'dataset'\)/);
});

test('a ◉ Graph checkpoint pill opens the cloud Continue dialog pre-filled', () => {
  const graph = fs.readFileSync(new URL('./RunLineageGraph.jsx', import.meta.url), 'utf8').replace(/\r\n/g, '\n');
  const tree = fs.readFileSync(new URL('./RunLineageTree.jsx', import.meta.url), 'utf8').replace(/\r\n/g, '\n');
  // the graph surfaces a "continue from here" action, threaded through the tree.
  // The action itself lives in the SHARED popover now (one popover for the graph
  // and the canvas); the graph's job is to hand it the mount's handler.
  const popover = fs.readFileSync(new URL('./CheckpointActionsPopover.jsx', import.meta.url), 'utf8').replace(/\r\n/g, '\n');
  assert.match(graph, /onContinue=\{typeof onContinueCheckpoint === 'function' \? onContinueCheckpoint : undefined\}/);
  assert.match(popover, /onClick=\{\(\) => \{ onContinue\(node, pill\); onClose\?\.\(\); \}\}/);
  assert.match(tree, /onContinueCheckpoint=\{onContinueCheckpoint\}/);
  // the Runs page maps a pill to the run and opens the dialog on that step
  assert.match(controller, /continueFromCheckpoint/);
  assert.match(controller, /open\(\{[\s\S]*?pill\?\.step \?\? null\)/);
  assert.match(controller, /initialFromStep: initialStep/);
});
