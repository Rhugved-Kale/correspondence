# Stage 1 handoff: the demo corpus

What Stage 1 produced, what Stage 2 needs from it, and the decisions that
are settled so they don't get relitigated.

Closed. 406 messages, 68 threads, 22 contacts, 85 calendar events.
`python -m demo.verify` passes 19/19.

---

## Working with it

```
python -m demo.load --db data/demo.db --fresh   # corpus -> SQLite
python -m demo.verify                            # assert the planted findings
python -m demo.generate --plan                   # what would regenerate
```

The loader writes messages and calendar events and nothing else. Contact
aggregates come from `ingest._rebuild_contacts_from_cache`, the same
function a real Gmail run calls. If the fixture computed its own contact
stats we would be testing the fixture instead of the pipeline.

This is also what makes Stage 2 cheap: a full pipeline run against the
fixture takes seconds instead of the twenty minutes a real inbox needs,
and it costs no Gmail quota. Iterating prompts against real private email
was the thing making v1 iteration expensive.

---

## What Stage 2 gets

**An evaluation set with known-good targets.** Twelve threads are
hand-written and carry the findings. When a prompt change lands, these are
the pages to read, because we already know what a good output says about
them:

| Thread | What a good agent should find |
|---|---|
| `theo-billing-argument` | Conflict, three weeks of silence, a non-apology that works |
| `theo-services-revenue` | The relationship changed shape. She argues as a peer now |
| `rosalind-double-booking` | A near-quit with a real turn. Bramble, in passing |
| `wendy-birthday` | Four asks, one answered, ends unanswered |
| `josiah-intro-ask` | A promise with a quotable sentence, never kept |
| `nkechi-equity-runway` | The user cooled first |
| `marguerite-metrics` | Long replies that answer two of three questions |

**A voice-quality bar.** Generated threads inherited the anchors' texture
through few-shot, so the corpus reads consistently. If a prompt change
makes output read like a competent summary, the corpus is not the reason.

**Known-good numbers**, all in `demo/verify.py`, so a regression is
visible rather than suspected.

---

## Settled decisions

**Landing person is Wendy, via `demo/config.json`.** The wiki opens on
whoever ranks first, which is Callum at 3.38 against Dane's 3.37, a gap
inside noise. Landing a cold visitor on Figma links and an invoice thread
is a demo failure, not a ranker failure, so it was fixed in presentation.
The ranker was not touched and neither was the corpus.

**The ranking order is not a target.** Spec ranks in `contacts.json` were
predictions, not requirements. Where the ranker disagrees it is usually
right, and the disagreements are informative:

- Wendy landed at exactly her predicted 7.
- Theo landed at 8 against a predicted 4, because he is the only featured
  person with zero meetings. That is correct. He is an informal advisor
  she emails, not someone she books.
- Beatriz entered the top ten from the noise list on 13 meetings alone,
  with the lowest reciprocity and volume in the ten. She is riding the
  calendar signal.
- Hana landed at 11 with the highest recency in the table and could not
  crack the ten, because reciprocity correctly dominates. That was the
  designed test and it passed.

A proposal to add Wendy and Theo threads was rejected. It was motivated
reasoning: the rank looked wrong, and a world-realism justification got
reached for afterward. Padding data to move a rank is the failure mode
the corpus exists to avoid.

**The About agent is skipped on demo runs**, with authored blocks from
`demo/about_blocks.json` injected instead. Fictional people have no web
presence, so the agent would correctly return empty for all ten. The
authored blocks match the agent's schema, caps, and completeness
distribution: two full, three partial, two thin, three empty.

---

## Known properties, not bugs

**Recency decays against real `now`, not `demo_as_of`.** Harmless for the
shipped demo, which bakes prebuilt JSON at build time. Anyone re-running
the pipeline against the fixture a year out gets uniformly decayed
recency. Worth a README line.

**Message-count reciprocity penalizes burst senders.** Dane's 71 inbound
against 29 replies scores 0.65 while Callum's 23 against 16 scores 1.11,
because Dane sends three messages in ninety seconds. Thread-level
reciprocity would be more robust. Real finding about the ranker, out of
v2 scope, worth its own task later.

**Send-hour clustering at 11:00 and 14:00.** 41 of 91 outgoing messages
sit in those two hours, a generation artifact. Invisible in the artifact
today, but it matters if Stage 3 renders an hour-of-day sparkline, because
two spikes would look synthetic. Either jitter at load time or do not
visualize that dimension.

---

## The findings, for Stage 3

Full detail in `notes/stage3-self-portrait.md`. The short version:

1. **Latency tracks how answerable a question is, not who asked.** But the
   longest-unanswered questions are the easiest to answer. Easy to answer
   versus easy to face. Three independent arcs. This is the opening
   vignette.
2. **She defers rather than declines.** 13 deferral messages across 9
   relationships. "This week" is how she says no without saying no.
   Marguerite names it out loud in June, so it is corroborated inside the
   data rather than inferred.
3. Four hard constraints on the self-portrait agent, each written because
   the corpus produced a finding a naive prompt would state wrongly.
