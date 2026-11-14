# Two-minute demo

## Hook (10 s)

"AI agents now write pull requests in seconds. The hard part was never writing the code. It's deciding whether to trust it. Vouch makes the AI earn that."

## Click path

1. **Cluster board**. Type a complaint live → it lands in the "closed generic struct crash" cluster, severity goes up, Kafka feed ticks.
2. Open the cluster → its requirement (#2283) → the agent-written PR.
3. **PR 2283**: claims, each tagged 🧪/📏/🤖/⚪. A claim with a fake quote is red. Reading list: the human reads only the lines without proof.
4. **PR 2129**: AI confidence 95%, greyed out, "not used". New public API → refused → full read.
5. **Sign 2283** as the named owner, write one residual risk → trust level of `source-generation` moves 🔴 → 🟡.
6. **Audit**: planted bugs, caught X of Y. One escape → area drops back to 🔴.
7. Close: "Every line of AI code traces back to a real user and forward to a named human."

## If something breaks

- Aiven down: run on the local fixture, say the same schema runs on Aiven.
- Model API down: show saved claims; citation and test checks are deterministic.
- Short on time: show only steps 1, 3, 4, 5.
