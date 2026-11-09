---
paths:
  - ".github/workflows/**"
  - "frontend/scripts/**"
---

# Public release mechanics

Read this when landing a wave on this public fork's `main` or changing release
tooling. Releases are cut from validated waves, never per commit. Agents must
not create releases, merge GitHub pull requests or change repository settings.

## Qualify the public tree

- Keep `main` releasable. Integrate only approved public upstream `v2` history;
  private product history cannot enter public history even after deleting files.
- Before landing or pushing a wave, require both full suites and both linters
  on the exact final tree. Reuse results that still cover that tree; resolve
  conflicts and fixes before validating. CI's size gate can skip heavy jobs,
  so it does not replace the local gate.
- From the repository root:
  `python -m pytest backend/tests scripts/tests -q -n 8 --dist loadfile`
  and `ruff check .`.
- From `frontend/`: `npm test` and `npm run lint`. Include core and bundled
  node tests and any required bundled profile; do not substitute plain
  `node --test` for the repository's complete test command.
- Backend privacy and all contract tests are part of the full suite. Run
  bundled Python contracts in isolated product processes and the release asset
  policy check as documented in `.github/workflows/ci.yml`.
- Use `backend/requirements-dev.txt` and the pinned CPU Torch overlay in
  `backend/requirements-torch-tests.txt` for runtime coverage. Keep the explicit
  `backend/tests` path to load `backend/pytest.ini` and its plugin exclusions.
- Use exactly eight local xdist workers and a short, task-owned `--basetemp`
  outside the repository. If a worker crashes or a test appears flaky, replay
  the named test in isolation, investigate it, and rerun the full failed suite.
  A crash or unverified failure is never a pass.
- Run responsive probes for changed layouts on populated affected surfaces.
  Report unavailable controls as skipped, not verified.
- Rebuild only if changed frontend inputs are not represented in `dist`.
  Build from a clean source tree and commit changed artifacts separately as
  `build(frontend):`. Documentation-only changes need no rebuild.

## Tag and release reference

These details describe the human release process, not agent authorization.

- A release tag matches `APP_VERSION`. `release.yml` runs its own suites and
  rebuilds the packaged frontend. Do not add a duplicate manual full run solely
  because a qualified wave receives a tag.
- Check the current workflow for tracked-dist/toolchain drift and packaging
  behavior; the ZIP uses its fresh build.
- `frontend/scripts/releaseNotes.mjs` uses What's-new entries added since the
  last published release, not their entry dates. A deliberately notes-free
  plumbing release needs `[no-notes]` in the tag message read by the workflow.
- Wait for successful release publication before announcing availability.
  A pushed tag alone is not a published release. Announcements tell users to
  "Update & restart".
