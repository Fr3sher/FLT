export const WHATS_NEW = [
  {
    "id": "2026-09-22-canvas-unpin-all",
    "date": "2026-09-22",
    "title": "Unpin every Canvas image in one click",
    "blurb": "Use Unpin all beside Pinned to clear image pins across all datasets, including images hidden by filters. Your gallery images and their remembered positions are kept, so you can pin them again later.",
    "to": "/canvas"
  },
  {
    "id": "2026-09-01-canvas-lanes-move-and-resize",
    "date": "2026-09-01",
    "title": "Move a dataset’s block on the Canvas, and give it the room it needs",
    "blurb": "Pin a run’s images and the contact sheet hangs below the tree — but the board never counted it, so it landed on top of the next dataset. Each lane now has its own two grips: drag its title strip to move the whole block, drag its bottom edge to set how much room it keeps, and the datasets below move with it. The edge turns amber when a lane draws past its own room — double-click it to fit. ✦ Tidy up still hands everything back to the automatic layout.",
    "to": "/canvas"
  },
  {
    "id": "2026-08-20-canvas-room-to-work",
    "date": "2026-08-20",
    "title": "The ◉ Canvas gets its screen back on a phone",
    "blurb": "The board is the whole point of the page, and on a phone it was getting half the screen: the filter bar wrapped onto two rows, the toolbar under it onto two more, and the page title repeated a word the nav bar was already highlighting. Measured on a 412-px phone, the board had 297 px to work in — 50 % of the page. It now has 451, which is 76 %, and on a folding phone opened out it goes from 57 % to 72 %. Nothing was taken away to get there. The toolbar is ranked instead: zoom, Fit and 🎨 Generate stay where your thumb is, and a new ⋯ button holds ✦ Tidy up, 💾 Layouts, 📷 PNG, 🔌 external LoRAs, ⏏ Undeploy, the colour key, the machine load and the full list of board gestures — as a sheet that floats over the board, so opening it never pushes the board down. ⋯ shows a badge when an external LoRA is on the board, so nothing it holds can go quietly. The chips in there carry their words again, and CPU/GPU/VRAM now reads from a phone too — which is the screen you check the machine from when you are not sitting at it. The desktop toolbar drops to a single row as well, because that ~500-character gesture line had been giving it a second one at every width, 1920 included.",
    "to": "/canvas"
  },
  {
    "id": "2026-08-18-canvas-one-grid-per-checkpoint",
    "date": "2026-08-18",
    "title": "Pinned batches land as one grid per LoRA",
    "blurb": "Generate a batch on the Canvas with several LoRAs selected and pin the results: each LoRA now gets its own grid on the board instead of everything fusing into one strip where the batches were indistinguishable. The epochs of one LoRA still share its grid — that side-by-side is the point — and prompts and separate launches keep their own grids too. Boards pinned before this keep drawing exactly what they drew.",
    "to": "/canvas"
  },
  {
    "id": "2026-08-17-canvas-bulk-undeploy",
    "date": "2026-08-17",
    "title": "Undeploy a pile of LoRAs in one go",
    "blurb": "Taking LoRAs back out of ComfyUI was a one-at-a-time errand buried in a checkpoint popover, and nothing anywhere told you how many were deployed. ⏏ Undeploy… at the top of the Canvas now opens the whole list — every LoRA the app has put into ComfyUI, across all your datasets and families, grouped by dataset. Tick what goes, press once, done; Select all is there for the clear-out. Only what the app deployed is listed, so a LoRA you downloaded into the same folder is never shown and never touched. Your training saves are kept — anything you undeploy can be deployed again from its checkpoint — and the removed copies go to the trash. The result is reported in three parts rather than a flat \"done\": removed, already gone, and refused (each one named).",
    "to": "/canvas"
  },
  {
    "id": "2026-08-10-canvas-gallery-open-folder",
    "date": "2026-08-10",
    "title": "Open your generated images straight from the Canvas",
    "blurb": "The gallery a checkpoint pill or a run card opens now has an 📂 Open folder button next to ZIP: it reveals the folder the generated images are saved in (the dataset’s own folder, on the machine running the app), so you can grab the files without archiving anything."
  },
  {
    "id": "2026-08-10-canvas-edges-tinted-per-dataset",
    "date": "2026-08-10",
    "title": "Tell whose line is whose on a multi-dataset Canvas",
    "blurb": "Every connector on the board used to be the same pale grey, so once two datasets had pictures parked near each other their lines crossed and became one tangle. Each dataset now draws its links in its own colour, shown as a dot next to its name in the lane header. The colour is fixed per dataset, so it is the same next time you open the board. The three colours that mean something keep meaning it: amber for a superseded branch, violet for \"blended from\", cyan for an external LoRA file."
  },
  {
    "id": "2026-08-09-canvas-pins-float-both-ways",
    "date": "2026-08-09",
    "title": "Park a pinned picture below its lane without shoving the next dataset",
    "blurb": "On the Canvas, dragging a pinned image above its dataset always let it float free — dragging it below pushed every dataset underneath further down the board. Pinned pictures now sit on a free layer in both directions: they overlap the lane below if you park them there, and nothing else moves. Fit still frames them, Export PNG still includes them, and ✦ Tidy up still brings them back beside the run that made them."
  },
  {
    "id": "2026-08-09-canvas-phone-board-room",
    "date": "2026-08-09",
    "title": "The canvas gives the board back its screen on a phone",
    "blurb": "On a phone the filter row was three wrapped lines floating on the board and the search box you rarely type in took most of one — it is now two lines: the chips keep their icon and their count, and 🔍 unfolds the search only when you ask for it (with the words still shown on the chip while a search is narrowing the board). The page blurb stays out of the way up to a laptop width, and a run in flight is announced once instead of twice when the Generate sheet is open. The board’s floating rows are also properly opaque now, so a strip of pinned images parked in a corner can no longer be read through Reset."
  },
  {
    "id": "2026-08-09-canvas-external-lora-links",
    "date": "2026-08-09",
    "title": "See which images an external LoRA actually touched",
    "blurb": "A permanent cyan line now joins each 🔌 plugin node to every board image generated with it, and an image’s facts panel lists its External LoRAs on their own row instead of filing them under always-on."
  },
  {
    "id": "2026-08-09-canvas-phone-toolbar",
    "date": "2026-08-09",
    "title": "The LoRA Canvas gives the board back to your phone",
    "blurb": "On a phone the board’s bottom controls took a quarter of the screen, and tapping ☝ Gestures buried the board under its own instructions with no way to put them away. The row is icons-only below a tablet — two rows instead of five, every button still thumb-sized — and the gesture help is now a sheet that floats over the board and closes with its ×. Nothing changes on a desktop."
  },
  {
    "id": "2026-08-09-canvas-external-loras",
    "date": "2026-08-09",
    "title": "Pin any LoRA onto the Canvas, even one you never trained here",
    "blurb": "Pin any LoRA from your ComfyUI folder onto the LoRA Canvas as a 🔌 plugin node and stack it on your generations, with its own strength. It stacks on a run anchored by a checkpoint trained here — there is no solo generation from an external LoRA alone."
  },
  {
    "id": "2026-08-08-the-canvas-controls-live-on-the-board",
    "date": "2026-08-08",
    "title": "The Canvas gives the screen back to the board",
    "blurb": "Everything that steers the LoRA Canvas — the zoom row, Fit, Tidy up, Generate, the colour key, the gestures sheet, the dataset filter and the banner announcing finished images — used to be stacked above the board. On a phone that chrome cost most of the screen before a single card was drawn, which is why the board opened tiny and pinned under a wall of buttons. Those controls now float ON the board: what it is showing sits along the top, what you do to it sits along the bottom within thumb reach, and the board itself takes back the space they were using. Nothing was removed and nothing moved to another page — the same controls, on the surface they act on."
  },
  {
    "id": "2026-08-08-canvas-filter-bar",
    "date": "2026-08-08",
    "title": "The canvas filters stopped eating half the screen",
    "blurb": "The Datasets panel was a fold-out card: unfolded on a library of fourteen datasets it stood 389 px tall on a 720-px screen — 54 % of the window, directly above the board, for anyone who had ever left it open. It is now a single row of chips about 40 px tall. Datasets, Models and Status each open a small menu with the same checkboxes (the dataset menu gained a search of its own, which the three-column list never had), Pinned images and Reset stay in the row, and the run search keeps its full-size box. Every chip shows its count and lights up while it is filtering, so nothing can narrow your board without saying so — and the menus now open above the board instead of under a pinned image."
  },
  {
    "id": "2026-08-08-canvas-zoom-labels",
    "date": "2026-08-08",
    "title": "Run cards stay readable when you zoom the board out",
    "blurb": "A board holding a dozen datasets is read at 30-40 % zoom, and at that scale a run card's title renders at about four pixels: the canvas was showing you everything and telling you nothing, so finding a run meant zooming in on each one in turn. Below 55 % every card now carries its run number at a constant, readable size, and below 30 % it carries the dataset name too — because the lane headings have gone unreadable by then as well."
  },
  {
    "id": "2026-08-08-canvas-layout-presets",
    "date": "2026-08-08",
    "title": "Keep a board arrangement instead of losing it to ✦ Tidy up",
    "blurb": "Laying two datasets' renders out side by side to judge a likeness takes twenty minutes, and until now the board only ever held ONE arrangement: the moment you needed it for something else, your only options were to leave it there forever or throw it away. 💾 Layouts in the board toolbar saves where every run card and every pinned picture sits — closed pictures included — under a name, and puts it back whenever you want. A run deleted since is simply not restored, and the app says how many, rather than leaving you to hunt for the card that is missing."
  },
  {
    "id": "2026-08-08-canvas-export-png",
    "date": "2026-08-08",
    "title": "Save the whole board as a PNG",
    "blurb": "📷 PNG in the board toolbar writes the entire canvas to one image file: every pinned picture at full size, every run card with its checkpoints, and the lines that join them. Useful for a comparison you want to keep, post, or look at next to something else. It is a redraw of the board, not a screenshot, so the buttons and badges are not in it — and a picture whose file has been cleaned off the disk comes out as a labelled placeholder instead of silently missing."
  },
  {
    "id": "2026-08-08-canvas-delete-image",
    "date": "2026-08-08",
    "title": "Bin a bad render from the board itself",
    "blurb": "The board is where you actually decide a render is a failure — and deleting it meant closing the node, opening the run, finding the checkpoint, opening its gallery, entering Select mode and finding the same picture again. Pinned images now carry a 🗑 next to their ✕. Press it once to arm it, again to delete: ✕ still only takes the picture off the board and remembers where it was, 🗑 deletes the image itself, through the same route (and the same recoverable-or-not setting) the gallery uses."
  },
  {
    "id": "2026-08-04-canvas-says-which-run-trained-a-full-model",
    "date": "2026-08-04",
    "title": "On the board, a run that trained the whole model now says so",
    "blurb": "A full-model run and a LoRA run of the same family printed exactly the same two words on their card — “Krea 2 · Raw” — while being completely different things: one produces a large checkpoint you load instead of the base, the other a small adapter you load on top of it. On a board holding both, nothing told you which was which. Those cards now carry a “full model” badge, in the graph and in the list alike."
  },
  {
    "id": "2026-08-04-canvas-drop-keeps-your-view",
    "date": "2026-08-04",
    "title": "Arranging the canvas no longer throws your framing away",
    "blurb": "Park a render up beside another dataset’s lane, let go — and the whole board zoomed out from under you, because it had just become bigger. Every time you tidied, the canvas re-framed the thing you were tidying, and the further you placed something the harder it kicked. From now on, moving anything — a pinned picture or a run card — means you have taken the view over: the board keeps the zoom and the position you chose and never re-frames itself again. ✦ Fit is still one click away for when you do want the whole board back, which is the difference between an offer and an interruption. A board you have never arranged still opens fitted to your screen, exactly as before."
  },
  {
    "id": "2026-08-03-canvas-images-go-anywhere",
    "date": "2026-08-03",
    "title": "Pinned images go anywhere on the canvas, not just below and right of their run",
    "blurb": "A picture pinned onto the ◉ LoRA Canvas could be dragged down and right as far as you liked, but never up and never left: its own lane's corner was a wall, so you could not park a render above its run, in the free margin beside the board, or next to another dataset's lane to compare across datasets. That wall is gone — the mouse and the arrow keys both reach everywhere now, and ✦ Fit grows to include a picture wherever you put it, so it is always one click from being back on screen. Nothing about where an image came from changes: the line to the checkpoint that made it follows it, because that link is read off the image itself rather than off its position. Three things came with it. ✦ Tidy up is the way home — it brings every picture on the board back beside the run that made it, side-by-side strips included, moved in one piece and never taken apart — and it is no longer greyed out on a board where only pictures have been moved, which is exactly when you need it. The board no longer re-zooms under your finger while you drag something past its edge — nor when you let go of it (see the entry above). And a strip of grouped pictures now draws ONE line back to each checkpoint it came from instead of one per picture, so a long link stays readable."
  },
  {
    "id": "2026-08-03-canvas-group-drag-out-crash",
    "date": "2026-08-03",
    "title": "Pulling a picture out of a group on the canvas no longer blanks the board",
    "blurb": "Dragging one image off a strip of grouped images showed the error screen instead of the picture coming loose — the board went blank and the only way back was a reload. The hint that appears while you pull (\"Drag it off the group to take it out\") was reading a size that had moved to another file when the group's title bar was split out earlier today, so the very gesture it exists to explain was the one that crashed. It is back, at the same size as the bar's own label at every zoom. Nothing you had pinned was lost — the board reloads exactly as you left it."
  },
  {
    "id": "2026-08-03-canvas-usable-on-a-phone",
    "date": "2026-08-03",
    "title": "The LoRA Canvas is finally usable on a phone",
    "blurb": "The board had never had a small-screen pass, and it showed. Opening 🎨 Generate on a tablet-width window turned it into a fixed side drawer that took more than half the screen and left a sliver of the very board you were picking checkpoints from — so that panel, the run details, the compare view and the image gallery now stay full-width sheets right up to a real desktop, and each one closes with a thumb-sized ✕ instead of a 14-pixel glyph. The zoom, Fit and Tidy up buttons are 40 px on touch, where a miss used to land on the board and pan it. The ✓ box that adds a checkpoint to a run no longer shrinks with the zoom — at the level the board opens on it had become a five-pixel square, on the one control the whole generate flow goes through. And the list of what the board can be told to do, which was simply hidden below laptop width, is now one tap away with the touch gestures spelled out."
  },
  {
    "id": "2026-08-03-canvas-opens-again-hotfix",
    "date": "2026-08-03",
    "title": "The LoRA Canvas opens again — v2026.08.03 broke it for a few minutes",
    "blurb": "If you updated to v2026.08.03 in the short window it was live, the Canvas page crashed on load (“An unexpected error occurred”). The provenance-edges feature read a value before it existed. Fixed — nothing else in that release was affected, and no data was touched."
  },
  {
    "id": "2026-08-03-canvas-blend-provenance",
    "date": "2026-08-03",
    "title": "🧬 A blended picture now shows every checkpoint it came from",
    "blurb": "A picture pinned on the LoRA Canvas was linked back to one checkpoint — but a 🧬 Blend loads several, often from different datasets, so the board was showing one parent out of two or three. Violet lines now join a blended picture to every source it was made from, across lanes, next to the existing indigo training lineage. When a source is no longer on the board — its run deleted, its dataset unticked — no line is invented: the picture says “1 of 2 sources is not on the board” instead. Blends made before this update keep their images and simply have no lines to show."
  },
  {
    "id": "2026-08-03-canvas-group-bar-reachable",
    "date": "2026-08-03",
    "title": "Groups of pinned images can be moved and closed again",
    "blurb": "A side-by-side group on the LoRA Canvas could end up impossible to move AND impossible to close, with no way to tell why. Its title bar — which holds the ⠿ grip, Export grid and ✕ — is drawn just above the strip, and any picture pinned over that space silently took the clicks meant for it. The bars are now drawn above every picture, so they always answer; and ✦ Tidy up and 📌 Pin all know that space is taken, so they stop dropping a picture there. It showed up most on a zoomed-out board, where the bar is twice as tall."
  },
  {
    "id": "2026-08-03-canvas-image-controls-see-through",
    "date": "2026-08-03",
    "title": "Pinned pictures are no longer hidden by their own buttons",
    "blurb": "Hovering a picture pinned on the LoRA Canvas dropped an opaque black band across its top and a black block over its corner — the controls covered the very thing you were pointing at. 🔍, ✕ and ⬇ are now separate rounded pills over a blur, and the step label is a small tag instead of a full-width band, so the image shows through between them. The glyphs went white too: they were mid-grey, which reads on the app’s dark chrome but vanishes on a bright render."
  },
  {
    "id": "2026-08-03-canvas-filter-opens-folded",
    "date": "2026-08-03",
    "title": "The LoRA Canvas opens on the board, not on its filter",
    "blurb": "The Datasets filter opened expanded every time you loaded the canvas, and on a library of any size its checkbox list pushed the board itself below the fold — so the first thing you did on the page you came to look at was scroll past a filter. It now opens folded at every width, with the same summary on the button (“3 of 7 · 12 runs shown”), so nothing is hidden. If you unfold it, it stays unfolded next time."
  },
  {
    "id": "2026-08-03-canvas-blend",
    "date": "2026-08-03",
    "title": "🧬 Blend two LoRAs into one image, straight from the board",
    "blurb": "Ticking several checkpoints on the LoRA Canvas used to mean one pass each. A new ⚖ Compare / 🧬 Blend toggle lets you load them all into the SAME generation instead, each on its own weight slider, with every dataset's trigger word listed before you launch rather than injected behind your back. Identity + style and identity + concept are where it pays off — two identities blend into a hybrid person, which the panel now tells you up front. The mode is called Blend everywhere now: the Test Studio's 🧬 Combine toggle is the same thing and now says Blend too. Nothing you saved changes — only the word."
  },
  {
    "id": "2026-08-01-canvas-runs-stay-separate-and-in-epoch-order",
    "date": "2026-08-01",
    "title": "Pin two generation runs to the canvas and compare them side by side",
    "blurb": "Pinning a second run at the same checkpoint no longer folds its images into the first run’s strip — each generation keeps its own strip on the board, so two runs stay two runs. Every strip now reads left to right in training order (500, 1000, 1500…) instead of alphabetically, and an over-cap batch keeps the early epochs rather than an arbitrary slice."
  },
  {
    "id": "2026-08-01-canvas-shows-the-dataset-reference-face",
    "date": "2026-08-01",
    "title": "See who the renders are meant to be, right on the canvas",
    "blurb": "Each character dataset’s lane on the LoRA Canvas now opens with its reference image, next to the dataset name. Click it to open it full size against the pinned renders. Concept and style datasets are unaffected — they have no reference face."
  },
  {
    "id": "2026-07-28-download-canvas-images-one-or-the-whole-gallery",
    "date": "2026-07-28",
    "title": "Download your generated images — one, or a whole run as a ZIP",
    "blurb": "The board can now hand the pictures over: ⬇ on a pinned image and in the full-screen viewer saves that one, and ⬇ ZIP in a gallery saves the lot (turn on Select first to take only the ones you tick). Every file keeps its lineage in its NAME — dataset, run, step and seed — so a render is still identifiable a month later instead of becoming another out_00042_.png. Big galleries say up front how many the archive holds, and a file that has left the disk is named rather than quietly dropped."
  },
  {
    "id": "2026-07-28-canvas-fuse-pinned-images",
    "date": "2026-07-28",
    "title": "Drop one pinned image onto another and compare them edge to edge",
    "blurb": "Comparing two checkpoints on the canvas meant lining two pinned pictures up by hand and squinting at the gap between their frames. Now dropping one onto another fuses them into a single node: the pictures sit side by side with nothing drawn between them, and there is no limit — add a third, a tenth. Drag the title bar to move the whole strip, hover a picture for its own 🔍 and ✕, and drag one off the group to take it back out at the size it had before."
  },
  {
    "id": "2026-07-28-canvas-pin-all-generated-images",
    "date": "2026-07-28",
    "title": "One click puts every image a canvas run made onto the board",
    "blurb": "A finished generation said “5 images ready” and left you to open each checkpoint’s gallery and pin the pictures one by one. The green bar now carries 📌 Pin all — the whole lot lands on the board in one go, each image in its own column under the checkpoint that made it, and nothing is ever placed on top of anything else. It says how many it put down, names anything it left out, and ↩ Undo takes them straight back off."
  },
  {
    "id": "2026-07-28-canvas-node-buttons-reachable-on-a-phone",
    "date": "2026-07-28",
    "title": "The ✕ on a pinned image can be tapped again",
    "blurb": "Closing a picture pinned on the LoRA Canvas did not work on a phone. The buttons were drawn at the board’s zoom, so on a board read at 65 % the cross was about ten pixels wide with the 🔍 right beside it — a near miss opened the full-screen view instead of closing the node. The ✕, the 🔍 and the resize corner now keep a real finger-sized target at every zoom level."
  },
  {
    "id": "2026-07-28-pin-to-canvas-from-the-thumbnail",
    "date": "2026-07-28",
    "title": "Put a generated image on the board without opening it first",
    "blurb": "Pinning a render onto the lineage board was only offered once you had opened it full-screen, so most people never learned the board could hold images at all. Every thumbnail in a run or checkpoint gallery now carries a 📌 of its own — one tap and it lands on the board next to the checkpoint that made it. It stays out of the way while you are selecting images to delete, so nothing new can be tapped by mistake."
  },
  {
    "id": "2026-07-27-canvas-pinned-images",
    "date": "2026-07-27",
    "title": "Put generated images ON the canvas, next to the checkpoint that made them",
    "blurb": "Comparing two checkpoints meant opening their images one at a time in a modal — never side by side. Open any generated image and hit 📌 Pin to canvas: it becomes a node on the board, joined to its checkpoint by the same connector the board already uses for \"this continued from that\". Drag it, resize it from its corner, close it with ✕. Closing does not forget anything: pin the same image again and it comes back exactly where you left it, at exactly the size you left it — stored with your card positions, so it follows the dataset from one machine to the next. Arrow keys move a focused image and +/− resize it, so a mouse is not required."
  },
  {
    "id": "2026-07-27-canvas-deployed-at-a-glance",
    "date": "2026-07-27",
    "title": "See at a glance which checkpoints you can generate from",
    "blurb": "On the LoRA Canvas, whether a checkpoint is deployed to ComfyUI — that is, usable right now — only showed up as small print AFTER you had picked it. Every pill now carries it on its left edge: a solid sky bar means deployed, a dashed grey bar means the file is on your disk but not deployed yet (the 🎨 Generate button deploys it for you). The shape carries the message as much as the colour, a legend sits above the board, and hovering a pill spells it out in words."
  },
  {
    "id": "2026-07-27-canvas-run-card-opens-everything",
    "date": "2026-07-27",
    "title": "Click a run on the Canvas to see everything it made, step by step — with its notes and settings",
    "blurb": "On the LoRA Canvas, the only way to look at a run's images was one checkpoint at a time: click a pill, look, close, click the next pill. Clicking the run card itself did almost nothing — it opened a little menu with a single \"Details\" row. It now opens the gallery for the WHOLE run: every image it ever generated, grouped by the checkpoint that made it, most-trained first, so you can judge where the LoRA stopped improving without hopping between pills. The run's note and its checkpoint notes are right there under the images, and so are the settings it trained with. It is the same panel the pills open — same Select mode, same real delete to the recycle bin — so nothing you already knew changes. Big runs stay quick: the three most-trained steps open, the rest fold behind their counts, and if a run has more images than one panel should hold it says so instead of pretending to be complete. Two bonuses: dragging a card to rearrange the board still opens nothing, and old test images whose file name names the run but not the step now show up in a \"Step unknown\" group instead of being counted as untraceable."
  },
  {
    "id": "2026-07-27-canvas-checkpoint-actions",
    "date": "2026-07-27",
    "title": "Click a checkpoint on the LoRA Canvas and act on it — download, deploy, undeploy, delete",
    "blurb": "On the board a checkpoint could only be ticked. It now opens the same actions the graph inside a run card has always had: ⬇ Download, 📦 Deploy → loras/…, ⏏ Undeploy, and the 🗑 delete that names exactly which file it removes. It is literally the same popover, so the two screens can never drift apart. When an action is not possible the reason is written where the button would be — a save that left the disk, a cloud run this machine has no link to — instead of a button that does nothing."
  },
  {
    "id": "2026-07-27-canvas-details-on-demand",
    "date": "2026-07-27",
    "title": "The run details drawer waits to be asked",
    "blurb": "Touching a run on the canvas used to throw the configuration drawer open, so glancing at the board meant closing a panel. Clicking a run — or a checkpoint — now opens its actions, and the drawer is one of them: ⓘ Details, filed with deploy and the rest. Shift-click still compares two runs, and dragging a card still just moves it."
  },
  {
    "id": "2026-07-27-canvas-generation-visible",
    "date": "2026-07-27",
    "title": "A generation launched from the board can be found again — and it says where the images went",
    "blurb": "Launch from the canvas and the progress now lives on the board itself: \"1 generating · 0 queued\", with its Stop. Close the settings panel, change page, reload — it is still there when you come back, instead of showing you an empty form while ComfyUI was still working. When it finishes it names the checkpoints it filled, and each one opens its gallery in a click. The board also refreshes itself as the images land, so the count on the checkpoint appears without a reload."
  },
  {
    "id": "2026-07-26-canvas-generate-from-the-board",
    "date": "2026-07-26",
    "title": "Test your checkpoints straight from the LoRA Canvas",
    "blurb": "Tick the ✓ on any checkpoint on the board and the Test Studio opens right there — the same prompt, seed, format, steps and engine settings, because it is the same panel, not a copy. The new part: your picks can come from several datasets at once, so you can put three LoRAs side by side on one prompt and one seed without leaving the board. Picked a checkpoint that is not in ComfyUI yet? The button says so before it does anything: \"Deploy 2 checkpoints, then generate\". Picked two families by mistake? It tells you Krea and Z-Image have no engine in common instead of going quietly dead."
  },
  {
    "id": "2026-07-26-canvas-move-cards",
    "date": "2026-07-26",
    "title": "Arrange the Canvas the way you think about your runs",
    "blurb": "Run cards on the Canvas can now be dragged, and they stay where you put them — after a reload, and after the next training finishes. That second part is the real change: the automatic tree centres every run over its continuations, so a new branch used to re-flow the whole lane and quietly undo any layout you had in mind. Once you have moved something in a lane, a run that finishes later lands in free space beside your arrangement and nothing else moves. On a phone, hold a card for a moment to pick it up (a finger that slides straight away still scrolls the board). Changed your mind? ✦ Tidy up forgets every card you moved on the lanes on screen and rebuilds the automatic tree — positions are only ever a display preference, never provenance."
  },
  {
    "id": "2026-07-17-canvas-lora-chain",
    "date": "2026-07-17",
    "title": "Dropped images rebuild the full LoRA chain in ComfyUI",
    "blurb": "Drag a generated image onto the ComfyUI canvas and the reconstructed workflow now shows every LoRA of your preset, not just the last one. (Generation itself was always correct — all LoRAs were applied.)"
  }
]
