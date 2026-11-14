# From Vector to Vouch

Vector (Devpost `vector-l89mzu`, xAI hackathon winner; reel by @vardy.mov): public complaints on X → embed + cluster → severity from count/likes/retweets → developer approves → agent clones the repo in a sandbox → PR with test/build/lint results. Stack: Flask, Next.js, Supabase, Grok.

## What we keep, 1:1

| Vector | Vouch |
|---|---|
| Complaints on X | MessagePack GitHub issues + comments, plus a live "post a complaint" box |
| Embed + cluster | fastembed + **Aiven pgvector** |
| Severity = count + likes + retweets | Severity = reports + 👍 reactions + comments |
| Cluster board you can click | Same: the cluster board is the dashboard's first screen |
| Agent writes the fix in a sandbox | Tieto's agent-written `ju26` branches (live agent = stretch) |
| PR with test/build/lint results | Evidence pack: tests run in a git worktree, results per claim |
| Supabase | Aiven PostgreSQL + Kafka |

## What we add (the Tieto part)

```text
Vector: feedback -> cluster -> code -> tests -> pull request
Vouch:  feedback -> cluster -> code -> EVIDENCE -> RISK ROUTE -> HUMAN SIGN-OFF -> TRUST LEVEL
```

1. Claims must quote the requirement or a real user, and cite real lines. Code checks this.
2. Route by what can break, not by size.
3. A named human signs the residual risk.
4. Trust per code area: 🔴 full read → 🟡 focused read → 🟢 light check. Earned with clean sign-offs, lost on one escaped bug.
5. Closed loop: after a fix merges, does the cluster go quiet?

## What we will not copy

No code or text from Vector or from other Junction teams, no competitor numbers, no auto-merge, no "AI score = safe".
