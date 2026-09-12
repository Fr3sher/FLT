import { Card, SecretField } from './primitives'

// Shared with the core prompt browser and gated downloads, even without scraping.
const CIVITAI_FIELD = {
    key: 'CIVITAI_API_KEY',
    label: 'Civitai API key',
    help: 'One key, three uses: adult content in Civitai scans (without it they return SFW results only), '
      + 'the prompts of the 🌐 Civitai browser, and — with the publishing plugin — posting your '
      + 'checkpoints and generated images from the app. Create one under civitai.com → Account settings → API Keys.',
    // Test = the key shown to Civitai, answering with the account it opens.
    testTarget: 'civitai',
  }

export default function ScrapingSection(props) {
  return (
    <div className="space-y-6">
      <Card id="civitai-credentials" title="Civitai access"
        help="The shared key for the Civitai prompt browser, model downloads and enabled source or publishing tools.">
        <SecretField field={CIVITAI_FIELD} {...props} />
      </Card>
    </div>
  )
}
