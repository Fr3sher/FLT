import { improvePreparations } from '../../utils/improveEngines'
import SettingsLink from './SettingsLink'

/** Visible, keyboard-accessible preparation beside the disabled action. */
export default function ImprovePreparationLinks({ caps }) {
  const preparations = improvePreparations(caps)
  if (!preparations.length) return null
  return (
    <div className="w-full min-w-0 space-y-1 text-xs text-content-muted">
      {preparations.map(engine => (
        <p key={engine.id} className="[overflow-wrap:anywhere]">
          {engine.label} needs preparation.{' '}
          <SettingsLink pluginId={engine.plugin} tone="warning"
            className="inline-flex min-h-10 items-center lg:min-h-0">
            Prepare {engine.label}
          </SettingsLink>
        </p>
      ))}
    </div>
  )
}
