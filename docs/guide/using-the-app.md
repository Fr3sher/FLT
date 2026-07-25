# Using the app

The workspace is a **guided flow**: each stage stays folded until the one
before it is done, and the progress rail on the left tells you where you are
and what's blocking the next step. You never have to guess what comes next —
this chapter just explains what each stage does and where the useful buttons
hide.

The walkthrough below follows a **character** dataset end to end because it
exercises the most stages; **concept**, **style** and the **image bank** each
get their own section after it. The flow is the same for all of them — only the
captioning rules and a few guards change with the dataset kind.

---

## The character walkthrough (reference photo → trained LoRA)

1. **Create the dataset** — Datasets → New. Pick **Character**, name it, set a
   **trigger word** (the token your prompts will use), and choose the **target
   model** (Z-Image / SDXL / Krea 2 / FLUX.1 / FLUX.2 Klein — changes the caption
   style; you can change it later).
2. **Upload the reference photo.** The app head-crops it automatically; use the
   crop editor (or *Reset to auto*) if the framing is off. Up to 3 extra angles
   can be added for multi-view consistency.
3. **Generate variations** — pick an engine (Nano Banana, ChatGPT, or local
   Klein) and fire the **variation catalog**: 53 shots across expression,
   angle, lighting, framing, outfit and background, each wrapped in an identity
   guard so the face stays the same person.
4. **Import** your own photos too (drag & drop) — each is auto-cropped to the
   face on the way in.
5. **Auto-classify framing.** A local vision model tags every image
   **face / bust / body / back**; the badges feed the composition meter.
6. **Curate** — keep / reject / crop, guided by the live meter targeting
   **12 face · 6 bust · 6 body · 1 back**. Watch the face-similarity badges
   (green = strong match, orange = review) to drop off-identity shots before
   they poison training.
7. **Caption** — one click captions the kept set (prose or booru tags,
   matched to the target model). The **identity-leak check** flags any caption
   that describes hair/face/skin — fix every flagged one. A find/replace +
   tag-frequency panel sweeps the whole set at once; its **💾 Write .txt
   files** button drops a kohya-style `<image>.txt` next to each kept image
   in the dataset folder (same format as the export ZIP) for external tools.
8. **Fix individual shots** — every generated tile has a ✏️ button: edit the
   exact prompt that made it and regenerate in place, without losing the rest.
9. **Train** — the pre-flight check runs the full checklist (count, balance,
   captions, leaks, duplicates). It no longer *blocks*: leaking captions and
   near-duplicates are editable right inside the confirm, and missing captions
   just ask you to **Start anyway** (captions stay strongly recommended). Steps
   are computed automatically; ⚙️ Advanced options exposes every knob (each with
   its own why/how) and a **Presets** row — apply a shipped ★ recipe (*Krea
   character*, *Concept*, *Style*) or save/import/export your own as a JSON.
   No GPU? **☁️ Train in cloud** rents one per run. Watch this run — and every
   other, cloud or local — from the **🏋️ Runs** tab, where you can retry a
   failed run (↻), continue a finished cloud run for more steps (▶), and download
   the LoRA.
10. **Pick the best checkpoint** — open the **Test Studio** from the dataset:
    grid-test checkpoint × strength, vote, rank by face similarity, and star ★
    the winning settings. The last checkpoint is almost never the best one.
11. **Export** — at any point, **Export ZIP** gives you the curated, captioned
    set as a standard ai-toolkit dataset. Nothing is locked in.

## Concept datasets (an object or action, not a person)

Pick **Concept** at creation and describe the concept in the required field —
the captioner needs to know exactly *what to omit*. What changes vs character:

