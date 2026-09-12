// Shared host controls preserve provider identity and user interaction rules.
// These are named product contracts, not access to arbitrary core modules.
import { runtime } from './runtime.js'

export const INPUT_CLASS = 'mt-1 w-full rounded-md border border-border-strong bg-surface-raised px-3 py-2 text-sm text-content '
  + 'placeholder:text-content-subtle focus:border-primary focus:outline-none'
export const TAG_CLASS = 'px-1.5 py-px rounded-full bg-app/60 border border-border text-content-muted text-[0.625rem]'
export const ROW_CLS = 'min-h-10 lg:min-h-0 flex items-center gap-1.5 rounded-md border px-2 py-1 text-[0.6875rem] font-medium '
  + 'disabled:cursor-not-allowed disabled:opacity-60'
export const MUTED_CLS = 'rounded-md border border-border bg-app/40 px-2 py-1 text-content-subtle text-[0.625rem]'

function control(name, props) {
  const host = runtime()
  const Component = host.ui?.[name]
  if (!Component) throw new Error(`LDS does not provide the UI control ${name}.`)
  return host.React.createElement(Component, props)
}
export function Card(props) { return control('Card', props) }
export function SecretField(props) { return control('SecretField', props) }
export function TextField(props) { return control('TextField', props) }
export function StatusBadge(props) { return control('StatusBadge', props) }
export function ResetToDefault(props) { return control('ResetToDefault', props) }
export function EngineCard(props) { return control('EngineCard', props) }
export function SettingsLink(props) { return control('SettingsLink', props) }
export function PexelsAttribution(props) { return control('PexelsAttribution', props) }
export function InstallRunner(props) { return control('InstallRunner', props) }
export function KleinModelSetting(props) { return control('KleinModelSetting', props) }
export function PromptOverrideField(props) { return control('PromptOverrideField', props) }
export function useFocusTrap(...args) { return runtime().useFocusTrap(...args) }
export function useCapabilities(...args) { return runtime().useCapabilities(...args) }
export function PluginSlot(props) { return control('PluginSlot', props) }
export function LocationEditor(props) { return control('LocationEditor', props) }

export function ownsTypedKeys(target) {
  if (!target || typeof target !== 'object') return false;
  if (target.isContentEditable) return true;
  const tag = typeof target.tagName === 'string' ? target.tagName.toLowerCase() : '';
  const type = typeof target.type === 'string' ? target.type.toLowerCase() : '';
  if (tag === 'textarea' || tag === 'select') return true;
  return tag === 'input'
    && !['checkbox', 'radio', 'button', 'submit', 'range'].includes(type);
}

export function reviewKeyAction(event) {
  if (!event) return null;
  if (event.metaKey || event.ctrlKey || event.altKey) return null;
  if (event.key === 'Escape') return 'close';
  if (event.shiftKey) return null;
  if (ownsTypedKeys(event.target)) return null;
  const key = typeof event.key === 'string' ? event.key : '';
  const letter = key.toLowerCase();
  if (letter === 'k') return 'keep';
  if (letter === 'r') return 'reject';
  if (letter === 's' || key === 'ArrowRight') return 'skip';
  if (key === 'ArrowLeft') return 'back';
  return null;
}

export function FolderPickerField(props) { return control('FolderPickerField', props) }
export function GuideInfoDot(props) { return control('GuideInfoDot', props) }
export function GeneratedImageLightbox(props) { return control('GeneratedImageLightbox', props) }
export function SliderLock(props) { return control('SliderLock', props) }
export function StudioActionBar(props) { return control('StudioActionBar', props) }
export function Stat(props) { return control('Stat', props) }
export function Chip(props) { return control('Chip', props) }
export function FilterGroup(props) { return control('FilterGroup', props) }
export function GroupLabel(props) { return control('GroupLabel', props) }
export function PassButton(props) { return control('PassButton', props) }
export function hasContributions(...args) { return runtime().hasContributions(...args) }
export function useSliderLock(...args) { return runtime().useSliderLock(...args) }

// Shared job-progress vocabulary is pure and does not require a browser host.
export { progressLabel, renderForJob } from './comfyConsole.js'

export function H3LoraPicker(props) { return control('H3LoraPicker', props) }
