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

---

## Deploy hygiene: two rules that paid for themselves

### Audit by reachability, not by rendering

**A public deploy changes the reachability of everything the frontend
fetches, not just what the frontend displays.** The correct pre-deploy
walk covers every URL a visitor can reach, not every page a visitor lands
on.

Two things were caught this way and neither was visible in a dev browser,
because neither renders:

`demo/config.json` is fetched by the browser at a guessable path and
carried several paragraphs of internal design reasoning, including a
frank assessment of which part of the demo is the weakest content. Anyone
who guessed the URL could read it.

`output/people.json` carried two plausible `@gmail.com` addresses. Nothing
in the UI shows an email, so nothing looked wrong.

Checklist for any future deploy: every JSON the app fetches, every asset
path, every error string the app can surface, every route that returns
something other than 404.

### Contamination is not only your identity

Scanning for the repo owner's name in the prompts turned up four other
people: an email address in a docstring, two "Last, First" samples, and a
correspondent named as the heavy case for token budgeting, with her
message count attached. All real, all from the original inbox, all in code
comments headed for a public repo.

Your own name in your own repo is your call. Everyone who ever appeared in
your test data is not, and they were never asked.

The corpus had the same problem from the other direction: two fictional
contacts used plausible `@gmail.com` addresses, which can collide with
real strangers who would then find their address attached to invented
emotional content. Fictional data belongs on RFC 2606 reserved domains.

**When you scan for one identity, scan for all of them.** The one you are
looking for is the one you already know about.

---

## What the live walk caught that local testing could not

Both were URL-identity problems, and neither can surface before a real
deploy because locally there is no public domain to be wrong about.

**The OG image pointed at a domain owned by someone else.**
`correspondence.vercel.app` was a hardcoded guess. The file served fine at
the real domain, the meta tag just pointed elsewhere, so every link
preview would have 404'd and every posted card would have carried a
stranger's URL. Fixed by taking the domain from
`VERCEL_PROJECT_PRODUCTION_URL` at build time. index.html gets it via a
`transformIndexHtml` plugin, since HTML cannot read a Vite define.

**Vercel detected the FastAPI backend as a deployable service.** It runs
OAuth flows and reads a user's Gmail. `.vercelignore` now keeps it, the
corpus and the database out of the upload entirely, and the project root
is `frontend/`.

## Deployment protection

A manually assigned alias came up behind Vercel SSO and returns 302 to a
login. The project's own production domain is public and serves the same
build. If a custom alias is wanted, Deployment Protection has to be turned
off in the dashboard: there is no CLI for it, and changing a project's
security posture is an owner decision rather than something to do with a
scraped token.

## Verified live

Root, deep links, an unknown person id, and the OG image all 200. Every
internal path 404s: `/output/*`, `/demo/*`, `/api/*`, `/vercel.json`,
`/package.json`, `/src/*`. No identity strings in the served bundle.
Security headers present at the edge.
