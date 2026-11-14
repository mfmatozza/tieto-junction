# PLAN — Vouch (Junction 2026 · Tieto "Earned Trust in AI Code" + Aiven)

> ⏰ It's Saturday 14 Nov. Demo/submission is Sunday 15 Nov. **You have ~18–20 working hours. Not a week.**
> ✅ = done · 🔲 = to do. Do them in order. Don't skip ahead.

---

## 🔥 DO THIS FIRST (10 min)

1. 🔲 Open https://hackjunction.app/participate/45/challenges/351 (logged in)
2. 🔲 Copy the **whole page text** into `docs/BRIEF.md` (judging criteria + submission deadline + what to submit)
3. 🔲 Same for the Aiven page → `docs/AIVEN.md`
4. 🔲 Paste both to Claude: "check PLAN.md against these"

Why: I could not read them (login wall). The criteria below are reverse-engineered. 90% sure, not 100%.

---

## 🎯 The idea in 1 sentence

**Vector turned user complaints into AI pull requests. Vouch does the same, but the AI must *earn* the right to ship: every PR carries proof, and each code area has a trust score that goes up with clean merges and drops on bugs.**

## 🧩 The idea in 5 boxes

```
 1. LISTEN          2. REQUIREMENT       3. AGENT PR         4. VOUCH (the judge)     5. HUMAN SIGNS
 user feedback  →   clustered issue  →   AI writes code  →   proof or it's read   →   owner accepts risk
 (GitHub issues)    + real user quotes   (Tieto's 4 ju26     by a human             → trust ledger updates
 Kafka → pgvector   severity score       branches)                                   (Aiven Postgres)
```

- **Box 1–2 = Vector** (the devpost/reel project). Kept, but feedback = MessagePack GitHub issues instead of X posts.
- **Box 3** = Tieto already gives you agent-written branches. Don't build an agent first. Stretch goal only.
- **Box 4–5 = the Tieto part. This is where the points are.** 70% of your time goes here.

## 🏆 Why we win (vs the one public competitor)

The only public competitor (`JesseSaarinen/tieto-trust-review`, solo, strong) = CLI tool, Markdown reports, no UI, no database, no link to real users.

We beat it on 4 things:

1. **Trace to humans** — every AI claim must quote a real user's words (from the feedback cluster) or the issue text. Fake quote = claim rejected automatically.
2. **Earned autonomy, like a driving licence** — each code area has a level: 🔴 L0 human reads everything → 🟡 L1 focused read → 🟢 L2 light check. Clean merges move it up. One escaped bug drops it to 🔴.
3. **Closed loop** — after merge, did the complaint cluster go quiet? That's the real proof the AI fixed it.
4. **A live dashboard** judges can click. Not a terminal.

⚠️ Don't copy his code or text. Same problem, our own design.

---

## 📋 Judging criteria (reverse-engineered — confirm in step 0)

Every team answers the same tensions. Each needs **one visible feature** in the demo:

| Criterion | Our feature that answers it |
|---|---|
| **Risk** — how deep to review? | Risk tier from *what can break* (public API, wire format, untrusted input), not lines changed |
| **Hallucination** | Line citations + user quotes checked by code, not by AI. Wrong cite = claim rejected |
| **Transparency** | Every claim shows HOW it was checked: test run / static rule / AI-only / not checked |
| **Confidence** | AI confidence is shown but **ignored**. Only evidence moves the level |
| **Quality** | Flags weakened tests, tests with no asserts, changes beyond the requirement |
| Who owns the decision? | Named human signs in the UI, writes the risk they accept. Stored in Postgres |
| How does it scale? | Cost + minutes per review shown on every PR. Trust per code area, not per repo |
| When to NOT trust ourselves? | Plant bugs → measure how many slip through. Escape = area drops to 🔴 |

---

## 🛠️ Aiven — use 3 services (bonus prize)

| Aiven service | Job | Why judges care |
|---|---|---|
| **PostgreSQL + pgvector** | feedback embeddings, clusters, claims, sign-offs, trust ledger | main DB |
| **Kafka** | event log: `feedback.raw` → `pr.reviewed` → `pr.signed` | immutable audit trail = trust |
| **Valkey** | job queue for reviews + cache | fast, cheap |
| (bonus) **Aiven MCP server** (`Aiven-Open/mcp-aiven`) | Claude agent queries the ledger in plain English | "AI-native" demo moment |

Free tier is enough. ⚠️ Free services power off when idle — hit them before the demo.

---

## ⏱️ Build order (each block = one thing that works)

| # | Block | Time | Done when… |
|---|---|---|---|
| 0 | Read brief + Aiven page (above) | 10 min | `docs/BRIEF.md` exists |
| 1 | Aiven: create PG + Kafka + Valkey, put URLs in `.env` | 30 min | `python -m vouch.db` prints "ok" |
| 2 | Clone Tieto repo, check out `ju26-issue-2283`, run its tests | 45 min | tests run on your laptop (dotnet 9 is installed ✅) |
| 3 | **Vouch core:** diff → Claude writes claims → code checks cites + runs tests → risk tier | 4 h | one JSON "evidence pack" for 2283 |
| 4 | Store pack + ledger in Postgres, events to Kafka | 1.5 h | rows show up |
| 5 | Dashboard: PR list · claims with ✅/❌ · reading list · sign button · trust levels per area | 3 h | judges can click it |
| 6 | Listen: pull MessagePack GitHub issues → embed → cluster → severity | 2 h | 2283's cluster shows real user quotes |
| 7 | Measurement: plant 10 bugs on copies of branches → count escapes | 2 h | one number: "caught X of 10" |
| 8 | Pitch: 2-min video + 3 slides + README | 2 h | submitted |
| — | Sleep | 4 h | not optional |

Total ≈ 16 h + sleep. **If behind schedule: cut block 6 first, then 7. Never cut 3, 5, 8.**

## 🧱 Stack (boring = fast)

- Python 3.12 + FastAPI + one HTML page (no React build step)
- Claude API (`claude-opus-5-5`) for claims; a cheaper model as second opinion if time allows
- `psycopg` (Postgres), `confluent-kafka`, `redis` client (works with Valkey)
- Tests run in a `git worktree` copy so the main checkout stays clean

## 📁 Repo map

```
PLAN.md          ← you are here
README.md        ← pitch version for judges
docs/INTEL.md    ← what I found: brief sources, Tieto repo, competitors
docs/BRIEF.md    ← 🔲 you paste the official brief here
```

---

## ▶️ NEXT ACTION (2 min)

Open the Tieto challenge page while logged in, select all, paste into `docs/BRIEF.md`.
