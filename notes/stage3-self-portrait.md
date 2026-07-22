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
