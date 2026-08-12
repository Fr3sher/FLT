# HANDOFF — Reddit app creation fails silently (no app appears)

**Filed by:** Codex agent, 2026-08-11
**For:** an AI WITH BROWSER ACCESS (can drive the Reddit UI directly)
**Status:** blocked on browser-side debugging — the form submit does nothing visible

---

## 1. Goal

Get the user a Reddit **installed-app** `client_id` so FLT - Fresh LoRa Trainer's Reddit
scraper stops rate-limiting (429 "Reddit is rate limiting requests, retry in Ns").
The studio needs a **secret-less installed-app id** — a web-app/`script` id comes
with a `client_secret` and the studio's anonymous login then fails with 401.

The `client_id` gets pasted into the studio Settings → Reddit client ID field
(it takes effect immediately, no restart needed). **Do NOT paste it into this file
or commit it anywhere.**

## 2. Exact state at handoff

- User opened `https://www.reddit.com/prefs/apps` and clicked **create app** (bottom of page).
- The form fields the user filled:
  - Type: **`Anwendung Installiert`** (installed app) — the required type
  - Name: `FLT - Fresh LoRa Trainer`
  - Description: `Personal scraper for LoRA training datasets`
  - Link Info / about URL: `https://github.com` (valid — earlier `asdafasd` was invalid and that DID fail)
  - Redirect URI: `http://localhost` (never used, but the form requires it)
- **Symptom:** clicking **App erstellen** produces no success, no error, and **no app
  appears in the list on `/prefs/apps`**. The only text the user sees is the standard
  legal notice: *"In order to create an application or use our API you can read our
  full policies here…"* — that notice is NOT an error, it's always on the page.
- User is frustrated and wants a browser-capable AI to just fix it.

## 3. Likely causes (in priority order) — verify with browser control

1. **Not logged in to Reddit.** `/prefs/apps` needs an active session. Check the
   top-right of reddit.com: does the user's username/avatar show? If not, log in
   first, then re-open `/prefs/apps`.
2. **Ad-blocker / privacy extension breaking the form's JS.** The create-app form is
   JS-heavy; a blocker can make the submit button a silent no-op. Disable the
   blocker (or use a clean non-private window), retry.
3. **Form validation error not visible.** After clicking, look for a small red
   message at each field or at the top of the form (e.g. "Please enter a valid
   redirect uri" / name taken). If found, read it back verbatim.
4. **Account not verified / not fully registered.** The page says "You must also
   register to use the API" — if the account lacks email verification, creation
   can silently fail. Check the account's email-verification status in settings.
5. **App WAS actually created but not visible** — re-open `/prefs/apps` fresh;
   sometimes no toast shows. If an entry now exists under the name
   "FLT - Fresh LoRa Trainer", the id is the short ~22-char string under the name.

## 4. What success looks like

After creation, on `/prefs/apps` there is an entry **"FLT - Fresh LoRa Trainer"** whose
type is **installed app** (no secret shown — installed apps have none). The
**`client_id`** is the short ~22-character string displayed directly under the app
name. That id is what the user pastes into the studio.

## 5. If you can create it (browser AI actions)

- Navigate to `https://www.reddit.com/prefs/apps`, ensure logged-in.
- Click **create app**; fill: type `installed app`, name `FLT - Fresh LoRa Trainer`,
  description `Personal scraper for LoRA training datasets`, about URL
  `https://github.com`, redirect uri `http://localhost`.
- Click **create app**; confirm an entry appears; copy the `client_id` and show it
  to the user so they can paste it into the studio Settings field.

## 6. Fallback (if Reddit UI is truly broken)

- A valid installed-app id from ANY account works — the user just needs *a*
  private quota. If creation keeps failing, try: another browser profile, logging
  out/in, or completing email verification first.

---

**Notes for the next AI:** The user already knows the form fields (they filled them
correctly). Do NOT re-explain the form — the blocker is that submit does nothing.
Use browser control to (a) confirm login, (b) check for red validation messages,
(c) re-check `/prefs/apps` after submit, (d) if all else fails check account
verification. The studio onboarding text (which the user pasted) is authoritative:
**installed app, no secret** — a `script`/web id will break the studio's 401-free
anonymous login. Do not commit the `client_id`.
