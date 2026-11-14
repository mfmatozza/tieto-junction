# How Vouch works, step by step

**The rule:** the AI only *proposes*. Plain code *decides*. A person *signs*.
No step uses the AI's confidence. If any part fails to run, Vouch shows **more** code, never less.

```
1 LANES  →  2 GUARDRAIL  →  3 CHECKPOINT  →  4 READING LIST  →  5 EASYREVIEW  →  6 SIGN-OFF
 agents      old tests        AI claims         what a person     team reviews      owner signs
 write       still pass?      checked by code   must read         live              the risk
```

---

## 1. Lanes: agents write code without colliding

- **In:** backlog issues, several coding agents.
- **What happens:**
  1. An agent asks the Lanes server for the files it will edit.
  2. If another agent holds that file, the second one waits.
  3. Every commit gets a `Lanes-Agent:` line (which agent) and a `Lanes-Task:` line (which issue).
- **Out:** one pull request per issue, each commit labelled with its agent.
- **AI involved?** The agents write code. Lanes itself is plain coordination code.
- **Code:** [github.com/mfmatozza/lanes](https://github.com/mfmatozza/lanes). Vouch reads the trailer in `vouch/review.py` (`Lanes-Agent`). No trailer = agent `unknown` = trusted for nothing.

## 2. Guardrail: did anything that worked break?

- **In:** the base commit and the agent's commit.
- **What happens:**
  1. Check out both commits in separate git worktrees.
  2. Run the **existing** test suite on each, with the language's own tool.
  3. Compare test by test:

| Before | After | Verdict |
|---|---|---|
| pass | pass | kept |
| pass | fail or missing | **regression → change blocked** |
| fail | pass | fixed |
| fail | fail | already broken |

- **Out:** for example "167/167 kept, 0 regressions, 3 new tests".
- **If the tests cannot run** (build error, timeout, tool missing): Guardrail is marked "not run" and the whole change must be read.
- **Languages:**

| Language | Tool run | Result read from |
|---|---|---|
| .NET | `dotnet test` | TRX report |
| Python | `pytest --junitxml` | JUnit XML |
| JS / TS | `vitest`, `jest --json` or `node --test` | JUnit XML or Jest JSON |
| Go | `go test -json` | JSON events |
| Java / Kotlin | Maven or Gradle | Surefire / Gradle JUnit XML |
| Rust | `cargo test` | test output lines |

- **Tested end to end:** .NET (Tieto repo), Python and Node (sample repos with a planted break, caught both times). Go, Java/Kotlin and Rust: result readers tested on sample output, not yet run end to end on this machine.
- **AI involved?** No.
- **Code:** `vouch/runners.py`, `vouch/dotnet.py`, `guard()` in `vouch/review.py`. Try it: `python -m vouch.runners <repo> <base> <head>` (exit code 1 = regression).

## 3. Checkpoint: is the AI telling the truth?

- **In:** the diff, the issue text, the test results from step 2.
- **What the AI does:** writes a summary and a list of claims. Each claim = "these lines do X, this quote from the issue is why, this test proves it", plus a confidence number.
- **What code then checks, per claim:**
  1. **cite:** every cited line is a line this change actually added.
  2. **quote:** the quoted text appears word for word in the issue (spaces and markdown ignored, at least 8 characters).
  3. **tests exist:** every named test is declared in the change.
  4. **tests passed:** every named test passed on the agent's commit.
- **Verdict per claim:**
  - checks 1, 2 or 3 fail → **disputed** (red, stays open)
  - all pass, including 4 → **proven**
  - 1 to 3 pass but 4 does not → **unproven** (stays open)
- **Mutation proof (step 3b):** for every code line a *proven* claim cites, Vouch breaks the line on purpose
  (`>` → `>=`, `+` → `-`, `and` → `or`, a constant + 1; up to 3 per line, 12 per change) and runs the tests again.
  - a test now fails → the break was caught, the proof holds
  - every test still passes → the tests do not pin that line down → claim becomes **unproven**, line goes back on the reading list
  - skipped for .NET today (one suite run takes minutes); shown as "not run" in the review
- **The confidence number:** shown, crossed out, never used.
- **Code:** `check_claim()` and the loop after it in `vouch/review.py`; mutation proof in `vouch/mutate.py`.

## 4. Reading list: what must a person read?

- **Start:** every meaningful added line (not blank, not a lone bracket) is on the list.
- **Remove:** lines cited by a **proven** claim.
- **Generated files:** if most of them got the identical edit, that shared edit is proven by code. Any file whose edit differs goes back on the list.
- **Put back, always:** lines that hit a risk rule. They never fold, even if every test passes:
  - public API changes
  - analyzer warnings users will see
  - unsafe memory code
  - third-party package changes

  (The patterns for these rules are written for the Tieto repository today.)
- **Out:** lines to read, for example 225 changed → 6 to read.
- **Route:** regression → **blocked**. Any risk rule, missing step or no claims → **read everything**. Nothing left → **quick check**. Otherwise → **focused review**.
- **AI involved?** No.

## 5. EasyReview: the team reads it together

- **One step per screen:** Guardrail result, summary, each claim, each risk rule, unexplained lines, sign-off.
- **Each person votes per step:** looks right, ask, or problem.
- **Step status:** any "problem" → problem. Else any "looks right" → approved. Else open.
- **Ask:** the AI answers from that step's code only. Labelled "not evidence". It changes nothing.
- **Live:** who is on which step lives in Aiven Valkey (gone after 15 s). Every vote goes to Aiven Postgres and the Aiven Kafka topic `review.events`.

## 6. Sign-off: a named person accepts the risk

- **Accept is refused by code unless:**
  1. every step is approved by someone, **and**
  2. Guardrail found no regression, **and**
  3. the owner wrote the risk they accept, in one sentence.
- **Reject:** always allowed.
- **Out:** a permanent record in Aiven Postgres: who signed, when, and the risk they accepted.

---

## Known limit

Mutation proof shows a test **pins a line down**. It cannot show the test expects the **right** value:
if an agent writes a wrong function and a test that agrees with it (VAT added as 22% of the price instead of
price × 1.22), both are consistent and the change can still fold. The planted-bug benchmark measures exactly this.
