# The Read: constraints for the self-portrait agent

Written during Stage 1, to be consumed by Stage 3. These are not
suggestions. Each one exists because the demo corpus produced a finding
that a naive prompt would have gotten wrong in a specific, nameable way.

The deterministic signal computation is the easy half. This file is about
the half that decides whether the page lands.

---

## The opening vignette

The page opens on one finding, and it is this one.

**Reply latency does not track importance or affection. It tracks how
answerable a question is. But the questions that go unanswered longest are
the easiest ones to answer. So the real split is not easy versus hard, it
is easy to answer versus easy to face.**

Evidence in the demo corpus, from three independent arcs:

| Context | Reply |
|---|---|
| Rosalind, surgery-day crisis | 17 min |
| Marguerite, easy logistics | 42 min |
| Marguerite, "is anyone paying you yet" | 35-61 h |
| Wendy, "are you bringing someone" | 4.2 days |
| Nkechi, "what if the seed doesn't close" | never |

Three separate relationships, three separate question types, same
behavior. That is what makes it structural rather than a lucky pattern in
one thread, and it is why it earns the opening slot.

Everything else on the page is second.

---

## The second vignette: the deferral

Found during Stage 1 verification, while checking whether Dane's June
questions were a third instance of the dropped-question pattern. They were
not. They are the first instance of something stronger.

**She does not ignore hard questions. She defers them. "This week" is how
she says no without saying no.**

Thirteen distinct deferral messages across nine relationships in ninety
days. The ones whose outcome is visible in the corpus are almost all
unkept:

| Deferral | What happened |
|---|---|
| Josiah: "Let me think about the right framing, give me a few days" | never |
| Wendy: "I'll venmo you this week" | Wendy, later: "Never got the venmo" |
| Wendy: "Let me look at the calendar this week" | never |
| Nkechi: "Let me look at next week and send some times" | never |
| Dane: "will ping her this week" | does not |
| Marguerite: "I'll have a real answer after that conversation" | Marguerite: "you have now told me twice" |

Why this earns the second slot, directly after the headline:

It composes with the headline instead of competing. The headline is *what*
gets avoided, questions that are easy to answer and hard to face. This is
*how*. The reader gets the pattern and then immediately gets the
mechanism, which is a better sequence than two unrelated observations.

