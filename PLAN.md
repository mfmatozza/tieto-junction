# PLAN — Vouch (Junction 2026 · Tieto "Earned Trust in AI Code" + Aiven)

> ⏰ Saturday 14 Nov → submission Sunday 15 Nov. **~16 h of building + 4 h sleep.**
> ✅ done · 🔲 to do. Top to bottom. Parallel split: `docs/WORKSTREAMS.md`.

## 🎯 One sentence

**Vector turns user complaints into AI pull requests. Vouch is Vector with a conscience: same pipeline, but no AI change reaches merge without proof, a human signature, and a trust score it has to earn.**

## 🧩 The pipeline (looks like Vector, judged like Tieto)

```
 1 LISTEN            2 CLUSTER + RANK         3 AGENT PR            4 VOUCH                 5 SIGN + EARN
 complaints come  →  pgvector groups them  →  AI writes the fix  →  claims checked by    →  human signs risk
 in (GitHub issues,  severity = reports +     (Tieto's 4 ju26       code, tests run,         trust level per
 live form)          reactions + comments     branches)             risk rules → route       code area moves
 ── Kafka ─────────────── Postgres ──────────────────────────────────── Postgres ──────────── Kafka ──
```

- **1–3 = Vector** (Devpost vector-l89mzu). Kept almost 1:1. Feedback source = MessagePack GitHub issues + a live "post a complaint" box instead of X posts.
- **4–5 = Tieto.** This is where the points are. ~60% of the time.
- Agent in step 3: use Tieto's agent-written branches. Our own agent writing a PR live = stretch (Claude Code headless on one tiny issue).

## 🛠️ Infra you need (set up first)

| # | What | Status | Why |
|---|---|---|---|
| 1 | **Aiven PostgreSQL** + pgvector | 🔲 | main DB + clustering |
| 2 | **Aiven Kafka** (SASL, download `ca.pem`) | 🔲 | live pipeline feed + audit |
| 3 | **Aiven Valkey** | 🔲 optional | job queue; Postgres can replace it |
| 4 | **.NET 8 SDK 8.0.4xx** | 🔲 **blocker** | Tieto repo's `global.json` pins 8.0.402. You only have .NET 9 → tests won't run. `winget install Microsoft.DotNet.SDK.8` |
| 5 | **Anthropic API key** | 🔲 | Claude writes the claims |
| 6 | **GitHub token** | ✅ (`gh` logged in) | pull issues |
| 7 | Python 3.12, Node 24, git | ✅ | |
| 8 | **Lanes** (`~/Desktop/lanes`, build once) + one laptop running `lanes server` | 🔲 | teammates' agents don't collide + per-agent provenance. `docs/LANES-INTEGRATION.md` |
| — | Embeddings: `fastembed` (local, 384 dims) | — | no extra API key |
| — | OpenSearch | ❌ skipped | Postgres covers it |

Details: `docs/AIVEN.md`.

## 📋 Judging criteria → feature (inferred, confirm against the official page)

| Criterion | What judges see |
|---|---|
| **Risk** | Route from what can break (public API, wire format, analyzers), not size. 2129 → full read even though the AI is confident |
| **Hallucination** | Fake line cite or fake quote → claim auto-rejected, shown in red |
| **Transparency** | Each claim tagged: 🧪 test run · 📏 static rule · 🤖 AI only · ⚪ not checked |
| **Confidence** | AI confidence shown greyed out, labelled "not used" |
| **Quality** | Flags: weakened tests, empty asserts, scope creep |
| **Ownership** | Named human signs + writes residual risk. Can't sign without acknowledging refusals |
| **Scale** | Cost + minutes per review; trust per code area |
| **Self-distrust** | Planted-bug audit: "caught X of Y". Escape → area drops to 🔴 |
| **Vector bonus** | Every requirement links back to the real users who asked for it |

## 🏆 Why we beat the public competitor

`JesseSaarinen/tieto-trust-review` = strong CLI, Markdown output, no UI, no DB, no users. We win on: **real users in the loop · live dashboard · earned-autonomy levels 🔴🟡🟢 per area AND per agent (via Lanes) · Aiven event stream.** Don't copy his code, text or numbers.

## ⏱️ Build order

| # | Block | Time | Done when… | Status |
|---|---|---|---|---|
| 0 | Paste official briefs into `docs/BRIEF.md`, `docs/AIVEN.md` | 10 min | text is in | 🔲 |
| 1 | Infra table above: Aiven ×2–3, .NET 8, keys in `.env`; run `db/schema.sql` + `db/seed.sql` | 45 min | `psql` shows 4 PRs | 🔲 |
| 1b | Lanes level 1: `lanes init` here, server + invites, everyone on Claude Code | 30 min | `lanes app` shows every teammate | 🔲 |
| 2 | Clone Tieto repo next to this one, run tests on `ju26-issue-2283` | 45 min | tests pass locally | 🔲 |
| 3 | **Prove** (lane B): claims → checks → tests → route | 4 h | packs for 2283 + 2129 differ | 🔲 |
| 4 | **Dashboard** (lane C) | 3 h | clickable end to end | 🔲 |
| 5 | **Listen** (lane A): issues → embed → cluster → severity, live complaint box, Kafka feed | 2.5 h | complaint appears live in a cluster | 🔲 |
| 5b | Lanes level 2: read `Lanes-Agent`/`Lanes-Task` trailers → contributors per line, trust per area × agent | 1.5 h | PR page shows who wrote what | 🔲 |
| 6 | **Measure** (lane D): ~10 planted bugs, caught vs escaped | 2 h | one honest number | 🔲 |
| 7 | Pitch: 2-min video + 3 slides + README + submit | 2 h | submitted | 🔲 |
| — | Sleep | 4 h | | 🔲 |

**Behind schedule? Cut 6, then 5b, then shrink 5 to "seeded clusters". Never cut 3, 4, 7.**

## 🧱 Stack

Python 3.12 · FastAPI · one HTML page (no build step) · `psycopg` · `confluent-kafka` · `fastembed` · Claude `claude-opus-5-5` · tests in a `git worktree`.

## 📁 Repo map

```
PLAN.md               ← you are here
README.md             ← pitch for judges
docs/WORKSTREAMS.md   ← parallel split: who builds what
docs/LANES-INTEGRATION.md ← build with Lanes + Vouch reads Lanes provenance
docs/AIVEN.md         ← infra + Kafka topics
docs/BRIEF.md         ← working brief (paste official text)
docs/INSPIRATION.md   ← Vector → Vouch mapping
docs/DEMO.md          ← 2-min click path
docs/INTEL.md         ← sources + competitors
docs/NAMING.md        ← name + backups
db/schema.sql         ← tables (incl. clusters + pgvector)
db/seed.sql           ← 4 Tieto branches, real SHAs, empty results
```

## ▶️ NEXT ACTION (2 min)

Run `winget install Microsoft.DotNet.SDK.8` and let it install while you create the Aiven services.
