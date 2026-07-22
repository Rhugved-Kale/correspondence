# The demo world

Hand-authored source of truth for the public demo. Threads get generated
from this file, not the other way around. If a fact is not here, it is not
true in the demo.

The rule that makes this honest: the world is fiction, the pipeline is not.
We author the people and the events. We do not author the findings. The
Read discovers the reply-latency gap because the reply-latency gap is
genuinely present in the generated timestamps, not because we wrote the
conclusion somewhere.

`demo_as_of`: 2026-06-30. All relative time in the demo renders against
this date, not against today, so the artifact never rots.

Window: 2026-04-01 to 2026-06-30 (91 days).

---

## Protagonist

**Priya Raghunathan** (she/her), 29. Technical co-founder and CTO of
Thicket.

Thicket makes practice-management software for independent veterinary
clinics: scheduling, records, billing. Two founders. Incorporated in
February 2026, so the window covers months three through five. Pre-seed
closed in April. Three pilot clinics, one of which is doing real work with
it and two of which are politely not.

Before this she was a staff engineer at Corvia, a mid-size freight
logistics company, for four years. She left in January.

Lives in Oakland. Family in Fremont, forty minutes away, which is close
enough that not visiting is a choice rather than a circumstance.

### How she writes

This is the part that has to be consistent, because half the findings in
The Read are derived from it.

- **Hours.** Sends cluster in two bands: 9am to 6pm, and a second shift
  from 10:30pm to about 1:30am. The late band is where the long,
  thinking-out-loud emails get written. Roughly 30% of her outgoing volume
  is after 10pm. Almost nothing between 2am and 8am.
- **Length is inverse to closeness.** Long and careful to people she is
  managing upward to. Short to people she works with hourly. This is the
  finding, so it has to be real in the data:
  - Marguerite: 250 to 400 words, structured, sometimes numbered
  - Rosalind: 150 to 250 words, warm, apologetic when there is a bug
  - Theo: 80 to 150 words, more careful than she is with anyone else
  - Dane: 5 to 20 words, often just a link or "yes"
  - Callum: 3 to 10 words, lowercase
  - Wendy: 15 to 40 words, and always slightly guilty
- **Sign-offs.** "Best, Priya" to Marguerite and Theo. "P" to Rosalind.
  Nothing at all to Dane and Callum. "love you" to Wendy, lowercase, which
  is the only time she uses it.
- **Opener.** She starts a lot of messages with "Sorry, just seeing this."
  Enough that it should surface as a finding. She is not usually sorry and
  has usually seen it.
- **Habit.** She replies to the easy question in a multi-question email and
  silently drops the hard one. This is the mechanism behind question debt
  and it needs to be visible in the threads, not just asserted here.

---

## The ten

Ordered by expected rank. Each entry ends with the finding it exists to
make true.

### 1. Dane Whitfield — co-founder, CEO

Former veterinary technician, eight years in clinics, turned himself into
the sales half of the company. Not technical, but knows the customer
better than Priya ever will. They met when he was a user of an internal
tool she built at Corvia and sent her a two-thousand-word teardown of it.

**Writes:** in fragments. Sends four messages in ninety seconds instead of
one organized one. No greeting, no sign-off, no capital letters at the
start of a sentence about half the time. Uses "ok so" as a paragraph
opener. Long voice-memo-shaped messages when he is excited.

**Tension:** he wants the billing module built now because two of the pilot
clinics have asked for it and he thinks it closes the seed round. Priya
thinks billing is a six-week hole that will eat the runway. It stays
professional and then briefly does not.

**Arc:** constant background traffic. Disagreement surfaces around week 6,
gets sharp in a single thread in week 7, resolves week 9 into a scoped
compromise (billing read-only, invoicing deferred).

**Plants:** the reply-latency floor, roughly 11 minutes median in both
directions. Highest volume by a wide margin. The shortest outgoing
messages. Daily calendar overlap. The "who gets the last word" stat.

### 2. Marguerite Vance — lead pre-seed investor

Angel, writes small checks and takes them seriously. Former COO of a
healthcare staffing company that exited. Sits on four boards, treats
Thicket as the one she is most hands-on with, which Priya experiences as
both flattering and a workload.

