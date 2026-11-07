// Public training history remains available when an optional execution lane is absent.
// The plugin supplies cloud actions; the host owns persisted-run identity and contexts.
import { runtime } from './runtime.js'

function control(name, props) {
  const host = runtime()
  return host.React.createElement(host.training[name], props)
}
export function TrainingProgress(props) { return control('TrainingProgress', props) }
export function BaseModelChip(props) { return control('BaseModelChip', props) }
export function DatasetVersionChip(props) { return control('DatasetVersionChip', props) }
export function RunIdChip(props) { return control('RunIdChip', props) }
export function UseDatasetCaptionsButton(props) { return control('UseDatasetCaptionsButton', props) }
export function RunsHub(props) { return control('RunsHub', props) }
export function RunsHubContent(props) { return control('RunsHubContent', props) }
export function FullArtifactStatus(props) { return control('FullArtifactStatus', props) }
export function RunStatusBadge(props) { return control('RunStatusBadge', props) }
export function AutoRetryBadges(props) { return control('AutoRetryBadges', props) }
export function RecipeWarning(props) { return control('RecipeWarning', props) }
export function timeAgo(...args) { return runtime().training.timeAgo(...args) }
export function famLabel(...args) { return runtime().training.famLabel(...args) }
export function checkpointHref(...args) { return runtime().training.checkpointHref(...args) }
export function postWithConfirmations(...args) { return runtime().training.postWithConfirmations(...args) }
export function retryConfirmableRefusals() { return runtime().training.RETRY_CONFIRMABLE_REFUSALS }
export function TrainingReadiness(props) { return control('TrainingReadiness', props) }
