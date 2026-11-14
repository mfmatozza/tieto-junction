# Aiven implementation map

Tech challenge URL: https://hackjunction.app/participate/45/tech-challenges/43

The exact logged-in brief should be pasted here before submission. The implementation below uses Aiven as a real part of the product, not as a logo in the README.

## Service plan

### 1. Aiven for PostgreSQL + pgvector

The system of record:

- projects, requirements, pull requests, changed lines, and claims;
- evidence checks and owner sign-offs;
- trust ledger per repository/code area;
- embeddings for clustering repeated user feedback.

Use standard PostgreSQL drivers and `pgvector` so the app stays portable.

### 2. Aiven for Apache Kafka

The append-only event spine:

```text
feedback.received
feedback.clustered
review.started
claim.checked
review.routed
owner.signed
trust.updated
```

The dashboard reads the current state from PostgreSQL; Kafka preserves how the state was reached and makes the event flow easy to show live.

### 3. Aiven for OpenSearch (stretch goal)

Search all evidence, requirements, and feedback in one place. This is useful if time remains, but it must not delay the PostgreSQL + Kafka demo.

### 4. Aiven AI tools (stretch goal)

- AI Gateway: one model endpoint if the event account exposes it.
- Managed Agents or Aiven MCP: a judge can ask, "Why is branch 2129 a full read?" and receive an answer grounded in the ledger.

## Minimum credible Aiven demo

1. Create an Aiven PostgreSQL service and run the schema.
2. Store one evidence pack and one signed decision.
3. Publish the review lifecycle to an Aiven Kafka topic.
4. Refresh the UI from PostgreSQL and show the Kafka event count.
5. Keep credentials in `.env`, never in git.

## Environment variables

```text
AIVEN_PG_URL=
AIVEN_KAFKA_BOOTSTRAP=
AIVEN_KAFKA_USER=
AIVEN_KAFKA_PASSWORD=
AIVEN_KAFKA_CA_PEM=
AIVEN_OPENSEARCH_URL=
AIVEN_OPENSEARCH_USER=
AIVEN_OPENSEARCH_PASSWORD=
```