**Writes:** formally. Full paragraphs, no fragments, numbered questions
when there is more than one thing. Always "Best, Marguerite". Replies
within a day but never instantly. Asks three-part questions where the
third part is the one that matters.

**Tension:** she has asked twice for a metrics update. Priya keeps
postponing because retention across the three pilots is soft and she wants
one more good week before showing anything. Marguerite is not angry, which
is worse.

**Arc:** intro-and-close in April, warm check-in in May, a slightly cooler
one in June with a question about pilot conversion that does not get a
straight answer.

**Plants:** the longest outgoing messages, 340-word median. Sub-hour reply
latency, which contrasts against Wendy. Question debt: her multi-part
questions are where Priya's answer-the-easy-one habit is most visible.

### 3. Dr. Rosalind Achterberg — pilot customer, Cascade Veterinary, Tacoma

Owns a two-vet clinic. Twenty-six years in practice. The only pilot
customer doing real daily work in the product, which makes her the most
valuable person in the window and the one most able to hurt them.

**Writes:** long, warm, digressive. Tells you about her weekend inside a
bug report. Exclamation points. Includes clinical detail she does not
realize is fascinating to a software person. Signs "Ros".

**Tension:** the scheduling module assumes appointments are the atomic
unit. Her clinic books around *rooms*, because a surgery blocks a room for
three hours regardless of what is on the calendar. The product is wrong in
a way that is expensive to fix, and she found it in week two.

**Arc:** skeptical in April, nearly quits the pilot in week 5 after a
double-booking incident during a surgery day, gets a genuine fix in week 7,
becomes their best reference by late June and offers to talk to other
clinics unprompted.

**Plants:** the strongest story material in the corpus, because there is a
real turn. The prep card's "something personal" (her dog Bramble, a
fourteen-year-old greyhound with a thyroid condition she mentions in
passing three times). A forgotten thread: a smaller bug she reported in
May that never got a response.

### 4. Theo Brandt-Sørensen — former manager at Corvia, informal advisor

Ran Priya's team for three years. The person whose opinion she is least
able to dismiss and most likely to argue with. No formal role at Thicket,
answers her email anyway.

**Writes:** short. Dry. Four sentences where most people use fifteen. Signs
"T". Occasionally brutal in a way that reads as affection if you know him
and as contempt if you do not.

**Tension:** he told her in week 4 that she is building a features list
instead of a product, and specifically that taking on billing would be a
mistake she cannot undo. She replied defensively. The reply was, in
retrospect, not her best work.

**Arc:** friendly April. One genuinely sharp exchange in week 4. Then three
weeks of silence, which is the loudest thing in the corpus. She breaks it
in week 8 with a short message that does not apologize but functions as
one. He responds as if nothing happened, which is its own kind of answer.

**Third act, and the reason he matters most.** After the repair the
relationship re-forms on different terms. She stops writing to him as a
former report managing a relationship and starts arguing with him as an
equal. Late June threads are real idea exchange, mostly about whether
vertical software in a low-margin industry can survive without services
revenue. She disagrees with him twice and does not back down.

This is the only place in the corpus where Priya writes as a peer about
ideas rather than transacting, apologizing, or managing upward. Without it
her outgoing register never leaves those three modes, which is both untrue
to a real person and flattening for the artifact. It is placed here, after
the conflict, because a relationship that changes shape is worth more than
one that was always equal.

**Plants:** the best single story, because conflict and repair is the only
shape that reliably produces a story with a turn. Her most careful writing.
A timeline with a real state change in it rather than a list of milestones.
The peer register, which gives length-by-recipient a second dimension: 340
words to Marguerite performing competence, 340 words to Theo thinking out
loud, same count, opposite mode.

### 5. Nkechi Adeyemi — engineering candidate

Senior engineer at a large company, six years in. Priya has been trying to
hire her since April. She would be the first employee.

**Writes:** carefully. Professional but not cold. Asks genuinely good
questions about equity, runway, and what happens if the seed does not
close, which are the questions Priya least wants to answer precisely.

**Tension:** she is interested and not moving. Priya is trying to create
urgency without looking desperate, and is not good at it.

**Arc:** strong interest in April, two good conversations in May, then a
noticeable slowdown in early June, then nothing after June 12. No rejection
ever arrives. The thread simply stops.

