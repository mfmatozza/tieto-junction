# Two-minute demo

## Hook (10 s)

"AI agents now write a thousand lines in minutes. Nobody can review a thousand lines. So either we stop using the AI, or we merge things nobody read. Vouch is the third option."

## Click path

1. **Backlog**: ranked issues from real users. Click #2283 → the agent's PR.
2. **Guard** (first screen of the tour): "Blast radius: N callers, M existing tests, M/M still pass." Nothing that worked before is broken, proved before anyone reads.
3. **Review Tour**: "Changed 228 lines · You read N · ~4 min." Press → . Each step animates in: claim, code, evidence. Proven code folds away. Unproven lines stay open.
4. Hit a **red step**: the AI quoted something that isn't in the issue. Caught by code, not by AI.
5. **Collaborative**: a second laptop joins. Its avatar appears on step 3, takes the analyzer part, approves. Ask ❓ on one line → AI answers, marked "not evidence".
6. **PR 2129**: new public API → the step can't fold, red frame, needs an explicit ✅ from a human.
7. **Sign**: owner writes the accepted risk → trust for this area × agent moves 🔴 → 🟡.
8. Close: "From backlog to merge, nothing broken, every line either proven or read by a person, in minutes, together."

## If something breaks

- Aiven down: local fixture, same schema.
- Model API down: saved claims; guard, checks and tour are deterministic.
- Short on time: steps 2, 3, 5, 7.
