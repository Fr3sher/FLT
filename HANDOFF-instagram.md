# HANDOFF — Instagram 429 / `_giules` scan (LoRA Dataset Studio)

For the next AI that has browser + shell access on this machine. Practical, no fluff.

## TL;DR
- Instagram is NOT an auth problem. `_giules` EXISTS (public). The blocker is a
  **429 rate-limit on the `web_profile_info` endpoint** (aggressive right after a
  fresh login; earlier probing made it worse).
- Root cause fixed in code: the app now retries (5 attempts w/ backoff) and
  reports rate-limit honestly instead of the misleading "blocked access (login required / rate-limit)".
- Image rebuilt + container recreated. API healthy. One scan is STILL in flight
  (instaloader honoring a ~666 s backoff sleep) — it may return 429 until the throttle cools.

## Environment (verified)
- App: Docker `lora-dataset-studio`, API-only, source `/home/timo/lora-dataset-studio`.
- Backend is **baked into the image** (`COPY backend backend`), only `.env` is mounted.
  → code changes require `docker compose build` + `docker compose up -d --force-recreate`, NOT just restart.
- Mounts are LIVE (recreate is safe): `.config`→/root/.config, `data-docker`→/data,
  `ComfyUI`, `ai-toolkit`, `.env`. No rebuild of those; nothing else changes.
- Deps installed in image: `instaloader 4.15.3`, `browser-cookie3 0.20.1`, CLI `/usr/local/bin/instaloader`.
- Container minimal (no `ps`): use `/proc/[0-9]*/cmdline`.
- ComfyUI API: `http://10.1.10.179:8188` (compose `environment:` wins over `.env`).

## What I proved (don't re-do)
- `GET https://www.instagram.com/_giules/` → **200** HTML (603 KB). Profile exists.
- Session pickle `/root/.config/instaloader/session-dr_fresher` is a **dict of cookies**
  (NOT a requests.Session): has `sessionid, mid, ig_pr, ig_vw, ig_cb, csrftoken,
  s_network, ds_user_id, ig_did, ig_nrcb, rur`.
  `sessionid=19690244236%3A8g6GwRmYPPDrxX%3A15%3A...`, `csrftoken=oAOjogZWNqhnyoNjKTAADAWW5QgyILQo`, `ds_user_id=19690244236`.
- `Profile.from_username(ctx,'_giules')` → **429**, instaloader sleeps 666 s → timed out.
  Session loads fine — the account IS logged in, just throttled on this endpoint.
- `web_profile_info` returns 404 "not-logged-in" anonymously AND with a hand-built cookie
  session (my cookie build ≠ instaloader's, so 404 ≠ clean). With `X-CSRFToken`+cookies it
  flipped to **429** after repeated probing — I hammered it, worsening throttle.
- `i.instagram.com/api/v1/users/web_profile_info/` → also 429.
- `?__a=1` trick is dead (200 JS "for (;;);... error 1357055").
- 2026 IG hydration HTML has NO simple parseable profile JSON (`_sharedData`/JSON-LD gone;
  userId/username buried in 157 KB / 40 KB bootstrap blobs). HTML-parse fallback not trivial.

## Code fix applied (in image now)
`backend/app/scrape/sources/instagram.py`:
- `_build_loader` (~L136): `max_connection_attempts=1` → **5** (instaloader retries 429 w/ backoff).
- `_scan_profile` (~L250) + `_scan_single` (~L371): added
  `except instaloader.TooManyRequestsException` → returns distinct
  `"Instagram rate-limit: trop de requêtes. Attends ~10 min avant de relancer."`
  instead of the misleading `_AUTH_ERROR`.
- Kept `ProfileNotExistsException` separate.
- Verified inside container: `max_connection_attempts=5` @L136, catches @L250 & L371.
- Rebuilt image, `docker compose up -d --force-recreate`. API healthy (`/api/health` 200).

## API test recipe (CSRF gotcha)
Flask-WTF CSRF protects POST. Flow (cookie jar REQUIRED):
1. `curl -c cj.txt http://localhost:5050/api/csrf-token` → `{"csrf_token": ...}`
   (route is `/api/csrf-token`, NOT `/api/n-token`).
2. `TOKEN=<that>`
3. `curl -b cj.txt -X POST http://localhost:5050/api/scrape/scan \
     -H 'Content-Type: application/json' -H "X-CSRFToken: $TOKEN" \
     -d '{"url":"https://www.instagram.com/_giules/"}`
Expected: `{scannable, platform, count, items}` 200. While throttled: the honest
rate-limit message instead of the old misleading one.
A scan is CURRENTLY in flight (started 2026-08-11 ~01:12, instaloader 429-backoff sleep,
up to ~11 min / up to 5 attempts). Poll it before re-testing; do NOT fire another
scan until it settles (avoid re-hammering the throttle).

## If still throttled after cooldown (ordered)
1. Refresh IG session in container: `docker exec -it lora-dataset-studio instaloader --login dr_fresher`
   (2FA code needed). New login resets the throttle window.
2. Or import the user's authenticated browser cookies via `browser-cookie3` (installed):
   the app's `_auto_import_browser_cookies` already does this — check
   `data-docker/app.log` for "Session Instagram détectée" / cookie-import lines.
3. `get_posts()` uses `api/v1/feed/user/{id}/` — a DIFFERENT endpoint; once the metadata
   429 passes, feed usually works. So one successful profile fetch unblocks the dataset scrape.

## Related threads (don't reopen)
- Reddit client_id: `/home/timo/lora-dataset-studio/HANDOFF-reddit.md` (browser-AI handoff, 83 lines).
  User's Reddit "create app" click shows nothing — likely Reddit's dev-page JS/registration gate,
  not a form they're missing. Don't re-explain the form; don't commit the `client_id`.
- Merge 2 people (Blend): follow `docs/DATASET_GUIDE.md:311-361` once both profiles are scraped.
- `HANDOFF-scrape.md` is STALE (claims deps missing; reality: deps installed, blocker is 429).
