# Two-minute demo

## The hook

"An AI can write a pull request in seconds. The expensive part is deciding whether to trust it. Vouch turns that decision into evidence a human can sign."

## Click path

1. Open the review list. Four Tieto branches appear with different routes.
2. Open `ju26-issue-2283`. Show the requirement, changed lines, claims, passing tests, and the focused reading list.
3. Open `ju26-issue-2129`. Show that a new public API triggers a refusal and a full read even though the model is confident.
4. Open the evidence timeline. Point out PostgreSQL as the current state and Kafka as the event history.
5. Sign `2283` as the named owner. Write one residual risk.
6. Show the trust ledger: source generation earned focused review; analyzers remain full read.
7. End with the Vector connection: user feedback can be clustered into requirements, but no request reaches merge without proof and human accountability.

## If something breaks

- Aiven is unavailable: run the seeded local fixture and say the same schema is deployed on Aiven PostgreSQL.
- Model API is unavailable: use saved claims and show the deterministic citation/test checks.
- Time is short: demo only `2283` and `2129`. The contrast is enough.

