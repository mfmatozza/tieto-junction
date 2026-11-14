# Workstreams: who builds what, in parallel

Run these workstreams with the Lanes tool so the agents do not collide: see `LANES-INTEGRATION.md`.

4 lanes. Each lane owns its folder and talks to the others **only through the database tables and Kafka topics** (contracts below). Nobody waits for anybody.

One person or one Claude session per lane. Claude sessions: `git worktree add ../tj-lane-N -b lane-N`, one terminal each, merge to `main` every ~2 h.

## The contracts (agree on these first, 10 min, then don't change them)

Every module, rule and endpoint: `docs/ARCHITECTURE.md`.

- Tables: `db/schema.sql`. Lane A owns migrations; others ask before changing.
- Topics: `docs/AIVEN.md` → 4 topics. Message = JSON `{ "type": "...", "id": "...", "at": "...", "data": {...} }`.
- Evidence pack + claims JSON: `docs/ARCHITECTURE.md` §4 and §12, stored in `pull_requests` + `claims` + `evidence_checks`.

## The lanes

| Lane | Owns | Builds | Done when |
|---|---|---|---|
| **A · Infra + Listen** | `vouch/config.py`, `db.py`, `events.py`, `listen.py` | Aiven setup, schema, Kafka producer/consumer helpers. Pull MessagePack GitHub issues + comments → embed (fastembed) → pgvector cluster → severity score. A "post a complaint" endpoint for the live demo. | Posting a complaint shows it in a cluster with severity |
| **B · Prove** (Tieto core) | `vouch/diff.py`, `claims.py`, `checks.py`, `risk.py`, `tests_run.py`, `guard.py`, `route.py`, `review.py` | Diff of a ju26 branch → Claude writes claims (JSON) → code verifies line citations + requirement/user quotes → runs named tests in a git worktree (.NET 8) → risk rules (public API, wire format, analyzers, generated files) → route. Fails closed. | Evidence pack JSON for 2283 and 2129, routes differ |
| **C · Dashboard** | `vouch/app.py`, `ledger.py`, `tour.py`, `collab.py`, `web/index.html` | FastAPI + one HTML page: cluster board → PR list → PR page (claims ✅/❌, how each was checked, reading list) → sign form → trust levels → live Kafka feed. Start on seed data, swap to real data later. | A judge can click through without help |
| **D · Measure + Pitch** | `bench/`, `docs/DEMO.md`, slides, video | Plant ~10 bugs on copies of ju26 branches (answer key kept OUT of the repo), run lane B on them, count caught vs escaped. Write pitch, record video, Junction submission. | One honest number + 2-min video |

## Order of merges

1. A pushes schema + seed (first hour) → C builds on seed.
2. B pushes first evidence pack JSON → C renders it.
3. A pushes live feedback → C shows clusters.
4. D runs B's tool on planted bugs → number goes on the dashboard + slides.

## If you're only 1–2 people

Do lanes **B → C → A → D** in that order. B + C alone already answer the Tieto brief.
