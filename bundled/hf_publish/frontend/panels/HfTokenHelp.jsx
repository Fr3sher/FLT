import { HelpBadge } from '@lds/plugin-sdk'

export default function HfTokenHelp() {
  return <p className="text-sm text-content-muted">
    Publishing datasets needs write permission on the destination repository. A read token is enough for model downloads but cannot publish.
    {' '}<a href="https://huggingface.co/settings/tokens/new?tokenType=fineGrained" target="_blank" rel="noreferrer" className="underline">
      Create a token with write access to your dataset repository
    </a>. Save it in the token field below. It is the same stored credential used for gated model downloads; replacing or removing it applies everywhere. <HelpBadge topic="hf-publish" />
  </p>
}
