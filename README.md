# TwinMind preview

A local app that reads your Gmail and Calendar, finds the ten people who matter most to you right now, and writes a short editorial page for each one. Built for the TwinMind founding engineer take-home.

Beyond the per-person pages, three dashboard surfaces sit on top:

- **Forgotten:** open threads with people you haven't talked to in a while, surfaced from your inbox so they don't quietly slip away.
- **Upcoming:** your next calendar meetings with people we wrote a page for, each with a quick refresher of where you left off.
- **About you:** aggregate stats about how you actually use email. The "things you didn't know about yourself" surface.

Everything runs on your machine. The only network calls are to your own Google account, your own Anthropic API key, and Google's public OAuth servers.

---

## Quick start

```bash
pip install -r backend/requirements.txt
./run.sh
```

That's it. The first time you open the app, an in-browser setup wizard walks you through providing:

1. An Anthropic API key (text field).
2. A Google OAuth credentials JSON (paste or upload).

The wizard validates each one before saving, so you find out immediately if anything's wrong. Once both are saved, you click Begin, authorize Gmail and Calendar in the popup, and walk away. Come back in 20-30 minutes to your pages.

### Prerequisites

- Python 3.10+
- Node 18+ and npm
- macOS or Linux (tested on macOS 14, Apple Silicon)

---

## What you'll need to provide

The setup wizard will ask for these. Get them ready before you launch, or get them while the wizard is open (both work).

### Anthropic API key

