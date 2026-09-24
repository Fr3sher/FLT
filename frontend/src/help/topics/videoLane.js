/* One section of the help registry, moved verbatim (2026-08-24 split).
   ORDER MATTERS inside and across sections: helpRegistry.js concatenates
   the six section arrays in a fixed order, and for a given (chapter,
   anchor) the FIRST topic owns the "Open this screen →" button. */
import { action } from '../topicBuilders.js';

export const VIDEO_LANE_TOPICS = [
  // ---- 🎬 the video lane -------------------------------------------------
  // Its own page topic rather than keywords bolted onto page-bank: someone with
  // a folder of rushes searches for "video", and until this lane existed the
  // honest answer was "your .mp4 files are skipped without a word".

  // 🎬 One video training set's workspace. Its own PAGE topic rather than
  // keywords on page-video-bank, because the two answer opposite questions: the
  // bank is where you decide WHICH shots, this is where you work on what the
  // encode produced. Someone whose set has three bad clips in it is not helped
  // by shot-detection troubleshooting.
  //
  // `app.route` is the LIBRARY and not `/video-dataset/<id>`: the workspace
  // needs an id nobody can put in a static registry, and the library is the one
  // address that always exists and always leads here in one click.

  // 🎬 The Video tab of the Test Studio. Its own PAGE topic rather than keywords
  // on page-studio: the two lanes share a screen but nothing else — different
  // tables, different pipeline, one clip instead of a grid — and someone whose
  // video LoRA renders nothing is not helped by the Z-Image troubleshooting the
  // image topic carries.

  // ⚡ The acceleration choice of the Render panel: searched by the names
  // people read in the arena and by what they are looking for ("faster",
  // "which turbo").

  // ⏭ Continue: the last frame as the next start frame, the render joined
  // behind. Searched by the gesture ("continue", "extend", "longer") and by
  // what the result is ("joined", "one video").

  // The batch's prompt: one for all, or one written per picture.

  // ↗ Smooth asks for the rate before it runs. Searched for by the gesture
  // ("smooth", "interpolate"), by the numbers ("48 fps", "60 fps", "why not
  // 60") and by what it costs.

  // 🔴 The Live lane: the same engine as a channel that never stops. Searched
  // for by the idea ("stream", "tv channel", "endless"), by the player ("vlc",
  // "hls"), by the dials ("playback rate", "fps") and by what goes wrong
  // ("behind", "slow motion", "buffering").

  // The start frame picker: its four sources and the 🔍 that sizes their tiles.
  // Searched for by what someone holds (a bank image, a generated picture, a
  // clip of the set), by the gesture ("bigger thumbnails") and by the tab that
  // "does not work" — the Dataset clip tab came up empty-looking once.

  // The ✨ writers of the Motion field. Searched for by the gesture ("auto",
  // "enrich"), by the format the answer comes back in (people paste H3's field
  // names and "<Picture 1>" from a prompt they did not write), by the ⚙ choice
  // and by what went wrong (the lock notice, "queued without enrichment").
  // Listed AFTER the page topic: for one (chapter, anchor) the first topic
  // owns the "Open this screen" button, and that is the page's.

  // ⚡ The preset chips under the Motion field. Searched for by the gesture
  // ("preset", "template", "example prompt"), by what people want out of them
  // (a camera move, an audio bed, a voice line, a multi-shot cut) and by the
  // two questions the format raises: whether a chip wipes what is written, and
  // what happens to "<Picture 1>" when there is no picture.

  // Searched for by what people TRIED and could not do: they pasted a RedGifs or
  // TikTok link into the image scraper and got "no images found", or they
  // downloaded clips by hand into a folder because nothing else was on offer.


  // Nobody searches "burst mode" until they have seen it. They search the
  // SYMPTOM of not having it — "triage faster", "too many clicks" — or the
  // thing they just pressed and nothing happened ("K does nothing").


  // People search for the SYMPTOM ("the cut is one second too early", "half my
  // clip is frozen"), and — since it is the discovery this tool folds in — for
  // the i2v conditioning frame, which they will have read about in a trainer's
  // README long before they connect it to a control called "trim".

  // The symptoms this one answers are the loudest in the whole lane: "it cut my
  // video into 60 pieces" and "it missed every cut". Both are the SAME control,
  // and until it was exposed the honest answer was "you cannot change that".



  // The symptoms: a search that cannot find an action, a dataset that trained on
  // nothing, and "why did my caption come back after I fixed it" (it must not).

  // The symptom is "my captions are vague" — nobody searches for "prompt style".

  // Two symptoms bring people here and neither mentions "audio metrics": a
  // trained model that came out silent, and an audio cut that flags nothing.
  // The second is almost always a bank measured before sound was looked at.

  // Nobody searches "max_per_source". They search the SYMPTOM: a set that came
  // out dominated by one file, or the question of whether the cap picks at
  // random (it does not — earliest first, so the same bank gives the same set).


  // People arrive here from the SYMPTOM ("I can't find the shot with the car")
  // and from the two failures that look like bugs: a search that returns nothing
  // because the pass never ran, and a "without" that returns exactly what was
  // excluded — which is CLIP ignoring the word, not the app ignoring the user.
  // Searched for by the SYMPTOM — "I have the same shot twenty times", "my LoRA
  // only draws one pose" — long before anyone looks for a control called dedup.


  // Arrived at from the SYMPTOM in almost every case — "my LoRA writes
  // subtitles", "black bars in every generation" — long before anyone goes
  // looking for a control named after the measurement. The install question
  // ("bands only") is here too: it is the one capability in the app whose
  // absence downgrades a pass instead of blocking it, so the sentence a user
  // meets is unlike every other missing-extra sentence.

  // Reached from the SYMPTOM in every case — "my LoRA output looks mushy",
  // "everything I generate has blocks in it", "this 1080p file does not look
  // like 1080p" — and from the one question this pass exists to answer that
  // nothing else in the app can: whether a file was upscaled. The sharpness
  // floor measures a small analysis copy and cannot see it, so a user who has
  // already set that cut and still gets soft output arrives here next.

  // Reached from the WORRY as much as from the feature name — "is this clip
  // real", "my scrape is full of AI slop" — and from the two questions the
  // hedge provokes the moment somebody sees the chip: how sure is it, and why
  // does the Bank say "AI" about a still while this says "may be". The keywords
  // carry both spellings of the cut, because its polarity is the thing people
  // get wrong.

  // 🎥 Two things people will search for and one they will complain about. The
  // complaint is the missing "tilt up" — the trainer's own vocabulary has it and
  // this pass never emits it — so the keywords carry the words nobody will find
  // as chips, and the Guide section says why they are absent rather than
  // leaving someone convinced the detection is broken.

  // 🔗 Two searches to serve and one misconception to head off. People will look
  // for this by the SYMPTOM ("two scenes in one clip", "the detector missed a
  // cut") rather than by the number's name, so those phrases carry the keywords.
  // The misconception is the one the calibration refuted: someone will assume a
  // near-1 coherence means "nothing moves" and go looking for a still filter
  // here — the keywords bring them to a section that says where stillness
  // actually lives.




  // The library is what "Open this screen →" should open for this anchor, so the
  // /datasets topic is listed FIRST (see the ordering note at the top).

  // The four sections of the video dataset workspace. One topic each, exactly
  // like `workspace-*` on the image side — the ? badge in a section header has
  // to resolve to something, and a section without one is a screen the Guide
  // cannot answer a question about.















  // 🧹 The button beside that readout: the same anchor, because the guide
  // explains it in the same paragraph — what holds the memory, what the
  // button gives back, and when it refuses.







  // 🪪 The reference face on the board. Worth its own topic: it is the only
  // picture on the canvas that is NOT a pinned render, so every question about
  // it ("why can't I move it / close it / export it") misses the topics above.


  action('canvas-download-images', '⬇ Download images (one, a selection as files, or a ZIP)',
    ['download an image', 'download image', 'save an image', 'save the picture',
     'export generated images', 'download all images', 'download the gallery',
     'zip', 'download as zip', 'download a run', 'get my images out',
     'save to disk', 'keep this render', 'file name', 'which checkpoint made this',
     'rename downloaded images', 'download selected images', 'download 500',
     'why only 500', 'zip is smaller than the gallery', 'missing from the zip',
     'image no longer on disk', 'download does nothing',
     // 🖼 Gallery's ⬇ Files — the un-ZIP. Asked about in both directions:
     // people who want it, and people whose browser just prompted about it.
     'without zip', 'no zip', 'individual files', 'separate files',
     'download each file', 'files not archive', 'plain files',
     'allow multiple downloads', 'browser asked to download multiple files',
     'downloads one by one'],
    '/canvas', 'using-the-app', 'the-lora-canvas-every-run-on-one-board'),
  // 🖼🖼 A gesture nobody can guess: it earns a topic of its own, not a clause
  // buried in the one above. Half these keywords are how someone who has
  // ALREADY done it by accident would describe what happened.


  action('generated-image-facts', 'What a generated image was made with',
    ['seed', 'copy the seed', 'copy the prompt', 'prompt too long', 'sampler',
     'scheduler', 'cfg', 'sampling steps', 'base model', 'lora file',
     'always-on loras', 'face similarity', 'image settings', 'image metadata',
     'what settings made this image', 'replay a seed', 'lightbox'],
    '/canvas', 'using-the-app', 'the-lora-canvas-every-run-on-one-board'),

  action('checkpoint-gallery-delete', 'Delete images from a checkpoint’s gallery',
    ['delete an image', 'delete images', 'remove a photo', 'remove images',
     'delete test images', 'clean up a checkpoint', 'too many images',
     'bad renders', 'failed test images', 'select images', 'select mode',
     'where is the select button', 'select button moved', 'no delete button',
     'delete several images', 'where do deleted images go', 'undo a delete',
     'restore a deleted image', 'does it delete from the test studio'],
    '/canvas', 'using-the-app', 'the-lora-canvas-every-run-on-one-board'),

  action('checkpoint-actions', 'Checkpoint actions (download, deploy, undeploy, delete)',
    ['click a checkpoint', 'checkpoint actions', 'checkpoint popover', 'download a checkpoint',
     'deploy a checkpoint', 'undeploy', 'remove from comfyui', 'delete a checkpoint',
     'delete the training save', 'continue from here', 'run details', 'details button',
     'why is deploy greyed out', 'cannot download this save'],
    '/canvas', 'using-the-app', 'the-lora-canvas-every-run-on-one-board'),
  { id: 'page-cloud', kind: 'page', title: 'Runs (cloud & local)',
    keywords: ['runs', 'cloud', 'vast', 'stuck', 'history', 'training', 'gpu',
      'lineage', 'tree', 'genealogy', 'graph', 'continue', 'resumed', 'branch', 'superseded', 'descend',
      'checkpoints', 'checkpoint', 'epoch', 'download', 'continue from here'],
    guide: { chapter: 'troubleshooting', anchor: 'a-cloud-run-seems-stuck' },
    app: { route: '/cloud' } },
  action('runs-test-in-studio', '🧪 Test a run in Studio',
    ['test in studio', 'test studio from runs', 'open studio from a run', 'test a run',
      'test checkpoint', 'run dataset', 'open the right dataset', 'compare run checkpoints'],
    '/cloud', 'using-the-app', 'test-a-run-straight-from-runs'),
  action('lineage-inspect-notes', 'Inspect a run & take notes',
    ['inspect run', 'run settings', 'settings used', 'lineage notes', 'config',
     'compare runs', 'note', 'annotate', 'lab', 'rank', 'learning rate',
     'which params', 'experiment',
     // Also reachable straight from a checkpoint card's ⚙ Details button.
     'run details', 'details button', 'from checkpoints', 'checkpoint card'],
    '/cloud', 'dataset-guide', '6-after-training-pick-the-right-checkpoint'),
  action('lineage-compare-runs', 'Compare two runs side by side',
    ['compare runs', 'compare two runs', 'diff', 'difference', 'what changed',
     'side by side', 'shift click', 'lineage compare', 'ab compare', 'settings diff',
     'which setting changed', 'experiment', 'lab',
     // The compare drawer now answers dataset and machine questions too, so the
     // words a user would actually type for those must reach this topic.
     'caption changed', 'which captions changed', 'caption diff', 'which images',
     'image added', 'image removed', 'deleted image', 'which image did i delete',
     'dataset changed', 'ai-toolkit version', 'torch version', 'cuda', 'gpu',
     'base model changed', 'snapshot', 'provenance', 'reproduce a run',
     // Also reachable straight from a checkpoint card's ⇄ Compare picks.
     'compare from checkpoints', 'compare button', 'checkpoint card'],
    '/cloud', 'dataset-guide', '6-after-training-pick-the-right-checkpoint'),
  action('lineage-remove-gone-run', 'Remove a gone run from the graph',
    ['remove run', 'delete run', 'gone', 'tidy graph', 'clean up runs',
     'no checkpoints', 'clear run', 'lineage cleanup'],
    '/cloud', 'dataset-guide', '6-after-training-pick-the-right-checkpoint'),
  action('lineage-generate-previews', 'Generate a preview per checkpoint',
    ['generate preview', 'preview checkpoint', 'inline generation', 'sample image',
     'same prompt', 'same seed', 'epoch by epoch', 'compare checkpoints', 'strength 1.0',
     'test studio', 'experiment lab', 'lab', 'which epoch', 'best checkpoint',
     'big previews', 'large previews', 'big preview mode', 'comfyui grid', 'preview tiles'],
    '/cloud', 'dataset-guide', '6-after-training-pick-the-right-checkpoint'),
  action('lineage-import-checkpoint', 'Import a checkpoint from the graph',
    ['import checkpoint', 'deploy checkpoint', 'import from graph', 'loras folder',
     'deploy lora', 'use this checkpoint', 'graph import', 'pill import', 'comfyui',
     'view preview large', 'zoom preview', 'lightbox', 'graph view', 'default view'],
    '/datasets?section=checkpoints', 'dataset-guide', '6-after-training-pick-the-right-checkpoint'),
  action('lineage-delete-checkpoint', 'Remove a deployed LoRA or delete a training save',
    ['delete checkpoint', 'delete save', 'remove checkpoint', 'trash checkpoint',
     'remove from comfyui', 'undeploy lora', 'delete training save', 'free disk space',
     'too many epochs', 'graph delete', 'pill delete', 'does it delete my lora',
     'imported lora kept', 'best settings warning'],
    '/datasets?section=checkpoints', 'dataset-guide', '6-after-training-pick-the-right-checkpoint'),
  action('lineage-undeploy-checkpoint', 'Undeploy a LoRA from ComfyUI (reversible)',
    // Same topic for the ◉ Graph pills and the Checkpoints & LoRAs rows — the
    // two surfaces now offer the SAME control, so they must not teach two answers.
    ['undeploy', 'undeploy lora', 'remove from comfyui', 'unimport', 'un-deploy',
     'deployed badge', 'no undeploy button', 'take it out of comfyui', 'redeploy',
     'deploy again', 'training save kept', 'reversible',
     'already deployed', 'which lora is in comfyui', 'also in comfyui',
     'import again', 'imported twice', 'orphan lora', 'run ?'],
    '/datasets?section=checkpoints', 'dataset-guide', '6-after-training-pick-the-right-checkpoint'),

  action('storage-measure', 'See what each folder weighs',
    ['what lives where', 'disk usage', 'measure', 'how big', 'size', 'space',
     'where are my files', 'which folder', 'free space', 'drive'],
    '/settings/storage', 'settings-reference', 'storage'),
  action('storage-move-location', 'Move a folder to another drive',
    ['move', 'relocate', 'another drive', 'change folder', 'd drive', 'c drive full',
     'disk full', 'out of space', 'external drive', 'adopt', 'start empty',
     'move my datasets', 'move my checkpoints'],
    '/settings/storage', 'settings-reference', 'storage'),

  action('storage-checkpoint-store', 'Where trained checkpoints are kept',
    ['checkpoint store', 'safetensors', 'lost checkpoint', 'deleted my checkpoint',
     'cleanup deleted', 'purge deleted my lora', 'stray checkpoint', 'durable',
     'move stray checkpoints'],
    '/settings/storage', 'settings-reference', 'storage'),
];
