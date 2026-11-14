# PLAN — Vouch (Junction 2026 · Tieto "Earned Trust in AI Code" + Aiven)

> ⏰ Saturday 14 Nov → submission Sunday 15 Nov. **~14 h of building + 4 h sleep.**
> ✅ done · 🔲 to do. Top to bottom. Parallel split: `docs/WORKSTREAMS.md`. Every module: `docs/ARCHITECTURE.md`.

## 🗣️ What the judges told us (14 Nov)

1. They judge the **spark**, not the flashy result.
2. The point: **backlog → implementation, safely, without breaking existing functions.**
3. **Nobody can review thousands of lines.** Today's review is long and tedious.
4. They want a review a human can **actually finish**, ideally **collaborative**.

## 🎯 One sentence

**Vouch takes a backlog item to a merged change without breaking anything, and turns a 1,000-line AI diff into a 5-minute guided review that a team does together.**

## 🧩 The pipeline

```
 1 BACKLOG        2 IMPLEMENT          3 GUARD               4 PROVE              5 REVIEW TOUR          6 SIGN + EARN
 issues ranked →  agents build it,  →  existing tests run →  AI claims checked →  animated walkthrough → owner signs,
 by real users    no collisions        before vs after:      by code, tests run   story order, proven    trust per area
                  (Lanes)              nothing broke?                             code collapsed,        × agent moves
                                                                                  team splits the reading
```

**The spark = steps 3 + 5.** Step 3 answers "did it break anything?" with proof. Step 5 answers "can a human review this?" with yes, in minutes, together.

## ⚡ The spark, concretely

### Guard: "nothing that worked before is broken"
- Find what the change touches: changed methods/types → their callers → the **existing** tests that exercise them.
- Run those tests on the **base** and on the **branch**. Passed before + failed after = 🛑 **regression, blocked before any human looks.**
- Public API diff: anything removed or changed in `PublicAPI.*.txt` = flagged.
- Screen: **"Blast radius: 14 callers, 37 existing tests, 37/37 still pass."**

### Review Tour: 1,000 lines → 5 minutes
- No file-by-file diff. **The AI tells the change as a story, step by step** (one step = one claim).
- Each step animates: the claim in plain words → the view glides to the code → edited lines type in, old lines fade out → evidence badges pop (🧪 test passed · 📏 rule · 🤖 AI only).
- **Proven code collapses** to one line ("42 lines, backed by 3 passing tests ✓"). **Only unproven / risky lines stay open.**
- Per step the reviewer clicks ✅ looks right · ❓ ask · ❌ problem. ❓ goes to the AI (answer grounded in the diff) or to a teammate.
- Header: **"Changed 1,043 lines · You read 61 · ~5 min"** with a live timer.

### Collaborative review
- The reading list is **split between reviewers** by who knows the code (git history of each file).
- Live presence: avatars on the step each person is on, comments appear for everyone instantly.
- The change is signed only when **every step is ✅ by someone** and the owner writes the accepted risk.
- Built on Aiven: presence in **Valkey** (keys with TTL), step updates on **Kafka** `review.events`, record in **Postgres**.

## 🛠️ Infra

| # | What | Status |
|---|---|---|
| 1 | Aiven PostgreSQL + pgvector | 🔲 |
| 2 | Aiven Kafka (`ca.pem`) | 🔲 |
| 3 | **Aiven Valkey**, now **needed** (live presence for collaborative review) | 🔲 |
| 4 | .NET 8 SDK | ✅ 8.0.428 |
| 5 | Anthropic API key in `.env` | ✅ tested |
| 6 | Aiven MCP in Claude Code | ✅ added, restart Claude Code to load |
| 7 | GitHub, Python 3.12, Node 24, git | ✅ |
| 8 | Lanes server on one laptop | 🔲 |
| — | OpenSearch | ❌ skipped |

## 📋 Judging criteria → what judges see

| Criterion | Feature |
|---|---|
| **Don't break things** | Guard: existing tests before vs after, regression = blocked |
| **Reviewable by a human** | Review Tour: proven code collapsed, "read 61 of 1,043" |
| **Collaborative** | Split reading list, live presence, shared comments |
| **Risk** | Public API / wire format / analyzers → always open in the tour |
| **Hallucination** | Fake citation or quote → step turns red, can't be collapsed |
| **Transparency** | Every step shows HOW it was checked |
| **Confidence** | AI confidence greyed, "not used" |
| **Ownership** | Named owner signs + accepted risk |
| **Self-distrust** | Planted bugs: caught X of Y; escape → area back to 🔴 |

## ⏱️ Build order (new)

| # | Block | Time | Done when… | Status |
|---|---|---|---|---|
| 1 | Aiven PG + Kafka + Valkey, `.env`, schema + seed | 45 min | tables exist | 🔲 |
| 2 | Clone Tieto repo, run 2283 tests on .NET 8 | 30 min | tests pass | 🔲 |
| 3 | **Prove**: diff → claims → checks → risk → route | 3 h | evidence pack for 2283 + 2129 | 🔲 |
| 4 | **Guard**: touched symbols → existing tests → base vs branch | 2 h | "37/37 still pass" for 2283 | 🔲 |
| 5 | **Review Tour** UI with animation | 3.5 h | 2283 tour plays end to end | 🔲 |
| 6 | **Collaborative**: split list, presence, live ✅/❓ | 2 h | 2 browsers review together | 🔲 |
| 7 | Backlog board: seeded ranked issues + live "add issue" | 1 h | issue → PR → tour link | 🔲 |
| 8 | Measure: planted bugs | 1.5 h | one honest number | 🔲 |
| 9 | Pitch: video + slides + submit | 2 h | submitted | 🔲 |
| — | Sleep | 4 h | | 🔲 |

**Behind? Cut 8, then shrink 7 to a static list. Never cut 3, 4, 5, 9.** Cut 6 last: judges asked for it.

## 🏆 Why we win

The public competitor is a CLI that prints Markdown. Ours: **a guarded, guided, shared review that a team finishes in minutes**, with proof nothing broke, on a live Aiven backend.

## ▶️ NEXT ACTION (5 min)

Create the 3 Aiven services (Postgres, Kafka, Valkey) in the Aiven console and paste their URIs into `.env`.
