# Vouch demo video: 2:00 total

**Format:** 1920×1080. You on camera for the opening and the close; screen recording in between with your voice over it.
**Your face clips:** slots A and B. Record them on their own; the screen part is already cut.
**Your voice over the screen:** read each screen line at a calm pace. Every block has a time budget; the screen clip is already that long.
**Timing rule:** 2:00 hard limit. Each block below is timed at ~2.6 words per second.

---

## A · FACE · 0:00 to 0:12 (12 s)

> AI agents now write thousands of lines a day. Nobody can review that. So teams either slow the AI down, or merge code no one has read. We built a third option.

## 1 · SCREEN · Landing hero · 0:12 to 0:20 (8 s)

> This is Vouch. Agents write. Vouch proves. Humans sign.

## 2 · SCREEN · Lanes, live collision · 0:20 to 0:38 (18 s)

> It starts before any code exists. With Lanes, built in house, every agent takes a lease on a file before it edits. Here two Claude Code agents plan the same files at the same second. One holds the lease, the other waits, then builds on top. No conflicting branches.

## 3 · SCREEN · Run Vouch on the pull requests · 0:38 to 0:52 (14 s)

> Each change becomes a pull request, and Vouch knows which agent wrote it. One click runs Vouch: a worker fed by Aiven Kafka runs your existing tests before and after.

## 4 · SCREEN · GitHub: blocked · 0:52 to 1:00 (8 s)

> If anything that used to work breaks, the pull request is blocked on GitHub before a person looks.

## 5 · SCREEN · EasyReview · 1:00 to 1:24 (24 s)

> Otherwise the AI explains the change as claims, and plain code checks every one: the lines exist, the quote is in the issue, the test passed. Then Vouch breaks the code on purpose. Here one break went unnoticed, so that line goes back to a person. The team reviews what's left, together, live.

## 6 · SCREEN · Sign and merge · 1:24 to 1:36 (12 s: 8 s sign + 4 s GitHub)

> A named owner signs and writes down the risk. Vouch posts the review record and merges on GitHub, under their name.

## 7 · SCREEN · Results · 1:36 to 1:48 (12 s)

> On Tieto's repository: 76 percent fewer lines to read, every existing test kept. We planted ten bugs in our demo repo: Vouch stopped all ten. Three blocked, seven put in front of a person.

## B · FACE · 1:48 to 2:00 (12 s)

> AI writes the code. Vouch makes sure a human can stand behind it. Built on Lanes, Claude and Aiven.

---

Subtitles: once your clips are in, the whole voice track gets transcribed and burned in as captions.

---

## What is on screen (all real, recorded from the live product)

| Block | Recording |
|---|---|
| Lanes | Lanes' own board during a real run of two Claude Code agents on vouch-demo: planned files, then "lease: bea" |
| Run | The repository page: Run Vouch on PR #4 (written by claude-code through Lanes), 90 s of real time sped up and labelled |
| GitHub | PR #2 on GitHub: "vouch/review: Blocked: 1 existing test(s) broke" |
| Review | PR #5: the claim mutation proof rejected ("Breaking pricing.py line 15 ... did not make any test fail"), a second reviewer live |
| Sign + Merged | PR #4 signed in Vouch, squash-merged on GitHub with the review record |
| Results | Landing page results and the planted-bug benchmark (7/10, 8/10, 10/10) |
