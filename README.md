# Vouch

**AI agents write pull requests faster than humans can read them. Vouch makes every agent-written PR earn its trust.**

Junction 2026 · Tieto challenge "Earned Trust in AI Code" · Aiven tech challenge.

1. **Listen** — real user feedback is clustered (Aiven Postgres + pgvector) into requirements with the users' own words.
2. **Prove** — the AI explains its change as claims. Code, not AI, checks every citation and runs the tests.
3. **Route** — risk comes from what can break (public API, wire format, untrusted input), not from size.
4. **Sign** — a named human accepts the residual risk. Every step is an event on Aiven Kafka.
5. **Earn** — each code area has a trust level that rises with clean merges and drops on any escaped bug.

> The AI's confidence is displayed and ignored. Only verified evidence changes what a human must read.

Status: planning. See `PLAN.md`.
