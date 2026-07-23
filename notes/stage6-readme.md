# Stage 6 handoff: the README

Written at the close of Stage 3. The current README is v1's, lightly
scrubbed in Stage 0. It describes an app that no longer exists.

## What is now wrong in it

It documents an "About you" surface of aggregate stats. That surface is
gone and The Read replaced it.

It says nothing about the demo, which by then will be the main way anyone
sees the project.

The trade-offs section predates the grounding layer, the precompute
discipline, and the composer. Those are the most interesting engineering
decisions in the repo and none of them are mentioned.

## What to say

The three durable rules, each of which cost something to learn:

  Any fact derivable from data is precomputed and handed to the model,
  never requested as output. Fabricated quotes, wrong word counts and
  wrong date arithmetic were all the same defect.

  Structural rules beat example lists. A ban on a phrasing gets routed
  around; a rule about grammatical structure does not.

  A guard that over-reports is worse than no guard. The normaliser
  inflated the measured hallucination rate by roughly two thirds before it
  folded terminal punctuation and quote marks.

Also worth a line: recency decays against real `now`, so re-running the
pipeline against the fixture long after 2026-06-30 gives a uniformly
decayed ranking signal. Harmless for the deployed demo, which bakes JSON
at build time.

## Voice

Direct, not corporate. No em-dashes. No "seamless", "robust", "elegant".
Occasional dry humour. Match the existing comments, which are the best
guide to the register.
