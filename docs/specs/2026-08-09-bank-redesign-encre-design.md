# Bank redesign — layout B (the “Encre” skin was tried and dropped)

**Status:** structure built and kept; skin reverted. This file is what a session
two weeks from now reads instead of guessing — including about the part that was
undone, which is the half nobody writes down.

> ## ⛔ The skin decision was REVERSED after seeing it running
>
> Encre was chosen from static mockups and looked right there. In the actual app,
> beside the rest of the product, it read as foreign: **“la couleur ne me plaît
> pas, on va rester sur ce qui se fait ici.”** The Bank keeps the app's own
> palette.
>
> **What survives:** structure B, the split of `BankWorkspace.jsx`, the frozen
> surface inventory — everything below section 2. **What was removed:** the
> `.bank-encre*` token override in `index.css` and its three class usages.
>
> The removal was cheap for one reason worth repeating: the skin was a **scoped
> token override on a single wrapper**, not a rewrite. It re-coloured ~1 900
> existing utility usages without editing any of them, so undoing it was deleting
> one CSS block and three class names — and the whole structure stayed put. **A
> skin that had touched every button would have been a skin nobody could undo.**
>
> Section 1 is kept as the record of what was trialled, not as an instruction.

**Why this file exists.** The skin was chosen in a brainstorm whose three mockups
lived in a session scratchpad — a temp folder. The technical half of the work
(the surface freeze) was documented with care in its commit; the half that says
*what it should look like* existed only in a conversation, and took ten minutes
of archaeology to recover. A brand decision for a whole screen must not depend on
`%TEMP%` surviving.

---

## 1. The skin — “Encre” (TRIALLED, THEN DROPPED — do not implement)

Chosen over **Slate** (neutral, dense, indigo accent) and **Verre** (translucent,
drop shadows, teal). Encre keeps the product's violet gradient and pushes it:
blue-black grounds, heavier type, a coloured halo instead of a drop shadow.

These are the tokens as trialled. **Do not re-derive them** — they were compared
side by side against the two alternatives, and the comparison is what made the
decision meaningful.

```css
--r:12px;  --gap:11px;
--bg:#08080d;      --panel:#101019;   --panel2:#171724;
--line:rgba(160,150,255,.13);         --line2:rgba(160,150,255,.26);
--tx:#f2f0ff;      --tx2:#a7a3c4;     --tx3:#726e91;
--acc:#8b5cf6;     --acc-tx:#d6c8ff;  --acc-bg:rgba(139,92,246,.16);
--shadow:0 0 0 1px rgba(139,92,246,.10), 0 14px 34px -18px rgba(139,92,246,.55);
--font:800;        --track:.01em;
```

Two details that carry the identity and are easy to drop by accident:

- the panel header is `linear-gradient(180deg, rgba(139,92,246,.10), transparent)`
  over `--panel` — the brand gradient, not a flat fill;
- the elevation is a **halo**, not a drop shadow. `--shadow` is a violet ring plus
  a wide soft glow. Replacing it with a neutral `box-shadow` turns Encre into
  Slate.

Semantic colours stay separate from the accent: `--ok:#34d399`, `--warn:#fbbf24`,
`--bad:#fb7185`. A destructive action is red because it is destructive, never
because it needs emphasis.

## 2. The structure — B, “filter rail + full-height grid”

Today the workspace is four zones stacked vertically, so adjusting a filter means
scrolling up, clicking, and scrolling back down to see what changed. On a bank of
20 000+ images that round trip is the cost, not the click count.

B puts the filter beside the thing it filters:

- **top bar** — bank identity, counters, and the decisive actions
  (`⚙ Passes`, `🚀 Launch all`, `→ Promote`);
- **left rail** — all of triage: search, Status, Quality, Person, then Score /
  Framing / Medium / Angle / Resolution / Origin folded below. It sits beside the
  grid only from **`lg` (1024 px)**, not `sm`: a 17 rem rail *fits* from 640 px
  but leaves the grid ~350 px — two thumbnails — and a triage screen showing two
  images is not one. Below that it is a drawer;
- **centre** — the grid, full height, with the selection bar above it
  (count, Select all, ✓ Keep, ✕ Reject, Sort, ▶ Review).

**① Analyze becomes a panel opened on demand.** All eight passes stay, with their
existing dialogs untouched — the panel is a container, not a rewrite of what the
buttons do.

Rejected, and why it is worth recording:

- **A** (stack, modernised in place) — zero relearning, but the scroll round trip
  survives, which is the actual complaint.
- **C** (full-screen grid + ⌘K) — the most striking, and the only one that makes
  you *learn a gesture* to reach what used to be visible. Defensible for two-hour
  sessions, expensive for a tool reopened every couple of weeks.

## 3. The guarantee already in place

`bankSurfaceInventory.contract.test.js` freezes **188 distinct interactive
surfaces (227 occurrences)** — button labels, `aria-label`s and `title`s — and
asserts each still occurs at least as often **anywhere in the Bank tree**. Moving
a button between files is therefore free; deleting one is loud.

⚠️ It was proven able to fail, twice, before being trusted:

1. the first extractor matched only buttons whose body was plain text, skipping
   every button with a conditional suffix, and ended the opening tag at the first
   `>` — which sits inside `onClick={() => …}`, so the inventory filled with
   `className` fragments;
2. the second stayed **green** when `BankPage`'s Open button was deleted, because
   the video lane has an `Open →` of its own. **A set cannot tell “one is left”
   from “there were two.”** Hence occurrence counts, not membership.

The scan discovers files rather than listing them, so a file the redesign creates
is covered without anyone remembering to add it.

## 4. Non-negotiables for the build

- **No surface lost.** The contract above is the gate, not a reviewer's memory.
- **400 px.** The rail must fold, not overflow. Every capture at 1440 **and** 400.
- **The dialogs are out of scope.** `PassDialog`, `LaunchAllDialog`,
  `PromoteDialog`, `BankReviewLightbox` and friends keep their behaviour; only
  where they are reached from changes.
- **`BankWorkspace.jsx` is 3 471 lines and holds 52 buttons** — more than the
  eleven other Bank components combined. Splitting it is part of the work, and it
  is what makes the contract test earn its keep.
- Help registry entry for any new panel or big button; What's-new entry; both
  contract tests stay green.

## 5. What is deliberately still open

- Whether the rail is collapsible, and whether that state persists. ⚠️ If it
  persists, it is a **screen preference** and belongs with view state — not with
  the settings that describe what a dataset produces.
- The video bank (`components/videobank`) shares surfaces with the image bank and
  is inside the frozen inventory, but its layout is **not** part of this decision.
