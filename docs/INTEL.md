# Intel (gathered 14 Nov 2026)

## The challenge
- Tieto challenge name: **"Earned Trust in AI Code"** (Junction 2026, challenge id 351).
- Official page needs login: https://hackjunction.app/participate/45/challenges/351 — paste it into `BRIEF.md`.
- Tieto's sample repo (public): https://github.com/te-industry-tech-office/junction26-messagepack-csharp
  - Fork of MessagePack-CSharp (.NET).
  - Agent-written branches to review: `ju26-issue-2129`, `ju26-issue-2234`, `ju26-issue-2283`, `ju26-issue-2297`
    - 2283: bug, crash on closed generic struct from referenced assembly
    - 2297: feature, `ExcludeFromCodeCoverage` on generated code (mostly generated files)
    - 2129: feature, formatters for types in a referenced assembly (adds public API → high risk)
    - 2234: bug, analyzer doesn't run with `SuppressSourceGeneration`
  - Requirement texts = upstream MessagePack-CSharp GitHub issues #2129, #2234, #2283, #2297.

## Inferred judging themes (from a competitor's write-up, confirm on the official page)
Risk · Hallucination · Transparency · Confidence · Quality · Who owns the decision · How it scales · What would make you not trust your own output.

## Competition
- 11 forks of the Tieto repo = at least ~11 teams.
- Only public tool repo: `JesseSaarinen/tieto-trust-review` (solo, TypeScript CLI, Claude + Gemini "breaker", line-level reading list, planted-bug measurement 21/22 caught, Markdown packs, **no UI, no DB, no user-feedback link**).
- Other active forks (code not inspected): nicholsss, ZeynelAbidin91, oliynykmax, miska-voutilainen.
- Private repos can't be seen by anyone, so "all possible names" searched: tieto junction, tieto-junction, junction2026, junction-2026, junction26, earned trust, messagepack junction, agent pr review.

## Inspiration
- Vector (devpost vector-l89mzu, xAI hackathon; reel by @vardy.mov): X complaints → embed + cluster → severity from count/likes/retweets → developer approves → agent clones repo in sandbox → PR with test/build/lint results. Stack: Flask, Next.js, Supabase, Grok.

## Aiven
- Tech challenge page (login): https://hackjunction.app/participate/45/tech-challenges/43 — paste into `AIVEN.md`.
- Free tier: PostgreSQL (pgvector), Kafka, Valkey, MySQL. Idle free services get powered off.
- MCP server: https://github.com/Aiven-Open/mcp-aiven
