# Aiven: what we use and why

Tech challenge: https://hackjunction.app/participate/45/tech-challenges/43 (paste the logged-in text at the bottom of this file).

## Final infra list

| Need? | Service | Job in Vouch |
|---|---|---|
| ✅ must | **Aiven for PostgreSQL** (+ `pgvector` extension) | System of record: feedback, embeddings, clusters, requirements, PRs, claims, evidence, sign-offs, trust ledger. Clustering = pgvector cosine search. |
| ✅ must | **Aiven for Apache Kafka** | Live event spine. The dashboard's "live feed" reads it. This is the Vector-style "watch the pipeline move" moment, and the audit trail. |
| 🟡 nice | **Aiven for Valkey** | Job queue for review/agent runs (one review at a time per branch), embedding cache. Cut if short on time: Postgres `SELECT ... FOR UPDATE SKIP LOCKED` does the same. |
| ❌ skip | Aiven for OpenSearch | Postgres full-text search covers the demo. Add only if everything else is done. |
| 🟡 nice | **Aiven MCP server** (`Aiven-Open/mcp-aiven`) | Judge asks Claude "why is 2129 a full read?" → answer read from the ledger. 15-minute add-on at the end. |

## Kafka topics (free tier allows 5, we use 4)

```text
feedback.received     a new complaint/issue came in
feedback.clustered    it joined a cluster, severity changed
review.events         review.started / claim.checked / review.routed (type field inside)
trust.events          owner.signed / trust.updated / bug.escaped
```

## Gotchas

- Free services **power off when idle**. Open the console and wake them 30 min before judging.
- Kafka uses SASL/SSL: you need user, password and the CA cert (`AIVEN_KAFKA_CA_PEM` = path to `ca.pem`).
- Enable pgvector once: `CREATE EXTENSION vector;` (already in `db/schema.sql`).

## Minimum credible Aiven demo

1. A complaint posted live → `feedback.received` on Kafka → row + embedding in Postgres → joins a cluster.
2. A review run writes claims/evidence to Postgres and events to Kafka.
3. Owner signs → `trust.events` → trust level changes on screen.

## Official brief (paste below)
