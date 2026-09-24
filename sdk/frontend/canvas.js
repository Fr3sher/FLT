// API 1.9: shared image Studio and lineage controls for alternate workspaces.
import { runtime } from './runtime.js'

export function buildLineageGraph(...args) { return runtime().canvas.buildLineageGraph(...args) }
export function BlendWeightRow(props) { const host = runtime(); return host.React.createElement(host.canvas.BlendWeightRow, props) }
export function BlendSweepSummary(props) { const host = runtime(); return host.React.createElement(host.canvas.BlendSweepSummary, props) }
export function runNumber(...args) { return runtime().canvas.runNumber(...args) }
export function useMediaQuery(...args) { return runtime().canvas.useMediaQuery(...args) }
export function RunSetupPanel(props) { const host = runtime(); return host.React.createElement(host.canvas.RunSetupPanel, props) }
export function readInjectTrigger(...args) { return runtime().canvas.readInjectTrigger(...args) }
export function writeInjectTrigger(...args) { return runtime().canvas.writeInjectTrigger(...args) }
export function useStudioForm(...args) { return runtime().canvas.useStudioForm(...args) }
export const DEPLOY_BAR_CLASS = {
  deployed: 'border-l-[3px] border-solid border-sky-400',
  'on-disk': 'border-l-[3px] border-dashed border-slate-500',
};
export function imageFactsLine(...args) { return runtime().canvas.imageFactsLine(...args) }
export function useImageDownload(...args) { return runtime().canvas.useImageDownload(...args) }
export function datasetThumbUrl(...args) { return runtime().canvas.datasetThumbUrl(...args) }
export function ratchetThumbSide(...args) { return runtime().canvas.ratchetThumbSide(...args) }
export function KleinLoraCombobox(props) { const host = runtime(); return host.React.createElement(host.canvas.KleinLoraCombobox, props) }
export function useKleinGenerationLoras(...args) { return runtime().canvas.useKleinGenerationLoras(...args) }
export function findLora(...args) { return runtime().canvas.findLora(...args) }
export function clampStrength(...args) { return runtime().canvas.clampStrength(...args) }
export const MAX_EXTERNAL_LORAS = 16;
export function contributions(...args) { return runtime().canvas.contributions(...args) }
export const CARD_W = 264;
export const DEPLOY_LEGEND = [
  { tone: 'deployed', glyph: '●', short: 'deployed', label: 'deployed — ready to generate' },
  { tone: 'on-disk', glyph: '○', short: 'on disk', label: 'on disk only — Generate deploys it first' },
];
export function GraphCard(props) { const host = runtime(); return host.React.createElement(host.canvas.GraphCard, props) }
export function CheckpointPill(props) { const host = runtime(); return host.React.createElement(host.canvas.CheckpointPill, props) }
export function LineageEdgeDefs(props) { const host = runtime(); return host.React.createElement(host.canvas.LineageEdgeDefs, props) }
export function LineageEdges(props) { const host = runtime(); return host.React.createElement(host.canvas.LineageEdges, props) }
export function noteBadge(...args) { return runtime().canvas.noteBadge(...args) }
export function toggleDiffSelection(...args) { return runtime().canvas.toggleDiffSelection(...args) }
export function lineageImportPayload(...args) { return runtime().canvas.lineageImportPayload(...args) }
export function removeRunFromTree(...args) { return runtime().canvas.removeRunFromTree(...args) }
export function LineageDetailPanel(props) { const host = runtime(); return host.React.createElement(host.canvas.LineageDetailPanel, props) }
export function LineageDiffPanel(props) { const host = runtime(); return host.React.createElement(host.canvas.LineageDiffPanel, props) }
export function CheckpointActionsPopover(props) { const host = runtime(); return host.React.createElement(host.canvas.CheckpointActionsPopover, props) }
export function ContinueDialog(props) { const host = runtime(); return host.React.createElement(host.canvas.ContinueDialog, props) }
export function continueAttemptOutcome(...args) { return runtime().canvas.continueAttemptOutcome(...args) }
export function PreviewLightbox(props) { const host = runtime(); return host.React.createElement(host.canvas.PreviewLightbox, props) }
export function clampPopoverToViewport(...args) { return runtime().canvas.clampPopoverToViewport(...args) }
export const POPOVER_W = 210;
export function popoverHeight(...args) { return runtime().canvas.popoverHeight(...args) }
export function useCheckpointActions(...args) { return runtime().canvas.useCheckpointActions(...args) }
export function galleryDeleteSummary(...args) { return runtime().canvas.galleryDeleteSummary(...args) }
export function loraFolderLabel(...args) { return runtime().canvas.loraFolderLabel(...args) }
export function runIdentityLabel(...args) { return runtime().canvas.runIdentityLabel(...args) }
export function normalizeExternalLoras(...args) { return runtime().canvas.normalizeExternalLoras(...args) }
export function tintIndexFor(...args) { return runtime().canvas.tintIndexFor(...args) }
export function tintFor(...args) { return runtime().canvas.tintFor(...args) }
export function ExportGridModal(props) { const host = runtime(); return host.React.createElement(host.canvas.ExportGridModal, props) }
export function CheckpointGalleryPanel(props) { const host = runtime(); return host.React.createElement(host.canvas.CheckpointGalleryPanel, props) }
export function externalLoraPayload(...args) { return runtime().canvas.externalLoraPayload(...args) }
export function useStudioRun(...args) { return runtime().canvas.useStudioRun(...args) }
export function useLoraTestStudio(...args) { return runtime().canvas.useLoraTestStudio(...args) }
export function edgePath(...args) { return runtime().canvas.edgePath(...args) }
export function runsHubContinueLanes(...args) { return runtime().canvas.runsHubContinueLanes(...args) }
export const CLOUD_LOCAL_UNAVAILABLE = 'Local continuation of cloud checkpoints is not supported.';
export function explicitRunContinuation(...args) { return runtime().canvas.explicitRunContinuation(...args) }
export function blendConfigCount(...args) { return runtime().canvas.blendConfigCount(...args) }
export function combineBlocker(...args) { return runtime().canvas.combineBlocker(...args) }
export function stackKey(...args) { return runtime().canvas.stackKey(...args) }
export function stackWeight(...args) { return runtime().canvas.stackWeight(...args) }
export function stackWeightList(...args) { return runtime().canvas.stackWeightList(...args) }
export function stackWeightSet(...args) { return runtime().canvas.stackWeightSet(...args) }
export function galleryEndpoints(...args) { return runtime().canvas.galleryEndpoints(...args) }
export const V_GAP = 26;
export const PAD = 22;
export function pillSelectScale(...args) { return runtime().canvas.pillSelectScale(...args) }
export function pillSelectScreenSize(...args) { return runtime().canvas.pillSelectScreenSize(...args) }
