# Vouch architecture

> One page per question: *what runs, what talks to what, what decides.* Read top to bottom once, then jump by heading.

## 1. Folder layout (create exactly this, nothing more)

```
vouch/
  config.py        env vars, paths (one place)
  db.py            psycopg pool, run schema/seed, tiny query helpers
  events.py        Kafka produce/consume (4 topics), mirror to review_events table
  listen.py        GitHub issues → feedback rows → embeddings → clusters → severity
  diff.py          git: merge-base, changed files, changed line ranges, commit trailers
  claims.py        Claude call → claims JSON (schema below)
  checks.py        deterministic checks: citations, quotes, tests named, quality flags
  risk.py          risk rules → refusals (contract / safety / honesty)
  tests_run.py     run dotnet tests in a git worktree, parse TRX results
  route.py         reading list + route (light / focused / full), fail-closed
  ledger.py        trust levels per code area × agent, sign-off, escapes
  guard.py         blast radius: touched symbols → callers → existing tests → base vs branch
  tour.py          evidence pack → ordered tour steps (what to show open, what to collapse)
  collab.py        reviewer assignment, presence (Valkey), step votes (Kafka + Postgres)
  review.py        orchestrates one review: diff → guard → claims → checks → risk → tests → route → tour → store
  app.py           FastAPI: JSON API + serves web/
web/
  index.html       the whole dashboard (vanilla JS, fetch + EventSource)
bench/
  plant.py         makes seeded-bug branches (answer key written OUTSIDE the repo)
  score.py         caught vs escaped, reads the key from a path given on the command line
db/schema.sql, db/seed.sql
```