- **No reference photo.** Images come from **import** or the built-in
  **scraper** (paste a gallery URL or run a Reddit keyword search, tick the
  frames you want, they land straight in the dataset — deduplicated and
  quality-filtered). Already have a kohya-style dataset on disk (images +
  same-name `.txt` captions)? **⋯ More → 📂 Import from folder…** merges it in
  from a pasted folder path — captions attach, duplicates are skipped (a ZIP
  works too, via **📦 Import dataset**). On gallery sites (PornPics), a category/tag/search scan
  shows **the same previews the listing page does** — one per gallery, the shot
  that actually matches your keyword. Tick **Scan full albums** to pull every
  photo of each matched gallery instead, or paste a single `/galleries/…` URL
  to get that whole album. Sex.com works the same way for keyword searches
  (`sex.com/en/pics?search=…`) — every pin **is** a single matching image, so
  there is no album option to worry about. Civitai searches return **SFW
  results only** unless you add a Civitai API key in **Settings → Scraping &
  sources**.

  > **Reddit says "wait N seconds" (429)?** By default Reddit scans share a
  > public client id (and its ~1000 requests / 10 min quota) with many other
  > people, so it can be exhausted before your first scan. Add your own free
  > client ID in **Settings → Scraping & sources** — a one-minute, step-by-step
  > guide is built into that page.
- **Captions invert**: they describe everything *except* the concept, so the
  concept is what binds to the trigger. The leak check watches for stray
  descriptions of it.
- **Masked training is off** (a person mask would erase the very thing you're
  teaching), and imports keep the full frame instead of head-cropping.

## Style datasets (a global aesthetic)

Pick **Style** at creation. What changes:

- **No trigger word** — the style tints every image once the LoRA is loaded.
- **Captions describe content only** (never the rendering), and they're
  optional; caption dropout rises so the style generalizes.
- **Step count switches to a sublinear √n scale** built for the large sets
  (hundreds of images) style LoRAs want.

## Your own shot catalog (JSON import)

The workspace ships a built-in shot catalog per subject type (53 shots for a
human, ~59 for an animal, and so on). If you want shots nobody wrote for you —
40 breed-specific poses for a dog, a product line's signature angles — you don't
have to type them one at a time. Open **📥 Shot catalog (JSON)** under the shot
grid.

**Export first.** The exported file is the format, and the example an LLM needs:

```json
{
  "format": "lds-shots/1",
  "subject_type": "animal",
  "shots": [
    {
      "label": "Dog, zoomies on the lawn",
      "framing": "body",
      "prompt": "full body photo of the animal running fast across a lawn, side view, sunny day"
    }
  ],
  "examples": []
}
```

Then ask a chat assistant for more shots *in that exact shape*, and import the
file it gives you.

Each shot needs three things:

- **`label`** — a short name, max 80 characters, shown on the card. It must be
  unique: not a built-in label (of *any* subject type), and not one of your
  existing shots. The app refuses a collision and tells you which label is at
  fault — two shots sharing a label would make it resolve the wrong prompt the
  day you regenerate one.
- **`framing`** — exactly one of `face`, `bust`, `body`, `back`. Anything else is
  refused; it is never quietly remapped.
- **`prompt`** — the text sent to the image engine, max 500 characters.

`nsfw: true` is optional and only has an effect when Klein is the only engine
checked. Everything under **`examples`** is ignored on import — that's how the
export can show you samples without them coming back as duplicates. Any other
field (including `aspect`) is ignored too, and the import summary says so: an
imported shot uses its framing's default aspect ratio.

**Nothing is written until you confirm.** The app reads the file, lists what
would land and what it refuses (naming the entry and the reason), and waits. A
40-shot file whose 37th entry is broken never leaves 36 shots half-imported.

Imported shots appear in their own **📥 Imported** group after the built-ins, one
set per subject type. They never replace a built-in, you can delete them one by
one or all at once, and they're stored with the app — not in the browser — so
they survive a cache wipe, show up on your phone and ride along in the backup.

### Keeping a shot you wrote by hand

The **✨ Custom shot** box below the grid is the quick way to add one shot: type a
prompt, pick a framing, Add. Those cards are stored **in your browser**, so
clearing its data takes them with it.

