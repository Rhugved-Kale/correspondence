# Stage 2 handoff: prompts and grounding

What changed, what it cost to learn, and the one rule that came out of it
which applies to everything after.

Closed. Voice work on the timeline, stories, and prep agents, plus a
deterministic grounding layer that turned out to matter more than the
prompt edits did.

---

## The rule

**Any fact derivable from data is precomputed and handed to the model as
input. It is never requested as output.**

This is not a style preference. Three separate defects showed up in this
stage and all three were the same defect wearing different clothes:

| Defect | What the model was asked to produce | Fix |
|---|---|---|
| Fabricated quotes | "quote the email" | verify against source, drop the field |
| Wrong word counts | "his reply was four words" (it was six) | compute from the quote, substitute |
| Wrong date arithmetic | "nine days before" (it was twenty-three) | precompute gaps, hand them in |

Every derivable fact handed in as input has zero hallucination risk. Every
derivable fact requested as output creates it. Stage 3's signal
computation already assumed this at the data layer. It now applies at the
prompt layer too, so the artifact has one architecture rather than two.

The corollary, learned expensively: **a prompt prohibition against a
rhetorically attractive construction does not hold.** "His reply was four
words" is a satisfying sentence, and the model reaches for it faster than
it consults a ban. Three attempts, three failures. If a defect is
deterministically detectable, detect it. Do not ask more firmly.

---

## What shipped

**`backend/agents/grounding.py`.** Runs after the agents, before compose.

- Timeline `evidence` is verified against the source. A quote that isn't
  there clears the field and keeps the event. Field-level, not
  event-level: a good event with a bad quote is still a good event, and
  the UI already renders empty evidence because that was always a
  legitimate agent output.
- Story quotes are checked and logged but never edited. Excising a quote
  mid-sentence produces worse output than leaving an imperfect one.
- Count claims ("four words", "two lines") are corrected against the
  nearby quote, or removed when there is nothing to count.
- Derived durations are detected and logged as a monitor, not enforced.

Every action logs one greppable line, so hallucination rate is measurable
on real inboxes and not just during iteration:

    GROUNDING drop person=... agent=timeline field=evidence text=...

**Precomputed silences.** `_format_gaps_block` in `person_pipeline.py`
computes every gap over ten days, with direction: who fell silent, who
spoke first afterward. The timeline agent writes prose around those
numbers instead of deriving them.

Direction detection earns its keep on its own. Josiah's second gap reads
"They sent the last message before it and they broke it too, so I never
replied at all," which is the forgotten-thread signature, precomputed.

**Voice spec** in `templates.py`: a banned-phrase list, bad/good pairs,
and the absence rule. Shared by all three voice agents.

**`demo/preview.py`.** Three agents, one person, guarded path, in about a
minute.

---

## The biggest single win

**Nothing in any prompt asked about absence.**

The Theo thread's most human moment is a twenty-three day silence after
she got defensive, which she breaks herself with a message that never
apologises and functions entirely as one. Every agent walked past it,
because every prompt pointed at what messages say.

Email's most meaningful content is frequently what is not there: the gap,
the unanswered question, the promise never mentioned again, the thread
that stops and who it stopped on. That is the thesis The Read is built on,
and the per-person agents now share it. The artifact has one voice at a
structural level, not just a stylistic one.

It generalised further than the precompute reaches. On Marguerite the
stories agent found an absence nobody planted: "Marguerite didn't reply to
that message. The thread moved to other questions and the scheduling
answer was never mentioned again."

---

## Prompt rules that worked, and one that did not

**Worked: structural rules beat example lists.** `why_it_matters` kept
awarding virtues ("He cared more about me learning than about being
right") through two rounds of banned examples. One grammatical rule fixed
it completely: *the subject may not be a person*. Output became "The
concession arrived twenty-three days later, by email, unprompted" and "The
ask escalated down, not up."

When banning a behaviour, ban the structure that produces it, not the
instances you have seen.

**Worked: concrete-noun requirement on timeline titles.** "I sought advice
on billing feature pressure" became "Billing is a trapdoor."

**Did not work: three separate prohibitions on counting and measuring.**
See the rule above.

---

## Open, deliberately

**Derived durations are monitored, not enforced.** The ban was written and
then dropped, because the evidence changed: durations went from badly
wrong ("nine days" for twenty-three) to accurate, and one contrast is
load-bearing. In Wendy's story, "I wrote back three days later... Twenty
days later she wrote again" is the headline finding surfacing unprompted.
Removing those numbers would cost the story more than the rule was worth.

`derived_durations` still counts every one. If they drift on a different
corpus, it shows up in logs before it shows up in an artifact.

**The guard checks quoted spans only.** Paraphrase is what prose is for.
Marguerite's story restated Corbin's equine software and the eighteen-month
shutdown accurately in its own words, and policing that would break the
thing worth having. The consequence is that unquoted numeric claims sit
outside the guard, which is exactly why that class of fix belongs on the
input side.

---

## Measured state at close

Three people through the guarded harness, all agents:

| | Theo | Marguerite | Wendy |
|---|---|---|---|
| evidence dropped | 0/11 | 1/5 | 0/6 |
| counts fixed | 1 | 0 | 0 |
| story quotes flagged | 0 | 0 | 0 |
| silence events | 2, exact | 1, exact | 3, exact |
| `why_it_matters` with a person subject | 0 | 0 | 0 |

The Marguerite drop is the guard doing its job on a run that otherwise
looked shippable: the model emitted "she was one incident away from
leaving" as verbatim evidence. The email says "one incident away from
going back to paper."
