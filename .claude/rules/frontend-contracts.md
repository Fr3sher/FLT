---
paths:
  - "frontend/**"
---

# Frontend contracts (enforced by tests)

## 🎁 What's new (`frontend/src/whatsNew.js`)

Prepend one **benefit-first** entry per user-visible feature or fix. Between
releases this panel is the ONLY way users learn something shipped. Plumbing and
refactors don't need one — bugfixes of unreleased work don't either.

Release notes are built from the entries this file gained since the previous
tag (`frontend/scripts/releaseNotes.mjs`, git diff of the file — not entry
`date`). Skipping an entry costs a release, not just a panel line.

## Help registry (`frontend/src/help/helpRegistry.js`)

Any new setting, section, page or big button needs a topic (and its Guide
anchor), or the contract test fails.

## Commits & dist

- **Source-only commits.** Never commit `frontend/dist/**` alongside sources;
  the dist rebuild is a separate consolidated `build(frontend):` commit at the
  end of the wave.
- Frontend tests: `node --test` from `frontend/` — includes the help-registry
  and what's-new contract tests.

## Stable identifiers

Never rename catalog labels, config keys or What's-new ids without an alias
path — several are stored in user databases and localStorage.
