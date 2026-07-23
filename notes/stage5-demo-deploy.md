# Stage 5 handoff: the public demo

Written at the close of Stage 3. Stage 5 puts the artifact on the web so
someone can see it without installing anything.

## Already done, ahead of schedule

Demo mode exists. `VITE_DEMO=1` makes `App.jsx` skip status polling, the
setup wizard and the progress view, and read prebuilt JSON instead. It was
built during Stage 3 because there was no other honest way to look at The
Read, and it is the same seam Stage 5 needs.

`demo/config.json` names the landing person. `demo/run_pipeline.py` runs
the real per-person pipeline against the fixture with the About agent
stubbed. `demo/read_all.py` and `backend/agents/read_composer.py` produce
The Read.

## What is left

**Bake the JSON into the build.** Demo mode currently fetches from
`/output/` and `/demo/`, served by a Vite middleware that only exists in
dev. For a static deploy the files have to be imported so they are bundled,
which also removes the loading flash on a cold visit.

**Real URLs per person.** Selection is React state, so every shared link
opens on the landing person. For an artifact whose whole purpose is being
sent to people, that is a bigger problem than it looks. History API plus a
Vercel rewrite to index.html.

**The date problem.** Upcoming is computed against `now`, so a frozen
fixture goes stale and eventually shows an empty calendar. The corpus
already carries `demo_as_of: 2026-06-30`; the frontend should compute
relative times against it in demo mode rather than re-basing every date at
build time. Less machinery, never breaks, and it does not pretend a
fictional meeting is happening on Tuesday.

**PROTAGONIST_NAME.** `VOICE_RULE` in templates.py still hardcodes the
repo owner's name, so the demo pipeline currently narrates Priya's inbox
as him. It does not show, because the rule only governs pronoun
attribution, but it is wrong and it is the last thing tying the prompts to
one person. Parameterise from config and thread through.

**Open Graph.** One good site-wide image. Per-person prerendered cards
from the Stage 4 renderer are the obvious follow-up and should not block
the deploy.

## Watch for

The local install path must keep working. `run.sh` and the API flow are
untouched by demo mode and should stay that way; the only shared surface
is `App.jsx`, and the demo branch returns before any of the API logic
runs.
