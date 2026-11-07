import { Card, SecretField } from '@lds/plugin-sdk/ui'
import HfTokenHelp from './HfTokenHelp.jsx'

const HF_PUBLISH_TOKEN = {
  key: 'HF_TOKEN', label: 'Shared Hugging Face token', testTarget: null,
  help: 'Use a token with write access to the destination dataset repository. Publishing checks access to the repository you choose.',
}

export default function HfPublishSettings(props) {
  return <Card id="hf-publish-token" title="Authorize dataset publishing">
    <HfTokenHelp />
    <SecretField field={HF_PUBLISH_TOKEN} {...props} />
  </Card>
}
