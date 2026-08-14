# Stage 4 handoff: the Share Card

Written at the close of Stage 3, before any Stage 4 code exists. It says
what the card is for and what Stage 3 changed about the plan, so the
build starts from the reasoning rather than rediscovering it.

Writing this file is itself a correction. Stage 3 had a forward handoff
written during Stage 1; Stages 4, 5 and 6 did not, and the gap was found
only when someone went looking for a note that was never written. Forward
notes for 5 and 6 exist now for the same reason.

---

## What the card is for

The reviewer feedback the whole rebuild answers: does the artifact pull
someone in enough that they want to keep using it and send it to a friend.
The card is the only surface that actually travels. Everything else is
seen by someone who already arrived.

One consequence: the card is not a summary. The v1 card had a header band,
a stats band, a story, a prep hook and a footer. Five sections is a page.
The card carries **one** thing.

---

## What Stage 3 changed

### 1. The composer already decides what is worth saying

The original plan had the card cycling three types with a shuffle button:
a story pull-quote, an email fragment, a finding from The Read. That
predates the composer, which now ranks candidates with warrant gates,
per-kind caps and evidence dedupe.

A shuffle that picks at random would be a worse selector than the one
already built. **The card renders the highest-priority vignette the
composer kept, and shuffle walks down that same ranked list.** Same
ordering, different surface.

### 2. The card needs an escape clause

The Read degrades gracefully: four vignettes instead of six, page reads
shorter, nobody notices. A card cannot. It is one canvas with one quote
on it, so a weak finding is visible as a weak card.

The card must be able to decline to exist. If nothing clears warrant,
offer no card rather than a card about nothing. This was not in the
original plan and it is the direct analogue of the vignette escape
clause, which returns `null` rather than manufacturing a distinction.

### 3. Two proven composer principles carry over

**Outliers game interestingness metrics.** The plan said the quote picker
selects candidates under a character threshold. That is a length filter
wearing a quality filter's clothes, and it is the same shape as the bug
that ranked Callum first at 4825x on one 26-day invoice thread. Selection
prefers quotes from high-priority vignettes; length is a hard constraint
on what fits the canvas, never a proxy for what deserves to be on it.

**Rare findings beat common ones.** Latency contrast fires for six of
thirteen people; cooling fires for one. On a page, a common finding is
merely unremarkable. On a card, it is the difference between an artifact
that looks bespoke and one that looks generated, and the card is the thing
that travels. Rarity wins the slot.

### 4. The primary card is self-portrait, and anonymisation is now a real decision

Agreed during planning on exposure grounds: a person card publishes a
colleague's name, their job, and a note that you owe them an email, which
caps how often anyone shares one. Stage 3 strengthens this on quality
grounds too. "You slowed down first, then she did" and "Let me check and
I'll ping you" are both strong and expose nobody.

But the single best vignette in the corpus is the Wendy one, and it names
a sister. So the open question Stage 4 has to answer, which the original
plan never raised:

**Does the card anonymise counterparties?** "your sister", "a candidate
you were hiring", "your co-founder". Three options: never name anyone;
name only when the finding collapses without it; let the user choose per
card. Leaning toward the second, since "you answered the photo in
seventeen minutes and the money question in five days" works without a
name, and a card that says "Wendy" is a card most people will not post.

---

## Unchanged from the original plan

- Two ratios: 1080x1080 for Twitter and LinkedIn, 1080x1920 for Stories
  with the top 250px and bottom 350px kept clear of text.
- Fixed-pixel offscreen nodes at exact output dimensions, CSS-scaled for
  the on-screen preview, so what is seen is what downloads.
- `html-to-image` at 2x pixel ratio, plus a clipboard copy with download
  fallback.
- Quote at roughly 60% of the canvas in Fraunces, attribution small at
  bottom left, a field of the accent colour rather than a white card,
  margins around 96px at 1080.
- No CTA to anyone's site. A small wordmark, and on the demo build only,
  the demo URL. The card carrying the link is the entire sharing loop.

**The thing most likely to eat the day:** Google Fonts loaded by `<link>`
frequently fail to embed during canvas serialisation, and the PNG comes
out in Times New Roman. Fix is self-hosting Fraunces and Inter as woff2
and inlining them base64. Budget for this first, not last.

---
---

# Stage 4 close: what shipped, and the durable insight

## The insight worth keeping

**When a constraint forces specificity to move, the constrained version is
often better than the unconstrained one.**

The Wendy latency finding was predicted to die at the anonymisation gate.
It did not. What died was the shortcut.

  Named:      Your sister sent a photo and you answered in seventeen
              minutes. She asked about $135 and you took five days.

  Anonymised: A photo got answered in seventeen minutes. A question about
              $135 with a Friday deadline took 5.6 days, after the
              deadline had passed.

The second is the better sentence, and not by a little. "Your sister" was
doing work that the messages should have been doing: it told the reader
this mattered instead of showing them why. Removing it forced the
specificity down into the evidence, where it belonged.

This is what the gate bought beyond privacy. It was built to stop the card
naming people who never agreed to appear on anyone's timeline, and it
turned out to also be a writing discipline. Neither of us predicted that.

Generalisation: a constraint that removes a shortcut is not only a cost.
Before treating one as pure loss, check what the output has to do instead.

## Reframe the operation, do not tune the parameters

Three calibration passes failed in three different directions: too strict
(0 of 6), anchored on prose rather than finding (2 of 6), then too loose
and actively dangerous (6 of 6 with invented relationships). No threshold
sat between them, because the operation was wrong. Anonymisation is not
"swap a name for a relationship". It is "drop the person, keep the
message".

That is the third time in this rebuild that a fix required a semantic
redefinition rather than a parameter search:

  Stage 2: structural rules beat banned phrase lists.
  Stage 3: rank by median, not by raw spread.
  Stage 4: drop the person rather than describing them.

**When three calibration passes fail in different directions, the
operation is wrong, not the numbers.** Stop searching the parameter space
and restate what the step is supposed to do.

## Extend to the class at the moment of building

The no-arithmetic rule existed for vignettes and was not carried to the
card layer when the card layer was written. A control case computed 34
minus 3 and reported 31 messages as 31 people.

Caught during Stage 4 rather than after it, which is the discipline
working, but the cheaper moment was still earlier. The trigger to watch:
when building for case A, and case B exists in the codebase, say so out
loud and decide whether to extend before moving on.
