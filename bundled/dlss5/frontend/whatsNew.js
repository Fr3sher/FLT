export const WHATS_NEW = [

{
    id: '2026-09-22-dlss5-open-folder',
    date: '2026-09-22',
    title: 'Open your DLSS 5 video folder in one click',
    blurb: 'Open folder below the selected video opens its folder on the computer running LDS, with the untouched original and any rendered result. It is available as soon as you import a clip.',
    to: '/dlss5',
  },

{
    id: '2026-09-02-video-neural-render',
    date: '2026-09-02',
    title: 'Re-render video clips with DLSS 5 Neural Rendering',
    blurb:
      'A Neural render button on the clips of a video dataset and on the finished '
      + 'clips of the Test Studio runs the NVIDIA DLSS 5 model over them: skin, hair '
      + 'and fabric gain structure the source only implied. In a dataset the render '
      + 'replaces the clip and the original is kept (Restore); in the studio it is a '
      + 'new clip to compare. A ⇔ Compare button plays the original and the render '
      + 'side by side, in step, with a 1:1 zoom. Strength, passes and a 2× working size '
      + 'push the effect well past the model\'s default. Windows + NVIDIA only; Setup '
      + 'installs the bridge, you bring the model file.',
    to: '/datasets',
  },

{
    id: '2026-09-03-compare-export',
    date: '2026-09-03',
    title: 'Save a before/after comparison as one video',
    blurb:
      'The ⇔ comparison has an ⬇ Export button: the original and its neural '
      + 'render are encoded into ONE mp4, side by side and labelled, so a '
      + 'before/after can be shown to somebody who does not have the app — on a '
      + 'rendered clip of a training set and on a render in the Test Studio '
      + 'alike. The exported file starts with no metadata at all, because a '
      + 'clip out of the studio carries the whole generation workflow — prompts '
      + 'and folder paths included — in a tag nothing displays.',
    to: '/studio?lane=video',
  },

]
