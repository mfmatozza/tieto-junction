# Lanes × Vouch (approved by the Junction organiser: pitch it as the implement step)

**Lanes lets many people's AI agents write one codebase together. Vouch decides how much of what they wrote a human must read.** Lanes is our own tool (`~/Desktop/lanes`, Apache-2.0, private beta). Declare it in the submission as an existing open-source tool we built before the event.

## Level 1: we build Vouch with Lanes (30 min, do it now)

Each workstream in `WORKSTREAMS.md` = one teammate + one agent. Lanes stops their agents from overwriting each other.

```sh
cd ~/Desktop/lanes && npm ci && npm run build          # once
alias lanes="node ~/Desktop/lanes/dist/lanes.cjs"
cd ~/Desktop/Tieto-Junction
lanes init                                             # hooks into .claude/settings.json
lanes team on                                          # shared team context
lanes server                                           # on ONE laptop; note its LAN IP
lanes invite <name>                                    # per teammate → prints `lanes join <url> <token>`
lanes app                                              # live board: who edits what
```

Teammates run the `lanes join ...` line they got, then `lanes doctor`.
Only the Claude Code adapter is tested on the real agent. **Everyone uses Claude Code.**

## Level 2: Vouch reads Lanes provenance (the product feature)

Every Lanes checkpoint commit carries trailers:

```text
Lanes-Agent: claude-code (session 3f9a12bc)
Lanes-Task: fix closed generic struct crash
Lanes-Files: ...
Co-authored-by: ...
```

Vouch uses them in 3 places:

| Where | What Vouch does | Schema |
|---|---|---|
| Evidence pack | `git log` + `git blame` on the PR → each changed line gets **agent · human · task** | `pull_requests.contributors` |
| Trust ledger | Trust is earned per **code area × agent**. Claude can be 🟡 in source-generation while another agent is still 🔴 | `trust_ledger.agent` (part of the key) |
| Sign-off | The human who ran the agent ≠ the owner who signs. Vouch shows both | `signoffs.owner_name` + `contributors` |

No trailers (like Tieto's `ju26` branches)? Agent = `unknown`, so trust starts at 🔴. That is fail-closed, and it is correct.

`lanes pr` squashes one task's checkpoints into a PR with one `Co-authored-by` per contributor → that PR is what Vouch reviews.

## Level 3: the multiplayer demo moment (stretch, 1.5 h)

1. Two teammates, two Claude Code sessions, both with Lanes, both fixing parts of the same complaint cluster.
2. Lanes app shows both agents working, no collision.
3. `lanes pr --task "..."` → one PR, two contributors.
4. Vouch shows the claims split by agent, each with its own evidence and its own trust level.
5. Owner signs → only that agent's trust in that code area goes up.

Pitch: Lanes optimises the first half (backlog → parallel agent implementation, no collisions); Vouch the second half (review). Organiser approved using it (14 Nov). Declare it as pre-existing.

## Limits

- Lanes is beta; if the server is down, edits go ahead uncoordinated. Run the server on the most stable laptop and keep it awake.
- Provenance only exists for code written through Lanes. Vouch treats everything else as `unknown`.
