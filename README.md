# Correspondence

Facts about you, written as observations you would screenshot.

It reads your Gmail and Calendar, finds the people you actually talk to,
and writes about them. Then it turns around and writes about you, from
evidence you supplied without meaning to.

**[See it running on a made-up inbox →](https://correspondence-demo.vercel.app)**
No signup, no install. The demo runs on a fictional person's ninety days
of email, generated for the purpose, so you can see the whole artifact in
about a minute.

---

## What it produces

**A page for each of the ten people who matter most right now.** Not a
contact card. A timeline of what actually changed between you, two or
three stories with a turn in them, and a prep card for the next time you
talk. Where a relationship went quiet, the silence is an event on the
timeline with the number of days on it.

**The Read**, which is about you. This is the part worth looking at first:

> **Let me check and I'll ping you**
>
> You have written "let me check" or "I'll ping" or "this week" fourteen
> times across nine people. Ten of those threads contain no further
> message from you. [...] Marguerite wrote back: "you have now told me
> twice that you will have a real answer after a conversation that has not
> yet been scheduled."

> **You slowed down first, then she did**
>
> Your first two replies to Nkechi took three hours and five hours. Then
> 2.6 days. Then 3.6, then 6.6. [...] Your messages got shorter as they
> got slower. You went from 167 words to 102 to 80 to 48 to eighteen.
> [...] But you're the one who changed pace first, two days before she
> did.

Every number there was computed in SQL before any model saw it. The model
was handed the figures and asked to write sentences around them, which is
the single design decision that most affects whether this is trustworthy.

**Share cards**, one thought each, at the two aspect ratios that matter.
Every card is anonymised: nobody else's name appears on anything you might
post.

**Forgotten threads and upcoming meetings**, which are the boring useful
part.

---

## Try it on your own inbox

```bash
pip install -r backend/requirements.txt
./run.sh
```

A browser wizard collects an Anthropic API key and a Google OAuth client,
validating each before it saves. Then it runs: roughly 20 to 30 minutes on
a first pass, mostly Gmail ingestion, and about $1 in API credit. Later
runs reuse the cache and take about two minutes.

Everything stays on your machine. The only outbound calls are to your own
Google account, your own Anthropic key, and Google's OAuth servers.

<details>
<summary><b>Getting a Google OAuth client</b> (about ten minutes, and unavoidable)</summary>

Each user has to create their own Google Cloud project. I cannot ship one
OAuth client that works for everybody: Google requires a multi-week
verification review before an unverified app can request Gmail access from
arbitrary users, and until then only explicitly allowlisted testers can
authorize. Every local app that touches Gmail has this problem.

1. Open [console.cloud.google.com](https://console.cloud.google.com),
   signed in as the account whose mail you want to read.
2. Create a project. Any name.
3. **APIs & Services → Library**: enable the **Gmail API** and the
   **Google Calendar API**.
4. **OAuth consent screen**: User Type **External**, fill in the three
   required fields, then find **Test users** (called **Audience** in newer
   consoles) and add your own address. Leave publishing status on
   **Testing**.
5. **Credentials → Create Credentials → OAuth client ID**, type
   **Desktop app**, then **Download JSON**.
6. Paste the file's contents into the wizard, or use the upload button.

</details>

---

## How it works

Ingestion pulls a recent window of mail into SQLite. A deterministic
ranker scores every contact on reciprocity, volume, recency and calendar
overlap, and the survivors get a full history pull. Five agents then run
per person, and a separate pass computes signals about you and writes The
Read.

```
backend/
  pipeline.py             orchestrator
  agents/
    ranking.py            score every contact, keep the top ten
    deep_fetch.py         full history for the ones that survived
    person_pipeline.py    the five-agent fan-out per person
    grounding.py          verify what the agents claim they quoted
    self_portrait.py      ten signal families about the user, no prose
    phrasing.py           every figure pre-rendered in every form
    read_composer.py      which findings make the page
    card_selector.py      which findings survive anonymisation
    insights.py           forgotten threads, upcoming meetings
  prompts/templates.py    every prompt, and every rule that cost something
frontend/src/components/
  PeopleWiki.jsx          the per-person pages
  InsightsDashboard.jsx   The Read, Forgotten, Upcoming
demo/                     the fictional corpus, and the tools that made it
```

---

## Three rules the code is built on

Each one cost a stage to learn.

**Any fact derivable from data is precomputed and handed to the model,
never asked for.** Fabricated quotes, wrong word counts and wrong date
arithmetic turned out to be the same defect wearing three coats: the model
being asked to produce something the data already contained. Handing the
value in drops that risk to zero. Asking for it creates the risk. This is
why `phrasing.py` renders "2.6 days" and "62 hours" and "about a week"
before anything reads them, and why a date gap is computed in Python and
passed in as a sentence.

**Structural rules beat lists of banned phrases.** Telling the model not
to write a phrasing gets that exact phrasing avoided and the move
performed some other way. Telling it that a field's grammatical subject
may not be a person ends the behaviour immediately. Three attempts at
banning interpretation failed before the rule became "every sentence must
describe something that happened or something that was written."

**A guard that over-reports is worse than no guard.** The grounding layer
flagged seventeen fabricated quotes on a full run. Eleven were the model
quoting accurately and adding a full stop, or rendering the source's
double quotes as single. A false-positive rate that high trains you to
ignore the alarm, which is worse than not having one. It measures six now,
and all six are real.

---

## Trade-offs

**Sequential Gmail ingestion.** Parallel at 8 and 20 workers both produced
silent data loss when the per-user quota kicked in. The right fix is a
shared token bucket that pauses every worker on a 429. What is here is
correct and slow.

**Anonymisation as a selection gate, not a formatting step.** Cards try
every finding with the names removed. What still means something becomes a
card; what collapses stays in the private view. This started as a privacy
control and turned into a writing discipline: the best finding in the demo
corpus got *better* anonymised, because "your sister" had been doing work
the messages should have been doing.

**Empty beats invented, everywhere.** Agents return empty fields rather
than guessing, the identity check on public bios fails closed, and both
The Read and the card layer will decline to say anything at all. A page
with four findings instead of six reads fine. A page with two invented
ones does not.

**The demo bakes prebuilt JSON.** No backend, no keys, nothing to run. The
consequence is that its corpus is frozen at a fixed date, so relative time
renders against that date rather than the clock.

---

## Known limits

- **OAuth stays in testing mode**, capped by Google at 100 users. Fine for
  personal use.
- **Ranking decays against the real clock.** Re-running the pipeline
  against the demo fixture long after its window gives a uniformly decayed
  recency signal. It does not affect the deployed demo, which bakes its
  JSON at build time.
- **Common-name contacts often have an empty "about them" block.** That is
  the identity check working.
- **No automated tests.** The interesting failures are integration-level.
  The demo fixture is the seam that would make real ones possible, and it
  already runs the pipeline end to end in seconds.

---

## What I would build next

**Validate The Read against live inboxes.** Everything in it was tuned on
one fictional corpus built to contain specific findings. The gates that
decide whether a finding is worth stating are calibrated against that
corpus and nothing else. Running it over several real inboxes and checking
what fires, what stays silent, and what turns out to be wrong is the
highest-value next step by a distance. Two things to watch specifically:
whether the interpretation ban holds on findings the demo never selected,
and whether the anonymisation gate rejects too much on relationships less
neatly shaped than the fixture's.

**Parallel ingestion with a shared rate limiter.** A token bucket across
all workers with global pause-on-429 would cut a sixteen-minute first run
to under three. Half a day of work and the single biggest latency win.

**Background refresh.** A daemon that re-ingests every few hours and
recomposes on cache delta, so the wiki stops being frozen at whenever you
last clicked a button.

**Per-person query.** "When did I last talk to X about Y?" against the
indexed mail. The data is already in SQLite.

---

## Stopping and resetting

Stop with `Ctrl+C`.

Stuck on a stale screen:

```bash
rm output/status.json
```

Start completely over, including re-authorizing:

```bash
rm -rf data/ output/ token.json .env credentials.json
```