Sign in at [console.anthropic.com](https://console.anthropic.com), go to API Keys, create a new key. You need access to Claude Sonnet 4.5 (default for new accounts). A typical first run uses roughly $1 in API credit.

### Google OAuth credentials

**This is the unusual part.** Each user has to create their own Google Cloud project. I cannot ship a single OAuth client that works for everybody, because Google requires a multi-week verification process before any unverified app can request Gmail or Calendar access from arbitrary users. While in "Testing mode" (the default), only the developer's explicitly-allowlisted users can authorize. So the standard pattern for local apps that touch Gmail is: each user provides their own OAuth client.

Takes about 10 minutes. The wizard has the instructions inline ("How do I get this?" expander), but here they are too:

1. Open [console.cloud.google.com](https://console.cloud.google.com) signed into the Google account whose Gmail you want to analyze.
2. **Create a new project.** Any name.
3. **APIs & Services → Library:**
   - Enable **Gmail API**
   - Enable **Google Calendar API**
4. **APIs & Services → OAuth consent screen:**
   - User Type: **External**
   - Fill in the app name, support email, developer contact (your own email is fine)
   - Find the section called **Test users** (or **Audience** in the newer Google Cloud Console), and **add the email you're signed in with**
   - Leave publishing status as **Testing**
5. **APIs & Services → Credentials → Create Credentials → OAuth client ID:**
   - Application type: **Desktop app**
   - Any name
   - Click Create, then **Download JSON**
6. Open the downloaded file in any text editor, copy the contents, and paste into the wizard. (Or use the wizard's file upload button.)

---

## What to expect

**First run: 20-30 minutes for a typical inbox.** Most of this is sequential Gmail ingestion (Gmail's per-user-per-minute quota doesn't tolerate the level of parallelism we'd need to go faster). The Claude pipeline takes ~12 minutes on an Anthropic Tier 1 account; faster on Tier 2+.

**Subsequent runs: under 2 minutes.** The email cache is reused; only new mail since the last run is fetched. The agent pipeline always re-runs to incorporate the latest correspondence.

**Cost per run: roughly $1** in Anthropic API usage.

Once the wiki loads, you can:
- Click **Start over** (top left) → **Re-run on this account** to refresh pages with new email.
- **Start over** → **Switch account** to sign out and pick a different Google account.
- **Share card** (top right) on any person to see a portrait-format summary.

---

## Architecture

```
backend/
  api.py                 FastAPI: /api/start, /status, /people,
                         /insights, /reset, /account, /preflight,
                         /setup/anthropic, /setup/google
  pipeline.py            Top-level orchestrator
  agents/
    ranking.py           Score-based contact ranking
    deep_fetch.py        Per-person history pull
    person_pipeline.py   Five-agent fan-out per person
    insights.py          Top-level dashboard composer (forgotten,
                         upcoming, about-you stats)
  prompts/templates.py   All Claude prompts, with hallucination guards
  clients/
    gmail.py             Gmail SDK wrapper
    calendar_client.py   Calendar SDK wrapper
    claude.py            Anthropic SDK wrapper with retry and citation stripping
  storage/
    ingest.py            Bulk ingestion into SQLite
    db.py                Schema and connection helper
  utils/
    progress.py          Status file read/write for the progress UI

frontend/src/
  App.jsx                Polls /api/status, routes between screens
  SetupWizard.jsx        First-run wizard: API keys + credentials.json
  SetupScreen.jsx        Pre-launch screen with preflight checks
  ProgressView.jsx       Live progress UI
  components/
    PeopleWiki.jsx       The editorial wiki (sidebar + per-person pages)
    InsightsDashboard.jsx  Forgotten / Upcoming / About-you surfaces
```

---

## Notable trade-offs

**Sequential Gmail ingestion.** I tried parallel ingestion at 20 and 8 workers; both produced silent data loss when Gmail's per-user-per-minute quota kicked in. The right fix is a shared token-bucket rate limiter that pauses all workers together on 429. The existing sequential path is correct, just slow on big inboxes.

**Tier 1 Anthropic API.** The agent pipeline could finish in ~4 minutes instead of ~12 with parallel per-person execution. Parallel runs trip the 30k input-tokens-per-minute Tier 1 limit, so we run sequentially with 1.5s inter-agent waits. Anyone with Tier 2+ access can set `PERSON_CONCURRENCY=4` in `pipeline.py` and see the speedup.

**No Perplexity integration.** Perplexity was suggested as one option for web research on the call. I went with Claude's built-in `web_search` tool instead: one fewer key for the user to provide, one fewer client integration to test, identical output quality for this use case. If you want to swap in Perplexity, the `clients/claude.py` interface is small and would take ~30 minutes to adapt.

**Hallucination defense.** Every agent prompt has an explicit zero-hallucination clause: empty fields are better than fabricated ones. The About-them agent verifies identity three ways (email domain match, in-email context match, or verifiable profile page) before stating any public fact. If none of those check out, it returns empty strings and the page renders without that block.

**Voice attribution.** Every prompt tells the model "I am [my name]," with messages tagged `ME -> THEM` or `THEM -> ME`. Without this, agents drift into describing the other person's actions as if I performed them.

**Citation stripping.** Web-search-enabled Claude outputs include `<cite index="X-Y">...</cite>` tags. The regex handles both the raw form and the JSON-escaped form before composing the final artifact.

**Display name normalization.** "Last, First" → "First Last". Missing display names are derived from the email's local-part. Falls back to raw email only as a last resort.

**Empty-field handling.** Sections render only when they have content. A page with no public info for that person shows just the timeline and prep card, cleanly.

**In-app setup wizard.** The brief asked for "a screen in the beginning that asks for all the Google client id, the Perplexity API key, the cloud API key, permissions and all." The wizard fulfills that: each key is collected, validated with a real API call (Anthropic) or shape check (Google credentials.json), and persisted to `.env` / `credentials.json` on disk. The user never has to open a text editor.

---

## Caveats and known limitations

- **OAuth is testing-mode.** Your GCP project is capped at 100 test users by Google. Plenty for personal use. Going to production requires Google's verification review.
- **Common-name contacts may have empty "About them" sections** by design. The identity check fails closed when we can't be confident.
- **First-run ingestion isn't parallel.** ~16 minutes for a 6,000-message inbox. Re-runs are quick (cache reuse).
- **Calendar shows up in three places** but isn't surfaced as raw event content on per-person pages: it biases ranking (people you meet with rank higher), shows up as a meeting count in each person's hero stats, and powers the Upcoming dashboard view with prep blurbs.

---

## What I'd build next

A few directions I'd take this if I had more time, ranked by what I think would matter most:

**Parallel ingestion with a shared rate limiter.** The single biggest win for first-run latency. A token-bucket limiter shared across all worker threads, with global pause-on-429, would let me run ~10 workers safely and cut the 16-minute ingest to under 3. Worth a half-day.

**Background refresh.** Right now the user has to manually click "Re-run on this account" to pick up new email or calendar events. A small daemon thread that re-ingests every N hours (cheap, no LLM calls) and re-composes insights on cache delta would make the wiki feel alive rather than frozen-in-time.

**Per-person query layer.** "When did I last talk to X about Y?" answered against the indexed email data. The data is already in SQLite; this would be a small RAG pipeline with one Claude call per query. The natural next step after the wiki, since people will want to ask questions about their own data.

**Connections graph.** Find people who appear together in your threads and surface the relationships between them, not just between you and each of them. "X introduced you to Y, who connected you to Z." Adds a network view to complement the per-person view.

**Real tests.** No automated tests in the current repo, partly because the most interesting failure modes are integration-level (rate limits, OAuth edge cases) where unit tests don't help much. A small set of end-to-end tests on canned email fixtures would cover the ranking heuristic, the agent prompt schemas, and the insights composer.

**Streaming agent output.** Right now the progress bar shows "agent 4 of 10" but the user sees nothing until everything finishes. Streaming partial JSON to the frontend as each person finishes would let people start reading immediately instead of waiting for the full pipeline.

---

## Stopping and resetting

**Stop:** `Ctrl+C` in the terminal.

**Stuck on a stale screen:** The server clears stale status automatically on startup, but if needed:
```bash
rm output/status.json
```

**Truly fresh start (re-ingest everything, re-authorize, re-setup):**
```bash
rm -rf data/ output/ token.json .env credentials.json
```

Next run will show the setup wizard from scratch.
