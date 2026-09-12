// Historical IDs and dates are preserved when ownership moves out of the core feed.
export const MIGRATED_NEWS = [
{
    id: '2026-09-02-publish-to-civitai',
    date: '2026-09-02',
    title: 'Publish a checkpoint and its images to Civitai without leaving the app',
    blurb:
      'A checkpoint pill now has a 📤 Civitai row: create its model page from '
      + 'here (name, trigger words, base model and description pre-filled, the '
      + '.safetensors uploaded, as a draft to finish on Civitai or published at '
      + 'once), or mark the page it already has by pasting its address. Once a '
      + 'checkpoint is linked, the image viewer’s 📤 button posts a picture '
      + 'under that page in one press, with its prompt, seed, sampler and LoRA '
      + 'weight as Civitai generation data. Every image leaves as a fresh PNG '
      + 'with no embedded metadata, and the checkpoint’s own metadata is '
      + 'checked for a machine path before anything is sent. Same key as the '
      + 'scraper and the 🌐 prompt browser.',
    to: '/gallery',
  },
]
