# Working brief: Tieto challenge

This is the implementation brief for the project currently called **Vouch**.

## What we know

- Challenge URL: https://hackjunction.app/participate/45/challenges/351
- Working title: **Earned Trust in AI Code**.
- Tieto provides a public MessagePack for C# repository with four agent-written branches:
  - `ju26-issue-2129`
  - `ju26-issue-2234`
  - `ju26-issue-2283`
  - `ju26-issue-2297`
- The useful evaluation shape is not "did an AI write code?" It is "can a human decide what to trust, with evidence?"

The challenge page is currently unavailable to unauthenticated HTTP requests from this environment. Treat this file as a working brief, and paste the exact logged-in page text here before final submission so the wording and required fields can be checked line by line.

## Working interpretation of the judging criteria

These are the criteria Vouch must visibly answer in the demo:

1. **Risk** - review depth follows what the change can break, not just lines changed.
2. **Hallucination** - AI claims must cite real diff lines and real requirement text; code checks the citations.
3. **Transparency** - every claim says whether it was proved by a test, static rule, second model, or not checked.
4. **Confidence** - model confidence is displayed but never releases code by itself.
5. **Quality** - detect weakened tests, empty assertions, scope creep, and generated-code drift.
6. **Human accountability** - a named owner signs the residual risk and acknowledges refusals.
7. **Scale** - show reading load, review time, cost, and trust per code area.
8. **Failure behavior** - missing model output, broken tests, or missing evidence routes to a full read.

## Demo proof

Use the four supplied branches as four deliberately different cases:

| Branch | Story | Expected Vouch behavior |
| --- | --- | --- |
| `ju26-issue-2283` | Bug fix in a closed generic struct from a referenced assembly | Focused read if tests and claims hold |
| `ju26-issue-2297` | Generated-code coverage attribute | Static checks can release generated files |
| `ju26-issue-2129` | New public API and analyzer rules | Refuse to auto-release; full read |
| `ju26-issue-2234` | Analyzer behavior under `SuppressSourceGeneration` | Fail closed when test evidence is unavailable |

The pitch should show the same tool making different decisions for these four changes. That is the product: not blind automation, but earned autonomy.

## Boundary

Vouch is inspired by the public Vector project, but it is not a copy. Vector collects user feedback and drives an AI coding pipeline. Vouch keeps that feedback-to-change spine and adds an evidence ledger, risk routing, human sign-off, and a trust history for AI-generated code.

