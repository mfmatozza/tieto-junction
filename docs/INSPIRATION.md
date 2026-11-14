# From Vector to Vouch

## What we are borrowing

The Devpost project **Vector** is an AI-powered feedback-to-code pipeline. It collects public feedback, clusters similar requests, prioritizes them, creates an issue, generates a plan and tests, writes the change, runs verification, and opens a pull request.

The Instagram reel linked with the brief is a short post-hackathon update from Vardhan Agnihotri about winning the xAI hackathon with Vector. It reinforces the useful product lesson: the workflow is easy to understand when shown as a visible pipeline.

## What Vouch changes

```text
Vector: feedback -> cluster -> code -> tests -> pull request
Vouch:  feedback -> requirement -> AI change -> evidence -> human sign-off -> trust history
```

The input can still be a GitHub issue, chat message, or user complaint. The key change is the output: Vouch does not pretend that a model's confidence is approval. It produces a small, inspectable decision pack.

## Why this fits Tieto

Tieto's supplied branches create a perfect demo because they vary in risk:

- a bug fix can earn a focused read;
- generated files can be released by deterministic checks;
- a public API or analyzer contract must stay on a human's full-read list;
- unavailable test evidence must fail closed.

That gives the judges a visible answer to the core question: **when should an AI-generated change be trusted, and who makes the final call?**

## What we will not copy

- no copied code from Vector;
- no copied wording or implementation from public Tieto projects;
- no claim that an AI score is a safety guarantee;
- no automatic merge in the demo.