Target repo lives next to ours: `../tieto-messagepack` (clone of Tieto's repo). Never edited in place; tests run in `.work/<branch>` worktrees.

## 2. Data flow

```
GitHub issues ─┐
live complaint ┴─► listen.py ─► feedback (pgvector) ─► clusters ─► requirement
                     │ Kafka: feedback.received / feedback.clustered
                     ▼
agent branch ──► review.py
                  ├─ diff.py      changed lines + who wrote them (trailers)
                  ├─ claims.py    Claude: "what this change does", as claims
                  ├─ checks.py    code verifies every citation + quote
                  ├─ risk.py      refuse-to-decide rules
                  ├─ tests_run.py named tests actually ran and passed?
                  └─ route.py     reading list → light / focused / full
                     │ Postgres: pull_requests, claims, evidence_checks
                     │ Kafka: review.events
                     ▼
dashboard ──► owner signs ──► ledger.py ──► trust level moves
                                  │ Kafka: trust.events
```

## 3. The core rule (put it on a slide)

**Every changed line starts on the human's reading list. A line comes off only if a claim cites it AND that claim is backed by a test the tool saw pass AND no check disputed it. The AI can add reading, never remove it. Anything missing or broken → full read.**

## 4. Claims (what Claude returns)

Claude gets: requirement text + cluster quotes, the diff with new-file line numbers, the list of test names in the changed test files.

```json
{
  "summary": "one paragraph, plain English",
  "claims": [
    {
      "id": "C1",
      "text": "TypeCollector no longer throws for closed generic structs from referenced assemblies",
      "requirement_quote": "exact words from the requirement or a user",
      "cites": [{"path": "src/.../TypeCollector.cs", "start": 702, "end": 718}],
      "tests": ["GenericsFormatterTests.ClosedGenericStructFromReference"],
      "confidence": 0.9
    }
  ],
  "out_of_scope": [{"path": "README.md", "why": "docs edit not asked for"}]
}
```

Prompt rules: one behaviour per claim, cite every line range it explains, quote verbatim, list scope you did NOT need. Use structured output (JSON schema). `confidence` is stored and shown, **never read by route.py**.

## 5. Checks (all deterministic, no AI)

| ID | Check | Fails when | Effect |
|---|---|---|---|
| K1 | Citation exists | path not in diff, or lines outside changed ranges | claim **disputed** |
| K2 | Quote is real | `requirement_quote` not found (normalised whitespace/case) in requirement or cluster feedback | claim **disputed** |
| K3 | Tests exist | a named test is not in the test files | claim **disputed** |
| K4 | Tests passed | named test missing from TRX results, or not `Passed` | claim gives no release |
| K5 | Empty / weakened test | test method with no `Assert`/`Verify`/`Should`, or an assertion line removed | **honesty refusal** |
| K6 | Scope | changed file no claim cites and not in a test/doc allowlist | finding, lines stay |
| K7 | Uncovered requirement | requirement sentences no claim quotes | listed on the PR page |

Every check writes one `evidence_checks` row with `details` explaining itself in one sentence.

## 6. Risk rules (refuse to decide → full read of those files)

| Rule | Matches | Why |
|---|---|---|
| R1 contract: public API | any change to `**/PublicAPI.*.txt`, or a new `public` type/member in `src/MessagePack/**` or `src/MessagePack.Annotations/**` | promise to every user |
| R2 contract: wire format | `src/MessagePack/**/Formatters/**`, `MessagePackWriter`, `MessagePackReader` | breaks stored data |
| R3 contract: analyzer rules | new diagnostic id in `src/MessagePack.Analyzers/**`, new `doc/analyzers/*.md` | user-visible warnings |
| R4 safety | `unsafe`, `Unsafe.`, `Marshal.`, `stackalloc` added | memory safety |
| R5 honesty | K5 fired, or test files deleted | can't trust the evidence |
| R6 deps | `Directory.Packages.props`, `*.csproj` package changes | supply chain |

Rules are a list in `risk.py` (path glob + regex on added lines). Per-repo config, like lint rules.

## 7. Tests (tests_run.py)

1. `git worktree add .work/<branch> <sha>`
2. `dotnet test <project> --filter "FullyQualifiedName~<Class>.<Method>|..." --logger trx` for only the named tests (fast).
3. Parse TRX → `{test: Passed|Failed|NotRun}`.
4. Any build error, timeout (10 min) or missing TRX → `tests: unavailable` → route.py fails closed.

Needs .NET **8.0.4xx** (pinned by the repo's `global.json`).

## 8. Routing (route.py)

```
reading = all changed code lines
for claim in claims:
    if claim not disputed and all its tests Passed:
        reading -= claim.cites
reading += lines of refused files (R1–R6) + finding lines
route = blocked if guard found a regression
route = full   if any refusal, tests unavailable, model failed, or 0 claims
        light  if reading is empty
        focused otherwise
route = max(route, trust_ledger floor for this area × agent)   # 🔴 area → always full
```

Output: `lines_to_read / changed_lines`, the list of ranges with a reason each ("no passing test", "disputed by K2", "R1 public API").

## 9. Trust ledger (ledger.py)

Key: `(project, code_area, agent)`. Code area = second path segment under `src/` (e.g. `MessagePack.SourceGenerator`). Agent = `Lanes-Agent` trailer, else `unknown`.

| Level | Floor on route | Get there |
|---|---|---|
| 🔴 full_read | full | start; any escaped bug |
| 🟡 focused_read | focused | 3 clean sign-offs in a row |
| 🟢 light_check | none | 8 clean sign-offs, 0 escapes |

Clean sign-off = owner accepted, no finding confirmed later. Escape (from `bench/` or reported after merge) → back to 🔴, counter reset. Every change → `trust.events`.

## 10. Sign-off

POST `/api/prs/{id}/signoff` `{owner, decision, residual_risk, ack: [refusal ids]}`. Rejected with 400 if any refusal is not acknowledged or `residual_risk` is empty. Stored in `signoffs`, then ledger update.

## 11. Listen (listen.py)

1. `gh api repos/MessagePack-CSharp/MessagePack-CSharp/issues?state=all` → last ~500 issues + comments.
2. Embed title+body with fastembed `BAAI/bge-small-en-v1.5` (384 dims).
3. Cluster: for each new item, nearest cluster centroid by cosine (pgvector `<=>`); join if distance < 0.25, else new cluster. Label = title of the highest-severity item.
4. Severity = `reports + 0.5·👍 + 0.3·comments`, recomputed on join.
5. The 4 ju26 issues are pinned as requirements of their clusters.
6. `POST /api/feedback {text}` = the live complaint box → same path → Kafka → dashboard updates.

## 12. API (app.py)

| Method | Path | Returns |
|---|---|---|
| GET | `/api/clusters` | clusters with severity, count, linked requirement |
| GET | `/api/clusters/{id}` | feedback items + requirement + PRs |
| POST | `/api/feedback` | adds a complaint |
| GET | `/api/prs` | PR list: route, reading load, cost, status |
| GET | `/api/prs/{id}` | full evidence pack |
| POST | `/api/prs/{id}/review` | (re)run review (queued) |
| POST | `/api/prs/{id}/signoff` | sign |
| GET | `/api/trust` | ledger table |
| GET | `/api/events/stream` | SSE fed by a Kafka consumer (live feed) |

## 13. Dashboard (web/index.html), 4 screens

1. **Clusters**: cards sorted by severity, live complaint box, live event ticker.
2. **Pull requests**: route badge 🔴🟡🟢, reading load bar ("read 70 of 218"), cost, time.
3. **PR page**: requirement + user quotes → claims (🧪 test · 📏 static · 🤖 AI only · ⚪ not checked; disputed = red; confidence greyed "not used") → refusals → reading list (file + ranges + reason) → contributors → sign form.
4. **Trust**: table area × agent with level, clean streak, escapes; history from `trust.events`.

## 14. Failure behaviour (all route UP, never down)

| Missing / broken | Result | Shown as |
|---|---|---|
| Claude call fails or 0 claims | full read | banner "no AI explanation" |
| tests unavailable | nothing released | banner "no test evidence" |
| Kafka down | review still runs, events kept in `review_events` table | ticker shows "offline" |
| Postgres down | app refuses to start | — |
| no provenance trailers | agent = `unknown` → 🔴 floor | contributors: unknown |

## 15. Guard (guard.py): "nothing that worked before is broken"

1. From the diff, list touched symbols: C# method/type names on changed lines (regex on `class|struct|record|interface X` and `X(` declarations; ponytail: regex, upgrade to Roslyn if it misses too much).
2. Callers: `git grep -n -w <symbol>` in `src/` and `tests/` at the branch head.
3. Existing tests = test methods (`[Fact]`/`[Theory]`) in files that reference a touched symbol **and exist on the base commit**.
4. Run them twice (two worktrees, same filter): base and branch. Cap at ~60 tests / 8 min; over the cap, run the ones in the same test class as the changed code first and say "sampled".
5. Verdict per test: `kept` (pass→pass) · `regression` (pass→fail) · `already broken` (fail→fail) · `fixed` (fail→pass).
6. Any `regression` → route = **blocked**, before a human spends a minute. Shown first in the tour.
7. Plus: `PublicAPI.Shipped.txt` lines removed or changed → `api-break` finding.

Stored in `guard_results` (pr, test, base, branch, verdict). Event `guard.done` on `review.events`.

## 16. Review Tour (tour.py + web)

A tour = ordered steps built from the evidence pack. **No AI call here**: it only reorders and folds what was already checked.

| Step kind | From | Shown |
|---|---|---|
| 0 Guard | guard results | blast radius + regressions (if any, the tour stops here) |
| 1 Story | `summary` | 3 sentences + "read N of M lines, ~X min" (X = lines_to_read / 12 per min) |
| 2..n Claim | one claim each, in Claude's story order | claim text → code hunk animates in → evidence badges → lines **collapsed** if released, **open** if on the reading list |
| Refusal | R1–R6 | always open, red frame, needs explicit ✅ |
| Leftovers | lines no claim cites | open, "nobody explained these" |
| Sign | — | accepted risk + sign button (enabled when all steps ✅) |

Animation (CSS only, no library): hunk slides in; removed lines fade to 30% and strike; added lines appear with a 20 ms per-line stagger; badge pops with a scale-in. Syntax highlight: Prism (C#) from cdnjs. Keyboard: `→` next step, `a` approve, `q` question, `x` problem.

❓ Ask: POST `/api/steps/{id}/ask {question}` → Claude answers using only that step's hunk + claim + test names, answer marked 🤖 "AI answer, not evidence".

## 17. Collaborative review (collab.py)

- **Assignment**: for each open step, suggest the reviewer with the most commits on those files (`git log --format=%an -- <file>`, mapped to team members; else round-robin). Anyone can take any step.
- **Presence**: Valkey key `presence:{pr}:{user}` = step id, TTL 15 s, refreshed by the browser every 5 s. `/api/prs/{id}/presence` lists them.
- **Votes**: POST `/api/steps/{id}/vote {user, vote: ok|question|problem, note}` → row in `step_votes` + event on `review.events` → SSE pushes to every open browser.
- **Done** = every step has at least one `ok` and no open `problem`. Then the owner signs (§10).
- Metric on the PR page: total human minutes (sum of time on open steps per reviewer) vs. lines changed.

New tables: `tour_steps (id, pr, ord, kind, claim_id, ranges, collapsed)`, `step_votes (step, user, vote, note, at)`, `guard_results (pr, test, base, branch, verdict)`.

## 18. Measurement (bench/)

`plant.py` copies a ju26 branch and adds one commit with one small bug (off-by-one, flipped condition, removed null check, swapped args) or a harmless change (controls). Key → `~/vouch-key.json`, never in the repo. `score.py` counts: bug **in view** = its line on the reading list or named by a finding; else **escape**. Report reading load + escapes together. Rules fixed before running.
