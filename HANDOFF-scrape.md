# HANDOFF — Instagram scrape deps not installed & browser-cookie auth path dead

**Filed by:** Codex agent, 2026-08-10
**For:** the next AI (or human) picking up this thread
**Status:** investigation complete — user needs a one-click install + `instaloader --login`

---

## 1. The problem the user hit

User wants to scrape one or two Instagram profiles (then train a character LoRA and
🧬 Blend them to make a *hybrid* of two people — see §6). When the app ran the
Instagram scan it returned:

```
❌ Instagram blocked access (login required / rate-limit).
```

User: *"I have an authenticated session in the same browser, does that not count?"*

**Short answer given to user:** their browser login counts *in principle*, but the
app cannot use it because `browser_cookie3` is missing from the environment — so the
browser-cookie auth path (`_auto_import_browser_cookies`) is dead. The reliable fix
is `Setup → Install everything` + `instaloader --login`.

---

## 2. Root cause — why the scrape deps are not installed

1. **`backend/requirements-scrape.txt` is an optional extra.** It is NOT part of the
   core install. `backend/requirements.txt` (what `start.bat` / manual
   `pip install -r requirements.txt` runs) contains **zero** scrape deps.
   README Option 2 installs `requirements.txt` + `requirements-ml.txt`, never
   `requirements-scrape.txt`.
2. **Scrape extras install on demand only** — via `Setup → Install everything` or
   the per-tile Reinstall button. `_action_needed('scrape_extras')` returns
   `not caps.get('scrape_deps')` (`backend/app/setup_installer.py:868-873`), so it
   only installs when `scrape_deps` is missing. If the user never clicked it, the
   packages stay absent. This machine never ran the scrape install.
3. **Verified the running app's interpreter** (this machine):
   - pid `681720` → `python backend/run.py` (the app).
   - sibling ComfyUI pid `627648` → `/usr/bin/python3.14`, cwd `/home/timo/ComfyUI`.
   - In `python3.14`, `instaloader`, `browser_cookie3`, `gallery_dl`, `curl_cffi` are
     **ALL MISSING** (checked via `importlib.util.find_spec`).

## 3. Critical wrinkle — `browser_cookie3` is never installed, even by "Install everything"

- `browser_cookie3` is **NOT** in `backend/requirements-scrape.txt`.
- `browser_cookie3` is **NOT** in the app's `probe_scrape_deps` check list
  (`curl_cffi, gallery_dl, bs4, cloudscraper, instaloader, ddgs, yt_dlp` —
  `backend/app/capabilities.py:984`).
- Consequence: even `Install everything` installs `instaloader` but **never
  `browser_cookie3`** → the browser-cookie auth path in the Instagram source is
  effectively dead for almost every install. This is a **latent app gap** — a
  candidate code fix for the next AI (see §7).

## 4. Evidence / exact references

- `backend/app/scrape/sources/instagram.py` — the Instagram scraper.
  - `_AUTH_ERROR` string at line ~59: `"Instagram blocked access (login required / rate-limit)."`
  - `_auto_import_browser_cookies(loader)` (line ~88) — Firefox→Chrome cookie import,
    only counts if a `sessionid` cookie is present (line ~106).
  - `_detect_session_username()` (line ~68) — reads `~/.config/instaloader/session-*`.
  - Limits: `SCAN_LIMIT = 50` (line ~54), `PROFILE_SCAN_TIMEOUT = 60` (line ~55).
- `backend/requirements-scrape.txt` — optional scrape extras. `instaloader>=4.12`
  present; **`browser_cookie3` ABSENT**.
- `backend/requirements.txt` — core install, no scrape deps.
- `backend/app/capabilities.py:972-988` — `probe_scrape_deps`, missing-module list
  (no `browser_cookie3`).
- `backend/app/setup_installer.py:244-254, 845-873` — `INSTALL_ACTIONS`, the
  on-demand `scrape_extras` rule, and `_INSTALL_ALL_ORDER` (`scrape_extras` first).
- `frontend/src/components/dataset/ConceptSourcesPanel.jsx:43` — Instagram listed
  under SFW sources.
- `docs/DATASET_GUIDE.md:311-361` — the 🧬 Blend hybrid section (see §6).

## 5. Fixes to give the user (ordered by reliability)

### Fix 1 (reliable — no browser_cookie3 needed)
1. `Setup → Install everything` (installs `instaloader` etc.).
2. In a terminal run `instaloader --login <username>` → writes
   `~/.config/instaloader/session-<username>`.
3. The app auto-detects it via `_detect_session_username()`.
4. Complete any 2FA / checkpoint prompt if asked.

### Fix 2 (browser cookies — optional)
Needs: `pip install browser_cookie3` into the app's Python env (the same
interpreter that runs `backend/run.py`), plus:
- a logged-in browser, and
- **the browser fully closed** (Chrome locks its cookie DB while running), and
- a `sessionid` cookie present.
Then re-scan. This path is currently dead out-of-the-box because `browser_cookie3`
is never installed (see §3).

## 6. The merge-2-people plan (unchanged)

- Scrape each profile (one at a time; the Instagram source returns ≤ 50 posts per
  scan — `SCAN_LIMIT`).
- Promote ~30–150 images per profile into the dataset.
- Train **two separate character LoRAs** (one per person).
- Use Test Studio **🧬 Blend** at ~0.7–0.9 weights — heavier = the person you care
  about most. Blend yields a *hybrid* (one person who is neither of the two), not
  both people in one shot. This is the intended way to "merge 2 people."

## 7. Optional code fix for the next AI (only if the user asks)

Add `browser_cookie3` so the browser-cookie auth path actually works:
1. Add `browser_cookie3` to `backend/requirements-scrape.txt`.
2. Add `browser_cookie3` to the `probe_scrape_deps` missing-module list in
   `backend/app/capabilities.py:984`.
3. Add a `🎁 What's new` entry (see CLAUDE.md conventions).
Respect `CLAUDE.md`: source-only changes, no commits unless asked, never
`frontend/dist/**`. A handoff doc is a non-code artifact; this file lives at repo
root and is fine.

---

## Quick facts for the next AI
- Repo root: `/home/timo/lora-dataset-studio`
- App process: pid `681720` (`python backend/run.py`); its interpreter is
  `/usr/bin/python3.14` — the scrape stack runs **in-process**, so deps must exist
  in that interpreter (see `probe_scrape_deps` docstring).
- The one-click fix is `Setup → Install everything`, then `instaloader --login`.