**Plants:** the cooling-relationship signal. Message frequency drops hard
between the first and second half of the window, which is exactly what that
finding is built to detect. Also a forgotten thread, because the last
message in the chain is hers and it contains a question.

### 6. Callum Reyes-Baptiste — design contractor

Part-time, two days a week, excellent, chronically late with invoices. Was
a friend of Dane's before he was a contractor.

**Writes:** lowercase, from his phone, almost always. "k". "on it". "sorry
just saw this". Sends a Figma link with no context and expects you to
understand. Occasionally sends a genuinely thoughtful paragraph at 2am that
is better than anything anyone else said that week.

**Tension:** low. The only friction is administrative, and it is mutual.

**Arc:** steady throughout. One invoice thread that takes eleven messages
to resolve something that should have taken two.

**Plants:** the terse extreme of the length-by-recipient finding. Sign-off
drift, since he gets "thx" and nothing else. An administrative thread that
decays into nothing.

### 7. Wendy Okonkwo — Priya's older sister

Thirty-four, lives in Fremont, two kids, does the family logistics because
nobody else will. The emotional center of the corpus.

**Writes:** warm, chatty, direct. Asks real questions and expects real
answers. Not passive-aggressive, which makes the eventual frustration land
harder.

**Tension:** their mother turns sixty in July. Wendy is organizing it. She
needs four things from Priya: a date confirmation, a contribution to the
gift, whether she is bringing anyone, and whether she can come a day early
to help set up. She asks across four separate emails over eleven weeks.
Priya answers the date question. She never answers the other three.

**Arc:** cheerful in April. Mildly prompting in May. In June, one message
that is still kind but has clearly cost her something to write: "I know
you're busy. I'd just like to know if I should set a place for you."

**Plants:** the headline finding. Median reply latency four to six days
against Dane's eleven minutes, which is the roughly 500x gap. Most of the
question debt. The single most uncomfortable and most shareable line in
The Read.

### 8. Josiah Lindqvist — friend from grad school

Building something in a different space. Wants an introduction to
Marguerite. Apologetic, persistent, entirely reasonable.

**Writes:** friendly and slightly over-explaining. Front-loads an apology
for asking. Follows up politely and hates that he is doing it.

**Tension:** Priya said "happy to, let me think about the right framing"
in week 2. She meant it. She never did it.

**Arc:** two genuine peer threads in early April with no ask in them at
all, trading notes on pricing and on hiring a first engineer. Then the
favor in week 2. An enthusiastic yes. A follow-up in early May, another in
late May with visible embarrassment, then quiet.

The two early threads exist so the ask lands between friends rather than
arriving from a supplicant. It makes the broken promise worse, which is
the point.

**Plants:** the canonical forgotten thread. A promise, made explicitly, in a
quotable sentence, with no follow-through anywhere in the corpus. This is
the one that should make a viewer wince.

### 9. Ezra Mbeki-Toft — office sublet landlord

They rent four desks in the back of a converted print shop. He manages the
building.

**Writes:** terse, formal, faintly passive-aggressive. Refers to "the
premises". Numbers his points for no reason.

**Tension:** the bathroom has flooded three times. Each time he explains
that it is not a plumbing issue.

**Arc:** three flooding threads, escalating in politeness, resolving in
nothing.

**Plants:** comic relief, which the corpus needs or it reads as one long
guilt trip. A clean example of the last-word stat.

### 10. Hana Vuković — recruiter

In-house at a large company, trying to pull Priya back into a salaried job.
Persistent, polished, does not take silence for an answer.

**Writes:** polished outbound sequences that are just personalized enough
to be annoying. Refers to Thicket by name to prove she did research.

**Tension:** none, really. Priya replied once in April to say she is not
looking. Hana has emailed four times since.

**Arc:** five inbound, one outbound.

**Plants:** tests the ranker. Low reciprocity, decent volume, recent. She
should score low and probably fall out of the top ten, which is the correct
behavior and worth being able to demonstrate.

---

## Noise contacts

Not featured. They exist so ranking has real work to do and so the
automated-sender filters have something to catch. Roughly 60 to 80 messages
total across all of these.