It is deterministic. A regex over outgoing messages for forward-commitment
phrases ("let me look", "I'll send", "this week", "next week", "give me a
few days"), then a check for whether the promised action appears in any
later message. No inference, no LLM judgment about intent.

And it is corroborated inside the data. Marguerite names the behavior
out loud in June. When a finding about the user is independently observed
by someone in their own inbox, the agent can quote them rather than
assert. That quote is the single most quotable line the corpus produces
and it should be a share-card candidate.

Implementation note: count distinct deferral *messages*, not phrase
matches. One message often contains two phrases ("I'll venmo you this
week") and counting matches inflates the number by roughly 60%.

---

## Working discipline: generalize at the first success

**When a mechanism is built for one instance in a class, extend it to all
instances in the class before proceeding.**

The trigger is finishing the first working application, not noticing the
pattern repeat. This is distinct from "read the handoff before writing the
code", which prevents a different failure. That one is about not knowing.
This one is about knowing and stopping too early.

What it cost here: durations-in-multiple-units was built and verified for
the latency vignette, then seven more vignette templates were written
without it. The next run produced converted durations in four of them and
one outright fabricated timeframe ("eleven months" for eighteen days).
Every one of those was preventable at the moment the first template
worked.

The class is whatever shares the shape: agents, prompt templates, vignette
types, share-card variants, signal extractors. When a fix lands in one,
enumerate the rest and apply it. The generalization pass is part of
shipping the first case, not a follow-up.

---

## Hard constraint 1: context class

**A latency finding must name the class of message it describes, and may
not generalize across classes without explicit warrant in the data.**

This kills three wrong findings at once, all wrong for the same reason:

- "She's always fast with customers." Rosalind's *median* is 2.2 days.
  The 17 minutes was one crisis.
- "She's slow with investors." Marguerite got 42 minutes on the close and
  61 hours on the metrics question. Same person, 90x spread, and the
  variable is the question.
- "She cooled on the candidate." See constraint 2.

The agent gets aggregate numbers per person. It will want to say "you
reply to X in N." That sentence is usually false. The honest version names
the context: *"a surgery-day emergency gets seventeen minutes. The
question about whether anyone is paying gets sixty-one hours."*

Implementation: pass latency broken out by context class, not as a single
per-person median. If a class has fewer than three samples, the agent may
report the instance but not call it a pattern.

---

## Hard constraint 2: who moved first

**When the user's behavior changes before the counterparty's, the finding
must say so.**

The Nkechi arc reads, to the person living it, as a candidate going cold.
The data says otherwise. Priya's replies run 2.6d/80 words, 3.6d/48,
6.6d/18 — monotonic in both latency and length — and Nkechi's gaps only
start lengthening after Priya's do. The candidate did not cool. She
matched what she was getting.

This is the same reframe as the Rosalind observation, and it is the move
that separates this page from a stats dashboard. "You are overwhelmed" is
a description. "You chose, and you did it first" is an observation. The
second one is the one someone screenshots.

Implementation: for any relationship showing a frequency or latency
decline, compute both sides' trend lines and compare inflection points. If
the user's inflects earlier, the finding names the user as the mover. If
the counterparty's does, it says that instead. If they are simultaneous or
noisy, it says neither.

---

## Hard constraint 3: incident versus habit

**One occurrence is an incident. Two or more independent occurrences is a
habit. Only habits may be stated as characterizations.**

The dropped-third-question pattern appears in Marguerite's threads and
Nkechi's threads independently: a numbered or multi-part question where
the last part is the one that matters, answered on every part except that
one. Two unrelated relationships, same signature.

That is what makes it worth a vignette of its own. A single instance would
be an anecdote about one email.

Implementation: the agent may only use verbs like "you tend to", "you
always", "your habit is" when the underlying signal has two or more
independent sources. With one source it must describe the instance
concretely and stop.

---

## Hard constraint 4: no interpretation

**The agent states behavior and stops. It does not say what the behavior
means about the person.**

Anything that would follow the words "which suggests" is not a finding and
must not be written. Same for "which says something about", "revealing
that", "a sign that", "because you", and any sentence explaining the
user's motive or emotional state.

> Finding: "You answered the question about the radio. You did not answer
> the one about whether to set you a place."
>
> Not a finding: "...which suggests you're avoiding commitments that feel
> like obligations."

This is the constraint most likely to be violated, because drawing the
conclusion is precisely what a summarizing model wants to do, and the
interpretation always sounds more insightful than the observation in
isolation. It is not. The observation is the thing the reader recognizes
themselves in. The interpretation is the thing that makes them close the
tab, because it is a stranger telling them who they are on evidence they
can already see for themselves.

The reader does the interpreting. That is what makes it land, and it is
the entire difference between a page someone screenshots and a page that
reads like an assessment.

Enforcement: put the banned phrases in the prompt as a literal list, the
same way the v2 plan bans "reached out" and "touched base" for the
per-person agents. Concrete bans work. "Be observational" does not.

---

## Voice rule, carried from the v2 plan

**Blunt, in the observer's voice, never the second-person verdict.**

> "The reply gap between Dana and your sister is 500x" is a screenshot.
> "You prioritize Dana over your sister" is a therapist bill.

Go as blunt as the data supports. The discomfort is the insight, and
softening it turns the finding back into a stat tile with more words. But
the bluntness sits in what is observed, never in what it is claimed to
mean about the person.

---

## What to watch for once the volume threads land

A third independent instance of the dropped-third-question pattern would
strengthen constraint 3's example considerably. Dane's June standup traffic
has Priya deflecting the hiring question twice, which may or may not
qualify: it is a deflection rather than an omission, and the distinction
matters. Check before counting it.

---
---

# Stage 3 close: what shipped, and what to watch

Everything above was written during Stage 1, before the code existed.
Everything below was written at the close of Stage 3, after it did.

## What shipped

`backend/agents/self_portrait.py` computes ten signal families. It writes
no prose and derives no conclusions.

`backend/agents/phrasing.py` supplies every figure in every form a writer
might reach for. It exists because prohibiting conversion failed twice.

`backend/agents/read_composer.py` runs candidates and selects the page.

`SELF_PORTRAIT_SYSTEM` plus `SELF_PORTRAIT_ESCAPE` in templates, and eight
per-vignette user templates.

`TheReadView` in the frontend: single column, opening vignette large with
no lede, no stat tiles anywhere.

On the demo corpus: 12 candidates considered, 6 kept, 0 skipped, 6
distinct finding types.

## Two composer principles, now proven rather than conjectured

**1. Outliers game interestingness metrics.**

Callum's latency spread is 4825x, which ranked him the most interesting
person in the inbox. It comes from one 26-day invoice thread against an
8-minute Figma acknowledgement, sitting on a median of 2.6 hours. Wendy's
median is 88 hours. Ranking by median put Wendy first and Callum out.

When ranking candidates for slot allocation, prefer metrics describing the
sustained character of a relationship over metrics dominated by extremes.
Extremes are what make a vignette worth reading. They are not what should
decide which vignettes exist.

**2. Rare findings beat common ones for slot allocation.**

Cooling fires once in the corpus, behind tight gates. Latency contrast
fires for six of thirteen people. Both wanted Nkechi's evidence key, and
whichever got there first locked the other out. The common one arriving
first would have cost the page its scarcest finding.

When two findings compete for the same person, the rarer one wins. This is
what makes The Read feel bespoke: different inboxes surface different
rarities, rather than the same handful of flavours reordered.

**Corollary found the hard way:** evidence-level dedupe is not enough on
its own. The first composer run kept four latency vignettes about four
different people. Every one passed dedupe, and the page made the same
observation four times with different names in it. Per-kind caps are what
prevent the template failure from wearing a disguise.

## Known limitation: interpretation residue

Constraint 4 was attacked four times: a banned phrase list, a structural
rule on sentence content, a ban on case-building, and a rule about the
closing sentence. Each fix relocated the behaviour rather than removing
it. The model has a strong prior toward concluding.

The shipped page is clean, but **it is clean partly by accident.** The two
vignettes carrying the worst residue, `length` ("the length tracks the
person, not the day") and `signoff` ("which makes it a template"), were
not selected by the composer on this corpus. Composition removed them, not
the prompt.

**Trigger condition:** if `length` or `signoff` is ever selected on a real
inbox, read the closing sentence specifically. If the interpretation leak
shows up there, that is the signal to build the detector: a check over
vignette bodies for generalising sentences, defined as present-tense
claims containing no proper noun, number, or quotation. Not worth building
speculatively; worth building the moment it is observed in the wild.

## Guard measurement is only as good as its normaliser

A full pipeline run flagged twelve story quotes as ungrounded. Five were
the model quoting accurately and adding a full stop the source did not
have. One was the model rendering the source's double quotes as single.

Both were normaliser gaps, not hallucinations, and they inflated the
measured rate by roughly half. Since this log is meant to be the
hallucination metric on real inboxes, a false-positive class that large
makes the metric useless. The normaliser now folds terminal punctuation
and inner quote marks. Real fabrications still fail: an evidence quote
saying "she was one incident away from being done with us" against a
source saying "one incident away from going back to paper" is still
caught.

Lesson worth carrying: when a guard produces a rate, audit the rate before
trusting it. A guard that over-reports is worse than no guard, because it
trains you to ignore it.

## Three bugs found in the precompute layer

Moving work out of the prompt moves the correctness burden into code, and
the code was wrong three times: `.0f` rounding turned 2.6 days into "3
days", `f"{n} weeks"` produced "1 weeks", and floor division turned a
90-day window into "about 12 weeks" when it is 12.9.

That last one is the instructive one. It surfaced as a model defect and
was not one. The model printed "over twelve weeks" because that is what it
was handed. Before blaming the model for a wrong figure, check what the
figure was when it left the code.
