import { INPUT_CLASS, Card } from './primitives'
import { SettingsGroup, SettingsGroupsToc, useSettingsGroupProps } from './SettingsGroupsView'
import { TRAINING_GROUPS } from './settingsGroups'
import ResetToDefault from './ResetToDefault'
import { defaultValueAt } from './settingDefaults.js'

// Keep in sync with backend TRAIN_TYPES (face_dataset_service.py) — 'flux' had
// been forgotten here when the FLUX.1 family landed (fixed alongside flux2klein).
const FAMILY_OPTIONS = ['zimage', 'sdxl', 'krea', 'flux', 'flux2klein', 'anima', 'qwenimage21']


/* Concept face masking (issue #15, reported by shivdbz2010 on GitHub). Both knobs
   are exposed because nobody has measured the right value — no public A/B of a
   concept LoRA trained with vs without face masking exists — so a frozen number
   would be a guess dressed as a default. Every shipped value is read from the
   server payload; a literal here would drift the day the default moves. */
function ConceptFaceMaskCard({ config, setField, configDefaults }) {
  const dflt = (key) => defaultValueAt(configDefaults, 'face_mask', key)
  return (
    <Card title="Concept face masking"
      help="Used only by Concept datasets that turned it on in Advanced training options. It weighs the faces down in the training loss so the concept learns the act, not the identities in your photos. It does not alter your images.">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div>
          <label htmlFor="face-mask-expand" className="block text-sm font-medium text-content">
            Head coverage (face box ×)
          </label>
          <input
            id="face-mask-expand"
            type="number"
            min="1"
            max="3"
            step="0.1"
            value={config.face_mask?.expand ?? dflt('expand')}
            onChange={(e) => setField('face_mask', 'expand', parseFloat(e.target.value) || dflt('expand'))}
            className={INPUT_CLASS}
          />
          <p className="mt-1 text-xs text-content-muted">
            Face detection returns a box from the eyes to the chin. This grows it into a head:
            higher covers hair and jaw, lower stays tight on the face. Preview it on your own
            images from the training panel — the right value depends on how your shots are framed.
          </p>
          <ResetToDefault label="Head coverage" section="face_mask" field="expand"
            config={config} configDefaults={configDefaults} setField={setField} />
        </div>
        <div>
          <label htmlFor="face-mask-min-weight" className="block text-sm font-medium text-content">
            Loss weight kept on faces
          </label>
          <input
            id="face-mask-min-weight"
            type="number"
            min="0.05"
            max="1"
            step="0.05"
            value={config.face_mask?.min_weight ?? dflt('min_weight')}
            onChange={(e) => setField('face_mask', 'min_weight', parseFloat(e.target.value) || dflt('min_weight'))}
            className={INPUT_CLASS}
          />
          <p className="mt-1 text-xs text-content-muted">
            How much the masked area still counts. Lower pushes the identity out harder.
            It does not go to zero on purpose: an area worth nothing is not ignored, it is
            unpenalised — the model can put anything there at no cost, and reports of
            degraded anatomy start right below this floor.
          </p>
          <ResetToDefault label="Loss weight kept on faces" section="face_mask" field="min_weight"
            config={config} configDefaults={configDefaults} setField={setField} />
        </div>
      </div>
    </Card>
  )
}

export default function TrainingSection(props) {
  const { config, setField, configDefaults } = props
  // Core training defaults and masks; cloud preferences belong to Cloud.
  const [defaultsGroup, maskingGroup] = TRAINING_GROUPS
  const groupProps = useSettingsGroupProps('training')
  return (
    <div className="space-y-4">
      <SettingsGroupsToc sectionId="training" groups={TRAINING_GROUPS} />

      <SettingsGroup {...groupProps(defaultsGroup)}>
      <Card title="Defaults" help="Preselected model family for new training runs — each dataset can still override it.">
        <div>
          <label htmlFor="training-default-family" className="block text-sm font-medium text-content">Default training family</label>
          <select
            id="training-default-family"
            value={config.training.default_family}
            onChange={(e) => setField('training', 'default_family', e.target.value)}
            className={INPUT_CLASS}
          >
            {FAMILY_OPTIONS.map((f) => <option key={f} value={f}>{f}</option>)}
          </select>
        </div>
      </Card>
      </SettingsGroup>


      <SettingsGroup {...groupProps(maskingGroup)}>
      <ConceptFaceMaskCard config={config} setField={setField} configDefaults={configDefaults} />
      </SettingsGroup>
    </div>
  )
}