Any card you want to keep, press **Keep** on it. It moves into the 📥 Imported
group and is saved with the app, exactly like an imported shot — surviving a
cache wipe, following you to another device, included in the backup. The card
keeps its identity, so a shot preset that had it selected still works. If its
label happens to clash with a built-in shot or with one you already imported, the
app says which label and refuses rather than creating a duplicate; rename the
card (remove it and add it again) and press **Keep** once more.

*Feature requested by ashish.sinha (Discord).*

## Back up everything

The **💾 Back up everything** button on the Datasets library packs your whole
setup into a single file so you can move to a new machine — or recover from one
— without losing anything.

- **What's inside**: every dataset (all images, captions, statuses, face and
  watermark states, references), its **training history** (which runs produced
  which version, the settings each used), plus your **settings** — engine
  choices, training defaults, cloud tuning, watermark preferences. It's a
  *logical* backup, one entry per dataset, not a raw disk dump.
- **Include trained LoRAs** (checkbox next to the button): also bundle the
  trained `.safetensors` files themselves. These are large — hundreds of MB per
  checkpoint — so it's **off by default**; the light training history above is
  always included, so a dataset comes back under **Trained** either way. Tick it
  when you want the finished LoRAs to travel too.
- **What's never inside**: your **API keys, Hugging Face token and scraping
  credentials**. They are deliberately left out so the file is safe to copy
  around; re-enter them once on the new install.
- **How it runs**: in the background. A library can be gigabytes, so you get a
  live "X / N datasets" progress bar and can keep working. When it's done, use
  **⬇ Download** to save the archive, or **📂 Open folder** to find it on disk.
