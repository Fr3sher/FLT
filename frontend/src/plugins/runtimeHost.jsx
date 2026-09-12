import H3LoraPicker from '../components/shared/H3LoraPicker.jsx'
import { canvasServices } from './canvasRuntime.js'
import PromptOverrideField from '../components/common/PromptOverrideField.jsx'
import { improveEngine, availableImproveEngines, improvementAvailable } from './hostCatalog.js'
// JSX services are wired by the application entry, keeping loadPlugins.js
// importable in Node. Every context here is the same one the app provides.
import { useToast } from '../components/common/Toast.jsx'
import { HelpBadge } from '../help/HelpMode.jsx'
import { requestHelpTip } from '../help/helpTips.js'
import GlobalModelPicker from '../components/shared/GlobalModelPicker.jsx'
import { installActionLabel } from './hostCatalog.js'
import { configureRuntimeServices } from './loadPlugins.js'
import { Card, SecretField, TextField, StatusBadge } from '../components/settings/primitives.jsx'
import ResetToDefault from '../components/settings/ResetToDefault.jsx'
import EngineCard from '../components/dataset/EngineCard.jsx'
import SettingsLink from '../components/common/SettingsLink.jsx'
import PexelsAttribution from '../components/dataset/PexelsAttribution.jsx'
import InstallRunner from '../components/setup/InstallRunner.jsx'
import KleinModelSetting from '../components/shared/KleinModelSetting.jsx'
import { useFocusTrap } from '../hooks/useFocusTrap.js'
import { useCapabilities } from '../context/CapabilitiesContext.jsx'
import { localEngineUnavailableReason } from '../utils/localEngineReason.js'
import { postJson as postJsonResult } from '../hooks/useDataset.js'
import PluginSlot, { hasContributions } from './PluginSlot.jsx'
import { LocationEditor } from '../components/shared/LocationEditor.jsx'
import TrainingProgress from '../components/dataset/TrainingProgress.jsx'
import { BaseModelChip, DatasetVersionChip, RunIdChip } from '../components/dataset/RunIdentityBadges.jsx'
import { UseDatasetCaptionsButton } from '../components/dataset/UseDatasetCaptionsButton.jsx'
import { RunsHub, RunsHubContent, FullArtifactStatus, StatusBadge as RunStatusBadge,
  timeAgo, famLabel, AutoRetryBadges, RecipeWarning, checkpointHref } from '../components/runs/RunsHub.jsx'
import { postWithConfirmations, RETRY_CONFIRMABLE_REFUSALS } from '../utils/trainingRefusals.js'
import { VAST_REFERRAL_ID, vastUrl, vastSignupUrl } from '../utils/vastReferral.js'
import VastLink from '../components/common/VastLink.jsx'
import VastReferralDisclosure from '../components/common/VastReferralDisclosure.jsx'
import FolderPickerField from '../components/common/FolderPicker.jsx'
import { GuideInfoDot } from '../components/common/GuideSectionModal.jsx'
import GeneratedImageLightbox from '../components/shared/GeneratedImageLightbox.jsx'
import SliderLock, { useSliderLock } from '../components/shared/SliderLock.jsx'
import StudioActionBar from '../components/dataset/studio/StudioActionBar.jsx'
import { Stat, Chip, FilterGroup, GroupLabel, PassButton } from '../components/bank/BankAtoms.jsx'
import BankLaneTabs, { laneTabClass } from '../components/bank/BankLaneTabs.jsx'
import { loadRailOpen, saveRailOpen, railIsColumn, passesButtonLabel } from '../components/bank/bankLayout.js'
import TrainingReadiness from '../components/dataset/TrainingReadiness.jsx'
import useOllamaFence from '../hooks/useOllamaFence.js'
import { useCanvasImageImprove } from '../hooks/useCanvasImageImprove.js'
import { useRestoreImproveSettings } from '../hooks/useRestoreImproveSettings.js'
import OllamaFenceNotice from '../components/common/OllamaFenceNotice.jsx'
import { GraphCard, CheckpointPill } from '../components/dataset/lineageNodes.jsx'
import { LineageEdgeDefs, LineageEdges } from '../components/dataset/lineageEdges.jsx'
import { buildLineageGraph } from '../utils/lineageGraph.js'
import { clampPopoverToViewport, popoverHeight } from './hostPopover.js'
import { isAbort, saveUrlAsFile } from '../utils/fileSave.js'

export function configureHostRuntime() {
  configureRuntimeServices({ canvas: canvasServices, useToast, HelpBadge, requestHelpTip, GlobalModelPicker, installActionLabel,
    useFocusTrap, useCapabilities, localEngineUnavailableReason, postJsonResult, hasContributions, useSliderLock,
    ui: { H3LoraPicker, Card, SecretField, TextField, StatusBadge, ResetToDefault, EngineCard, SettingsLink,
      PexelsAttribution, InstallRunner, KleinModelSetting, PromptOverrideField, PluginSlot, LocationEditor,
      FolderPickerField, GuideInfoDot, GeneratedImageLightbox, SliderLock, StudioActionBar,
      Stat, Chip, FilterGroup, GroupLabel, PassButton, BankLaneTabs },
    training: { TrainingProgress, BaseModelChip, DatasetVersionChip, RunIdChip,
      UseDatasetCaptionsButton, RunsHub, RunsHubContent, FullArtifactStatus, RunStatusBadge,
      timeAgo, famLabel, AutoRetryBadges, RecipeWarning, checkpointHref,
      postWithConfirmations, RETRY_CONFIRMABLE_REFUSALS, TrainingReadiness },
    links: { vastReferralId: VAST_REFERRAL_ID, vastUrl, vastSignupUrl, VastLink, VastReferralDisclosure },
    inference: { improveEngine, availableImproveEngines, improvementAvailable, useOllamaFence, useCanvasImageImprove, useRestoreImproveSettings, OllamaFenceNotice },
    lineage: { GraphCard, CheckpointPill, LineageEdgeDefs, LineageEdges,
      buildLineageGraph, clampPopoverToViewport, popoverHeight },
    files: { isAbort, saveUrlAsFile },
    bank: { loadRailOpen, saveRailOpen, railIsColumn, passesButtonLabel, laneTabClass },
  })
}
