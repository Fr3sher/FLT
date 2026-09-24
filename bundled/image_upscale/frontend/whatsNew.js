export const NEWS = [
  {
    "id": "2026-09-07-klein-improve-seedvr2-split",
    "date": "2026-09-07",
    "title": "Klein Improve and SeedVR2 can be installed separately",
    "blurb": "Klein Improve 1.1 keeps its prompt, LoRA presets, image actions and finishing. Faithful SeedVR2 restoration is a separate Store plug-in; install it only when you want that engine. Existing settings and results are preserved.",
    "to": "/plugins/image_upscale/settings?focus=klein-improve-settings"
  },
  {
    "id": "2026-09-01-bank-improve-carries-the-dials",
    "date": "2026-09-01",
    "title": "The bank’s ✨ improve shows the dials it obeys, instead of naming them",
    "blurb": "Improving a whole bank ran on the same instruction, LoRA preset, strengths and output size as a dataset improve — and its launch window listed them as things to go and change in Settings. They are in the window now, exactly as in the dataset one, whenever Klein is the engine.",
    "to": "/bank"
  },
  {
    "id": "2026-09-01-improve-panel-lora-strengths",
    "date": "2026-09-01",
    "title": "Tune a preset’s LoRAs from the picture they apply to",
    "blurb": "The ✨ Upscale & improve window named which LoRA preset it chains and then said nothing about what was in it, so the one number you actually change — how hard a LoRA pulls — still meant a trip to Settings. The window now lists the preset’s LoRAs with a slider each, saved as you drag. Building the presets themselves (adding, removing, reordering) stays in Settings ▸ Engines: those change what a preset IS, for every surface that runs Klein.",
    "to": "/gallery"
  },
  {
    "id": "2026-09-01-improve-result-zoom",
    "date": "2026-09-01",
    "title": "Zoom into the improved picture without leaving the window",
    "blurb": "An upscale is judged on detail that fit-to-window hides. The result now takes the wheel, a pinch on a touchscreen and a double-tap to fit again — the same gestures the image viewer has always had, and never past the picture’s own pixels.",
    "to": "/gallery"
  },
  {
    "id": "2026-08-29-improve-settings-window",
    "date": "2026-08-29",
    "title": "✨ Improve now opens its settings in a window — and shows you the result",
    "blurb": "Press ✨ Improve via Klein anywhere — dataset, Gallery, Canvas, a checkpoint gallery — and a window opens with the instruction (editable in place), model, LoRA preset and output size, then a Generate button. Stay and the finished picture appears right there; leave early and it lands where it always did, with a toast saying where. The image viewers keep their action bars short — the batch toolbar keeps its inline note, since a batch should show its instruction before launching a lot."
  },
  {
    "id": "2026-08-24-use-these-improve-settings",
    "date": "2026-08-24",
    "title": "Like a ✨ result? Make the next improves run the same way",
    "blurb": "Open any Upscale & improve result (Gallery, checkpoint gallery, or pinned on the Canvas) and press ↩ Use these improve settings: the instruction, LoRA preset, strength, steps, output size and Klein model this image was made with become the app-wide improve settings again. New improvements record all of it from now on; older images restore what they carry (instruction + preset), and the toast names exactly which halves happened — a preset renamed or deleted since is said out loud instead of silently dropped. SeedVR2 results have no settings to restore and show no button.",
    "to": "/gallery"
  },
  {
    "id": "2026-08-24-improve-output-size-in-note",
    "date": "2026-08-24",
    "title": "Pick the improve output size right under the ✨ button",
    "blurb": "The ✨ Upscale & improve note now carries the Output size (MP) box — the same 0.5–8 MP value Settings edits (klein.improve_megapixels), changeable without leaving your images. App-wide, like the instruction and the LoRA preset beside it.",
    "to": "/datasets?section=images"
  },
  {
    "id": "2026-08-24-improve-lora-preset",
    "date": "2026-08-24",
    "title": "Upscale & improve can now chain your LoRA presets",
    "blurb": "The ✨ pass ran with its instruction and nothing else — your generation LoRA presets (Settings ▸ Engines) never applied to it. The improve note now has a LoRA preset picker next to the instruction editor: pick one and every Klein improve chains it after the consistency LoRA — the single pass, the 🔄 re-run and the batch alike, in every dataset (it is app-wide, like the instruction, and the panel says so). SeedVR2 stays a pure restoration. A renamed or deleted preset quietly runs as None, never a blocked pass — and the result records which LoRAs actually ran in its details.",
    "to": "/datasets?section=images"
  },
  {
    "id": "2026-08-08-improve-instruction-editable-in-place",
    "date": "2026-08-08",
    "title": "Fix the improve instruction where it goes wrong, not in Settings",
    "blurb": "The note under ✨ Upscale & improve already told you what the pass was about to ask Klein for — \"add detailed texture, add sharp details…\" — and then sent you to Settings to change it. Now you can change it right there: ✎ Edit this instruction here opens the box under the button, in the lightbox and in the bulk toolbar, already filled with the exact text in force. Rewrite it for a drawing, or untick it and let the pass upscale with no instruction at all; both take effect on your next improve, with nothing to save. It edits the app-wide setting — the same value Settings shows, applying to every dataset — and the panel says so before you touch it. Reset to default appears only once you have actually overridden something, and puts you back on the shipped text rather than on a frozen copy of it, so later improvements to that text still reach you."
  },
  {
    "id": "2026-08-05-upscale-improve-finds-its-lora-on-a-docker-install",
    "date": "2026-08-05",
    "title": "✨ Upscale & improve stops re-downloading a LoRA you already have",
    "blurb": "On a Docker or Linux install, raising the enhancement-LoRA strength made every ✨ Upscale & improve answer “Klein needs klein_enhancement_lora — I’ve started downloading it”, then download the file it already had, then say it again. The file was never missing: the improve workflow was exported from a Windows ComfyUI and names that LoRA klein\\realistic.safetensors, and on Linux a backslash is part of a filename rather than a folder separator — so the app looked for one file with a strange name instead of realistic.safetensors inside klein/. Setup, which spelled it correctly, kept showing it installed, which is why the two screens disagreed and only that one file looked broken while every other model loaded. The name is now respelled for whichever system opens it, on the way in and on the way out to ComfyUI. Nothing to reinstall — the LoRA already on your disk is picked up after an Update & restart. Reported by @_nofaceman on Discord."
  },
  {
    "id": "2026-08-04-gallery-lightbox-upscale-improve",
    "date": "2026-08-04",
    "title": "Upscale & improve is now in the checkpoint gallery — the screen the result lands on",
    "blurb": "Yesterday ✨ Upscale & improve arrived on the ◉ LoRA Canvas lightbox. It was missing from the one place an improvement actually appears: a checkpoint’s gallery. Open any picture from a pill’s 🖼 gallery or from a run card and the button is there, next to ⬇ Download — the same pass, the same choice between Klein (re-renders detail and texture) and SeedVR2 (resolves detail, keeps the look), and the same quote of the instruction Klein is about to send. It is the same action on the same picture as on the board, wired once rather than twice, so the two screens can never start behaving differently. The original is never touched: the improvement arrives as its own image in that very gallery, beside the picture it came from, ready to compare, download or pin onto the board. One honest limit — the pass takes minutes and a gallery left open does not refresh by itself, so close it and open it again to find the new picture waiting at the top."
  },
  {
    "id": "2026-08-03-canvas-lightbox-upscale-improve",
    "date": "2026-08-03",
    "title": "Upscale a picture without leaving the canvas",
    "blurb": "Open a picture on the ◉ LoRA Canvas and it now carries ✨ Upscale & improve next to ⬇ Download — the same pass, and the same choice between Klein (re-renders detail and texture) and SeedVR2 (resolves detail and keeps the look) you already had in the dataset lightbox, with the same live quote of the instruction Klein is about to send. Until now the only way to improve a render you liked on the board was to go and find it somewhere else. The picture on the board is never touched: the result arrives as its own image in that checkpoint’s gallery, right next to the original, so you can compare the two and pin the better one. SeedVR2 offers to install itself if it is not there yet, an improvement cannot be improved again, and these upscales stay out of the Test Studio — they never count as a run in progress and never enter a checkpoint’s 👍/👎 ranking. Improve & upscale also works in Gallery without Canvas.",
    "to": "/gallery"
  },
  {
    "id": "2026-08-03-improve-note-cites-the-setting",
    "date": "2026-08-03",
    "title": "The amber “drawn dataset” note now names the setting it came from",
    "blurb": "Next to Improve, a caution used to announce “This dataset is drawn.” — a verdict the app never actually reached, because it only ever read the subject type you picked. On a photoreal dataset left marked Anime the sentence was simply wrong, with nothing to tell you where it came from. It now says the subject type is set to anime, so when the setting and your images disagree you can see which one to change. The advice itself is unchanged."
  },
  {
    "id": "2026-08-02-upscale-candidate-visible",
    "date": "2026-08-02",
    "title": "You can finally see that an upscale is waiting for you",
    "blurb": "An upscale never touches your original: it arrives as a separate tile you keep or reject. Which also meant that from the image you had just sent, nothing appeared to happen — so the pass got re-run on images that already had a result waiting, paying GPU time for a duplicate. The source tile now says it, both while the result is rendering and once it is ready to review. And the candidate names the engine that actually made it, instead of always crediting Klein."
  },
  {
    "id": "2026-07-30-keep-an-improvement-without-training-on-both",
    "date": "2026-07-30",
    "title": "✓ Keep an improved image without accidentally training on both",
    "blurb": "Keeping a completed ✨ Upscale & improve candidate now returns its original to Undecided automatically — from one tile or a bulk Keep, even when both were selected. Nothing is deleted: both files and the comparison remain, and you can keep the original again if you deliberately want both in training."
  },
  {
    "id": "2026-07-28-choose-the-klein-model-improve-runs-on",
    "date": "2026-07-28",
    "title": "Choose which Klein model ✨ Upscale & improve runs on",
    "blurb": "Improve never asked which model to use: it picked one for you, silently, and nothing on the screen said which. It now names the model it will run — even when there is only one — and lets you choose it when your ComfyUI has several. The choice is saved on the dataset (not in one browser), it is the same model Klein generation uses, and it applies to the single pass, the 🔄 re-run and the whole batch alike. Models are detected automatically wherever ComfyUI can load them, and if the one you chose is later moved away the run says so by name instead of quietly swapping in another."
  },
  {
    "id": "2026-07-28-improve-says-what-it-is-about-to-ask-klein",
    "date": "2026-07-28",
    "title": "Upscale & improve now shows the instruction it is about to send",
    "blurb": "The improve pass sends Klein a fixed instruction — and the built-in one asks for photographic texture and sharp detail, which is why anime and illustrated datasets came back looking realistic. That instruction is now quoted right next to the ✨ button, with one click to rewrite it or turn it off entirely, and a drawn dataset gets an explicit warning. Thanks Qeeyana (Reddit)."
  },
  {
    "id": "2026-07-27-rerun-upscale-and-improve",
    "date": "2026-07-27",
    "title": "Tuned the Upscale & improve settings? Re-run the pass on a tile in one click",
    "blurb": "An image made by ✨ Upscale & improve had no regenerate button, and that was on purpose: the normal 🔄 restarts from your dataset's reference photo, so on an improved image it would have quietly produced something unrelated instead of a better version of that shot. But the improve settings became editable (steps, megapixels, base and consistency strength, and the instruction itself), and until now the only way to see a new value take effect was to delete the result and click ✨ again on the original. Those tiles now carry their own 🔄✨ button: it re-runs the improve pass on the SAME source image, with your settings as they are right now, and replaces the result in place — old file to the Trash, your typed caption kept. Images you improved with earlier versions get it too. If the source image was deleted since, the button says so instead of improving the wrong thing."
  },
  {
    "id": "2026-07-23-bulk-improve-is-a-server-job",
    "date": "2026-07-23",
    "title": "✨ Improve 250 images at once — and Stop really stops",
    "blurb": "Selecting a big batch for \"Improve via Klein\" used to hit a wall: only the first 60 were accepted, the rest were refused one by one, and ⏹ Stop generation had no effect because the batch was a loop running in your browser tab — cancel the images in flight and the tab queued the next ones. The batch now runs on the server. It works through the whole selection a few at a time, waiting for a free slot instead of being refused, shows honest progress (how many queued out of how many), survives a page reload, and keeps going if you close the tab. And ⏹ Stop generation ends the batch itself, not just what happened to be generating at that instant."
  },
  {
    "id": "2026-07-22-improve-tuned-profile-and-loud-missing-lora",
    "date": "2026-07-22",
    "title": "✨ A better \"Upscale & improve\" out of the box — and it speaks up now",
    "blurb": "The pass now ships with a high consistency strength by default. That setting resists redrawing the shot, which is a drawback when you are restaging an image and exactly the point when you are only adding detail — so an improve keeps your composition instead of quietly reinventing it. And a LoRA strength you raised is never silently ignored any more: if its weights file is missing, the pass says so (which is what fetches it) rather than running unchanged and leaving you guessing. At strength 0 nothing changes — a LoRA you did not ask for is still skipped quietly."
  },
  {
    "id": "2026-07-22-enhancement-lora-installed-automatically",
    "date": "2026-07-22",
    "title": "⬇ The improve detail LoRA installs itself now",
    "blurb": "The \"Upscale & improve\" enhancement strength depends on a weights file the app never shipped or fetched — and when it is missing, that node is skipped entirely, so the slider moved nothing at all and said nothing about it. It is now downloaded with the other Klein assets by Setup ▸ Install everything, straight into the right ComfyUI folder. Fetched from its original public source (dx8152, Apache-2.0), never re-hosted."
  },
  {
    "id": "2026-07-22-improve-strength-settings",
    "date": "2026-07-22",
    "title": "🔧 \"Upscale & improve\" is now adjustable, not a fixed profile",
    "blurb": "Its instruction was editable, but everything deciding what the pass produces was hardcoded — the output size at 2 MP whatever your source was worth, and both LoRA strengths at 0, which meant the enhancement LoRA built into the workflow never applied at all. Settings ▸ Image engines now exposes the output size, the enhancement LoRA, the consistency LoRA (it anchors composition, not identity) and the step count. All four start at exactly the values the action used before, so leaving them alone changes nothing. One caveat worth knowing: the enhancement LoRA reads a file that ships with neither the app nor the Klein install, and when it is missing its node is skipped entirely — so that one slider does nothing until you have it."
  },
  {
    "id": "2026-09-07-image-upscale-product",
    "date": "2026-09-07",
    "title": "Improve & upscale is a complete optional plug-in",
    "blurb": "Install Klein improvement, SeedVR2 restoration, high-resolution tiling, instructions, finishing, settings and preparation together from the Store. LDS starts without this addition; its controls appear on the Bank, datasets, Gallery and Canvas when active.",
    "to": "/plugins/seedvr2/settings?focus=seedvr2-engine"
  }
]