- **Restoring**: hand the master archive to the same **📦 Import backup** button.
  It restores your settings (without overwriting keys you've already entered),
  rebuilds each dataset **and its training history** — so it lands back under
  **Trained** instead of "Not trained yet", with its runs in the Runs hub.
  Bundled LoRA files are re-deployed to ComfyUI when it's configured on the new
  machine; if it isn't, they're reported as skipped and the **Trained** status
  still stands (the run is what marks it trained, not the file on disk). Nothing
  is ever overwritten — a dataset whose name already exists comes back with a
  `(restored)` suffix — and you get an honest final report of what was restored,
  renamed or skipped.

## The image bank (triage a big folder)

You exported 9 000 unsorted images from Telegram (or a scraper dumped a
mountain of files) and a dataset only needs the best 30–150 of them. The
**🗃️ Bank** tab is the triage funnel that gets you there — without ever
touching the folder itself:

1. **Create a bank** — give it a name and paste the folder path. The app
   inventories every image in place (subfolders included). Nothing is copied,
   nothing is modified; rejecting an image is a reversible status, never a file
   deletion. The folder stays LIVE: keep dropping images into it and they are
   picked up automatically the next time you open the bank list or the bank
   itself ("42 new image(s) found in the folder"), as undecided images ready
   for the next scan — your existing keep/reject decisions, scores and captions
   are never touched. Files you removed from the folder are reported at the top
   of the bank, never deleted from it, so an unplugged drive can't wipe your
   triage.
2. **🔎 Scan quality** — a background pass (CPU only, a few minutes even on
   thousands of images) scores every file: sharpness, noise, flat/empty
   frames, resolution — and groups **near-duplicates**. The flags follow the
   thresholds in *Settings → Captioning & quality*; because the raw scores are
   stored, tuning a threshold re-sorts the bank instantly, no rescan.
3. **Cull** — use the filter chips (🌫 Blurry, 📺 Noisy, ⬜ Flat, 📐 Small,
   ≈ Duplicates) to review the worst offenders first. **🧹 Auto-reject
   flagged…** clears whole categories in one click (your manual ✓/✕ are never
   flipped). In the Duplicates view, resolve every group at once with **keep
   best** (highest resolution, then sharpest) or **keep first**, or pick the
   keeper by eye.
4. **👥 Group by person** — the face pass (needs the Quality tools from Setup)
   detects the dominant face of every remaining image and clusters the bank by
   person, *no reference photo needed*. Click a person card to see only them,
   select all, keep or reject. Embeddings are cached, so re-running after a
   cull is much faster.
5. **🏷️ Caption & 🔍 search** — caption the bank with the same engines your
   datasets use (JoyCaption / Ollama vision, your *Settings*). Hit **🏷️ Caption
   all** to describe every not-yet-captioned image, or select some first to
   caption just those. It runs in the background, frees the GPU like the other
   passes, and is Stop-able mid-run. The captions are plain descriptions (no
   trigger word, nothing omitted) whose real job is **search**: type into the
   🔍 box — `red dress`, `sunset`, a file name — and the grid filters to
   matching images, combinable with every other filter. It's the fast way to
   find shots in a 9 000-image dump.
6. **⬆ Promote** — the kept images are **copied** into the dataset you choose
   through the normal import path: normalized to webp, near-duplicates already
   in the dataset skipped. Any bank caption **rides along**, so a captioned
   selection starts already captioned in the dataset. From there they get
   everything datasets have — captions, watermark cleaning, face scoring against
   a reference, training.

Work the funnel in that order: quality first (cheap, catches the trash), then
subject, then selection. A promoted image keeps its ⬆ badge in the bank so you
always know what's been used where.

**🎨 Curate down to the right subset.** Culling removes the bad shots; curation
picks the *good* subset — and it's most of what makes a LoRA good. Once **✨
Score** has run (it caches a CLIP embedding per image), the **Curate** row under
the selection bar offers two selectors that cost no extra GPU time:

- **🎨 Pick diverse** — enter a number and it selects the images that best
  *cover the variety* of what you're looking at (varied angles, outfits, scenes),
  instead of that many near-identical frames. It's the antidote to a dump of
  4 000 shots of the same pose: ask for 60 and you get 60 that actually differ.
- **🎯 Similar to selected** — select **one** image as a reference, and it ranks
  everything by how much it looks like that image and selects the closest N — the
  fast way to pull one person or one look out of a mixed export.

Both honour whatever filter and 🔍 search are active ("the 60 most diverse of
*this* subfolder"), and both just **select** — the images light up and you review
them with the same ✓ Keep / ✕ Reject / ⬆ Promote bar. Nothing is auto-kept or
deleted, so a selection you don't like costs one click to clear.

**📐 Classify framing** tags every non-rejected image by *shot type* — face
close-up, bust, full body or back view — using the same detector the datasets
use. The result becomes a row of **📐 Framing** filter chips (compose with every
other filter and search), so balancing a character set's angles is a couple of
clicks. It's a GPU vision pass; add it to **🚀 Launch all** to have it run
overnight with the rest.

**📊 Coverage advice** (idea by [@antonp](https://github.com/perfectgf/lora-dataset-studio))
is a read-only panel next to the Curate row. From what you've **kept** (or every
non-rejected image before you've kept anything), it says in plain sentences what
leans and what's thin for a good LoRA — *"70% face shots, add body/back"*,
*"person #1 is 60% of the set — one subject or a mix?"*, *"only 8 kept, most
families want 20+"*. It's **advice only** — nothing is kept or rejected — and
pure maths on data the passes already computed, so it costs no GPU. The
framing-balance line needs the 📐 Framing pass to have run; without it the panel
still covers person mix, style spread and resolution and hints to run framing.
**🗑 Delete rejected from disk** (next to Promote) is the one exception to the
"your source folder is never modified" rule, and it's opt-in. Once you're happy
with your triage, it removes every image you marked ✕ rejected from its source
folder — the actual files, not just the status. It asks you to type **DELETE**
first, and tells you where the files will go before you confirm: your OS trash
when [`send2trash`](https://pypi.org/project/Send2Trash/) is installed, the
app's own Trash otherwise (recoverable until you empty it from Settings), and a
permanent delete only when neither can take the file. Kept and undecided images
are never touched, and a file it can't remove (locked, read-only) is reported
and left alone rather than aborting the batch.

⚠️ A bank doesn't own its folder, so two banks can point at nested folders and
list the **same files**. That's harmless while you triage — decisions live on
the bank — but deleting from disk in one bank removes those files from the other
too, along with every decision you made on them there. The app says so when you
create such a bank, and the confirmation names the other bank and how many of
its files are about to disappear.

**🚀 Launch all** does the whole funnel for you in one go. Tick which passes
run and how auto-reject behaves, hit Go, and walk away — it chains *scan →
auto-reject → score → find watermarks → group by person → classify framing →
(optional) caption* in that exact order. Two things make it safe to run overnight: a pass whose
tool isn't installed, or a moment when the GPU is busy with a training run, is
**skipped with a reason** instead of failing the whole run; and because
auto-reject runs *before* the heavy passes, scoring/watermarks/person only ever
process the survivors, never the images you just rejected. Captioning is the one
pass left **off by default** (it's the slowest GPU pass and a clean-up run
rarely needs a description on every shot). Stop it any time — and when you come
back, a saved report at the top of the bank tells you exactly what ran, what was
skipped and why, with the headline counts.

## Review a bank one image at a time

Filter chips and bulk actions clear the obvious trash, but the last call —
*is this shot good enough for the LoRA?* — is made one image at a time, and
squinting at a 140-pixel thumbnail is not how you make it. **▶ Review one by
one** (above the grid) opens the images of the **current filter** full size, one
after the other:

- **✓ Keep**, **✕ Reject**, **⏭ Skip** — each one saves and jumps straight to the
  next image. The keyboard is the point: **K** keep, **R** reject, **S** skip,
  **←/→** move without deciding, **Esc** to leave. A few hundred images go by in
  minutes.
- **⏭ Skip** decides nothing (the image stays undecided) but is not shown again
  in that run — it's "not now", not "no".
- **🎲 Random order** walks what's left in shuffled order instead of folder
  order. On a scraped dump of 3 000 photos, sequential order means 200
  near-identical frames in a row; random gives you a representative sample from
  the first click. Ticking or unticking it mid-run only re-orders what you have
  **not** seen yet — nothing you already judged comes back.
- Under the image, the facts the passes already computed (resolution, sharpness,
  aesthetic score, NSFW, quality flags, person and duplicate groups) so you can
  call it without leaving the lightbox.
- The counter is honest — *12 / 340* over the snapshot taken when you opened the
  review, so a decision that drops the image out of the filter can't make the
  run skip images or loop. Each decision is saved on the spot: close after fifty
  of them and all fifty are there.

The ▶ button on a tile starts the same review **at that image**. A plain click
on a tile still selects it for the bulk ✓/✕/⬆ bar, so both ways of working stay.

## Clean the watermarks a bank found

**🚩 Find watermarks** flags the images carrying an overlaid logo, URL or
@username. Removing them used to mean promoting the watermark into a dataset
first and cleaning it there; the bank now does it itself, in **two steps you
launch by hand** — cheapest and safest first:

1. **✂ Auto-crop** cuts off the marks sitting in a border strip. No model, no
   GPU, no invented pixel: it simply trims the band up to the mark, and only
   when the image stays big enough to train on. Anything it can't crop that way
   is left flagged, on purpose.
2. **🧽 Inpaint** repaints what's left. **LaMa** (fast, non-generative) handles
   small off-centre marks and leaves marks *on the subject* flagged; **Klein**
   (slower, via ComfyUI) also clears those. Each engine says what to install
   when it isn't ready, and the button stays off rather than failing mid-pass.

Each step shows how many images it still has to work on and how many it has
already handled, so you can see where the funnel stands. **Your source files are
never modified** — a cleaned image is a copy the app keeps beside the bank's
thumbnails. That copy is what the grid shows, and what **⬆ Promote** sends to
the dataset, so a cleaned bank produces a clean dataset. **↩ Undo cleaning**
just deletes those copies and flags the images again, and **👁 Before / after**
flips a sample between the cleaned version and your untouched original.

If a bank was scanned by an older version, its flagged images carry no recorded
mark position; the panel says so and one more **🚩 Find watermarks** run makes
them cleanable.


## Move a bank folder to another disk

A bank points at a folder *in place*, but nothing it computes lives in that
folder: the quality scores, duplicate groups, face clusters, captions and every
keep/reject decision are stored against the image row, and each row remembers
its file *relative* to the bank's folder. So moving a 30 000-image bank to
another drive costs nothing — you just have to tell the app where it went.

You can do this in either order. **📦 Move folder…** sits in the bank's header
next to its path (and **📦** on the bank's card in the list), so you can open it
before touching anything to see what the app will ask for; it also appears inside
the warning shown once the app notices the folder is gone, if you moved first.
Paste or browse to the new folder
and press **🔍 Check this folder**. Nothing is written yet: the app walks the
candidate folder and tells you how many of *this bank's* images are in there and
how many are not.

- **All of them found** → confirm, and the bank is repointed with every score
  and decision intact.
- **Some found, some missing** → you can still confirm. Nothing is deleted:
  rows whose file didn't come along keep their analysis and simply read as
  missing until the file comes back.
- **None found** → refused. That folder is a *different* folder, not a moved
  one — the usual cause is picking the parent of the folder you moved.

The app never deletes a row on its own, and an analysis pass run while the files
are away no longer degrades them either: a file that is *absent* is not a file
that is *broken*, so the pass stops and tells you the folder appears to have
moved instead of marking thousands of images unusable.


## Make Score use a GPU Python you already have

The **✨ Score** pass (aesthetic · NSFW · style) runs in its own small Python
environment, and that environment deliberately carries **CPU-only PyTorch**: a
first install stays a few hundred megabytes instead of pulling ~2.5 GB of CUDA
wheels onto machines that may have no card at all.

On a machine that *does* have one, that default is expensive — CLIP measures
about **336 ms per image on the CPU against ~15 ms on a recent card**, so a
30 000-image bank is the difference between a coffee break and most of an
afternoon. The bank says so: when Score is about to run on the CPU on a machine
with an NVIDIA card, an amber note gives you the estimate and a button, **⚡ Use
a GPU Python I already have**.

That button is the point. If you train LoRAs or run ComfyUI, this machine
*already* has a PyTorch with working CUDA. Score can simply borrow it — no
download, no third environment to maintain.

The dialog lists the interpreters the app knows about (the environment it built
for scoring, ai-toolkit's, ComfyUI's, its own) and reports each one **package by
package**:

- **GPU ready** — everything the pass imports is there *and* PyTorch sees the
  card. Pick it and the next Score run is minutes instead of hours.
- **Missing packages** — the reason is named. The common one is an interpreter
  with a perfect CUDA PyTorch but no **OpenCLIP**: Score needs `open_clip` and
  `transformers`/`timm` too, so CUDA alone is not enough. Such an interpreter is
  **refused**, on purpose — accepting it would trade slow-but-working scoring for
  an import error an hour into the pass.
- **CPU only** — it can run the pass, it just has no usable CUDA.
- **No answer** — the path is not a working interpreter (moved venv, unplugged
  drive). Nothing changes.

**The app never installs anything into an environment it did not create.** Your
ai-toolkit venv runs your training and ComfyUI's runs your generation; a silent
`pip install` into either is not something a dataset tool gets to do. When a
package is missing the dialog shows you the exact command and leaves the choice
to you — run it in a terminal, then hit **↻ Check again** and the row updates.

Not listed? Paste any python executable's path and press **Check it** — a conda
env, a uv venv, anything. And **Back to the app default** puts it back exactly as
it was; the choice is reversible at any time, and the note under the passes
always says which interpreter is in use.

## Tips that save runs

- Trust the composition meter over your instinct — a set that "looks varied"
  is usually still face-heavy.
- Fix every leak the badge reports before training; one "a woman with long
  blonde hair" caption quietly competes with your trigger.
- Don't chase steps. Train the auto count, then let the Test Studio find the
  *earliest* checkpoint that nails the identity — it keeps the most prompt
  flexibility.
- The next chapter — **Building a good dataset** — explains *why* behind every
  rule above. Read it once before your first serious run.