- `receipts@stripe.com` — billing notifications, no replies
- A weekly industry newsletter, opened, never replied to
- `no-reply@` calendar and doc-sharing notifications
- A conference CFP and two follow-ups
- Two cold sales emails, one of which gets a one-word "no thanks"
- **Beatriz Salas-Whitmore**, office manager at Cascade Veterinary. CC'd on
  most Rosalind threads, three direct messages. Real human, correctly ranks
  below the ten.
- **Aiden Fenwick**, an old Corvia colleague. One catch-up exchange in
  April, two messages each way, then nothing. Thin but genuine, which is
  exactly the case the reciprocity damper is built for.

---

## Planted findings

Every row is a fact the generated corpus must make true in the data. None
of these get written as conclusions anywhere. The pipeline finds them or
the corpus is wrong.

| Finding | Mechanism | Owner |
|---|---|---|
| Reply-latency gap | 11 min median vs 4 to 6 days | Dane vs Wendy |
| Question debt | 14 unanswered questions, answer-the-easy-one habit | Wendy, Marguerite, Rosalind |
| Second shift | ~30% of sends after 10pm | Priya, all threads |
| Length by recipient | 340 words vs 9 words | Marguerite vs Dane |
| Sign-off drift | Five distinct sign-offs by relationship | all |
| Signature opener | "Sorry, just seeing this" | all |
| Cooling relationship | Frequency cliff after June 12 | Nkechi |
| Last word | Ends threads with Ezra and Hana, never with Dane | Ezra, Hana |
| Forgotten: the promise | Explicit yes, zero follow-through | Josiah |
| Forgotten: the dropped bug | Reported in May, never acknowledged | Rosalind |
| Forgotten: the open question | Her last message asks something | Nkechi |

---

## Calendar

Roughly 34 events across the window, plus 5 in the two weeks after
`demo_as_of` so Upcoming has content.

- Daily 9:15am standup with Dane, weekdays, recurring
- Weekly Thursday pilot check-in with Rosalind, moved twice
- Three investor calls with Marguerite, one rescheduled twice before
  happening
- Two Nkechi interviews in May, and a third that was scheduled for June 18
  and quietly cancelled, which corroborates the cooling signal
- Callum's Tuesday design sessions
- A dentist appointment, a car service, and Wendy's "MOM BIRTHDAY PLANNING
  CALL" that appears on the calendar three times and is declined twice

Upcoming (after June 30): standup, a Rosalind check-in, a Marguerite
quarterly, a first-round with a new candidate, and the birthday planning
call, still unanswered.

---

## About-them blocks

These people do not exist, so the About agent would correctly find nothing
and correctly return empty strings. The hallucination guard working as
designed is what would break the demo. So these are authored here and
injected by the demo loader, with the About agent skipped on demo runs
only. Stated plainly in the README.

Two rules, because a badly authored version is worse than an empty one.

**Match the schema exactly.** `one_line` under 25 words. `current_focus`
and `background` are one to two sentences or an empty string. Between zero
and three `three_things_to_know`, each under 25 words. No generic
descriptors: no "experienced", no "innovative", no "passionate".

**Match the completeness distribution.** This is the part that is easy to
get wrong. A real inbox does not return ten full bios. The agent fills a
block in proportion to how much of a public footprint the person has, and
for most people in most inboxes that is not much. The demo has to show the
same spread or it is advertising a capability the tool does not have.

| Person | Fill level | Why the agent would land there |
|---|---|---|
| Marguerite | Full | Named investor, board seats, an exit. Findable. |
| Theo | Full | Engineering leader at a company with a public eng blog. |
| Nkechi | Partial | Senior IC at a large company. Title and employer, little else. |
| Hana | Partial | In-house recruiter. A profile page and nothing more. |
| Rosalind | Partial | Clinic has a website with a staff bio. No personal presence. |
| Dane | Thin | Cofounder of a three-month-old company. One line, maybe. |
| Josiah | Thin | Founder of something pre-launch. Barely indexed. |
| Callum | Empty | Freelance designer, no site, common enough name. |
| Wendy | Empty | Private person. Correctly returns nothing. |
| Ezra | Empty | Manages a building. Correctly returns nothing. |

Three empty blocks out of ten is not a gap in the demo. It is the demo
showing the identity check failing closed, which is a real property of the
tool and worth a viewer seeing.

Authored blocks live in `demo/about_blocks.json`.
