"""
FastAPI app for the local TwinMind preview.

This is what runs on the user's laptop. The flow:
  1. They launch the server (uvicorn backend.api:app).
  2. The frontend loads at http://localhost:8000/.
  3. They click "Begin" on the setup screen, which POSTs /api/start.
  4. The pipeline runs in a background thread, writing progress events to
     output/status.json after each phase change.
  5. The frontend polls /api/status every second to render a live progress
     view: "Ingesting message 800/4500", "Running agents for person N of 10".
  6. When status reports "done", the frontend switches to the artifact view
     and loads /api/people.

We picked polling over Server-Sent Events because polling is simpler to get
right under macOS networking constraints, costs essentially nothing for a
single-user local app, and avoids long-lived connection bugs. The poll
interval is 1 second; the pipeline takes ~25 minutes, so the poll overhead
is invisible.
"""

from __future__ import annotations

import json
import threading
import time
import traceback
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.config import get_settings
from backend.utils.logging import get_logger, setup_logging
from backend.utils.progress import (
    STATUS_PATH,
    PEOPLE_PATH,
    Phase,
    read_status,
    write_status,
)


log = get_logger("api")

app = FastAPI(title="TwinMind preview", version="0.1.0")

# CORS: in dev the frontend runs on 5173 and the API on 8000. We allow that
# origin so npm run dev can hit /api/* without a proxy. In production the
# frontend is served by this same FastAPI, so CORS doesn't matter.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Pipeline state. We protect it with a lock because /api/start can be hit
# concurrently if the user double-clicks the button.
_pipeline_lock = threading.Lock()
_pipeline_thread: threading.Thread | None = None


@app.on_event("startup")
def clear_stale_status() -> None:
    """
    If the previous server crashed mid-pipeline, output/status.json could
    be stuck pointing at an "in progress" phase even though no thread is
    running anymore. On a fresh process start there's definitionally no
    pipeline running, so any non-terminal phase in the file is a ghost.
    Reset it to idle so the user sees the Setup screen instead of a
    progress view that never moves.
    """
    current = read_status()
    if current and current["phase"] not in (
        Phase.IDLE.value,
        Phase.DONE.value,
        Phase.ERROR.value,
    ):
        log.info("clearing stale status (phase=%s)", current["phase"])
        STATUS_PATH.unlink(missing_ok=True)


@app.get("/api/status")
def get_status():
    """
    Return the current pipeline status. The frontend polls this once a
    second to render the progress view. Returns sensible defaults when no
    pipeline has been kicked off yet so the setup screen doesn't have to
    special-case the "fresh launch" state.
    """
    status = read_status()
    if status is None:
        return {
            "phase": Phase.IDLE.value,
            "message": "Ready to begin.",
            "current": 0,
            "total": 0,
            "started_at": None,
            "finished_at": None,
            "error": None,
        }
    return status


@app.post("/api/start")
def start_pipeline():
    """
    Kick off the pipeline in a background thread. Idempotent: if a pipeline
    is already running, returns 409 instead of starting a second one. The
    response is immediate; the caller polls /api/status to track progress.
    """
    global _pipeline_thread

    # Refuse to start if the user hasn't finished setup. The frontend's
    # routing should prevent this, but a direct caller (curl, a buggy
    # client state) shouldn't be able to trigger a run that's guaranteed
    # to fail when the agent code reaches for the missing key.
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise HTTPException(
            status_code=412,
            detail="Anthropic API key not configured. Complete first-run setup first.",
        )
    from backend.config import PROJECT_ROOT
    if not (PROJECT_ROOT / "credentials.json").exists():
        raise HTTPException(
            status_code=412,
            detail="Google credentials.json not found. Complete first-run setup first.",
        )

    with _pipeline_lock:
        current = read_status()
        if current and current["phase"] not in (
            Phase.IDLE.value,
            Phase.DONE.value,
            Phase.ERROR.value,
        ):
            raise HTTPException(
                status_code=409,
                detail=f"Pipeline already running (phase={current['phase']}).",
            )

        # Reset state and spawn the worker thread. We use a daemon thread
        # so if the user kills the server with Ctrl-C, the worker dies too
        # instead of holding the process open.
        write_status(
            phase=Phase.STARTING.value,
            message="Starting up...",
            current=0,
            total=0,
            started_at=time.time(),
        )
        _pipeline_thread = threading.Thread(
            target=_run_pipeline_in_thread, daemon=True
        )
        _pipeline_thread.start()

    return {"ok": True}


@app.get("/api/people")
def get_people():
    """
    Return the generated artifact. The frontend loads this once status flips
    to done. Returns 404 if the pipeline hasn't run yet, so the UI can show
    a friendly "no data" state instead of crashing on a parse error.
    """
    if not PEOPLE_PATH.exists():
        raise HTTPException(status_code=404, detail="No artifact yet. Run the pipeline first.")
    with open(PEOPLE_PATH) as f:
        return JSONResponse(content=json.load(f))


@app.get("/api/insights")
def get_insights():
    """
    Return top-level insights: forgotten threads, upcoming meetings,
    about-you stats. These are nice-to-haves layered on top of the
    per-person wiki, so a missing file is not an error; the frontend
    simply doesn't render the dashboard surfaces.
    """
    from backend.config import OUTPUT_DIR
    insights_path = OUTPUT_DIR / "insights.json"
    if not insights_path.exists():
        # Empty shape rather than 404 so the frontend doesn't have to
        # branch on HTTP status for what is genuinely a "no data yet"
        # state.
        return JSONResponse(content={
            "forgotten": [],
            "upcoming": [],
            "about_you": {},
        })
    with open(insights_path) as f:
        return JSONResponse(content=json.load(f))


@app.get("/api/account")
def get_account():
    """
    Return the email of the currently-authenticated Google account, or null
    if no valid token is on disk. The frontend uses this to show "Connected
    as foo@gmail.com" on the Setup screen and Wiki so the user always knows
    which account they're about to run against.

    We resolve the email by calling Google's userinfo endpoint via our
    existing helper. If the token is missing, expired without a refresh
    token, or revoked, we return null and let the caller render an
    appropriate "not connected" state rather than 500-ing.
    """
    settings = get_settings()
    if not Path(settings.google_token_path).exists():
        return {"email": None}
    try:
        # Local import keeps the api module light at startup; this path
        # is only hit when the frontend asks about the account.
        from backend.clients.gmail import get_credentials, get_my_email
        creds = get_credentials(settings.google_credentials_path, settings.google_token_path)
        email = get_my_email(creds)
        return {"email": email}
    except Exception as e:
        # Token might be corrupt or revoked. Don't surface the traceback to
        # the UI; just say "not connected" so the user can re-auth.
        log.warning("could not resolve account email: %s", e)
        return {"email": None}


@app.get("/api/preflight")
def preflight():
    """
    Quick check for the two files a new user has to provide before clicking
    Begin: .env (with an Anthropic key) and credentials.json (Google OAuth
    client). We report each one's presence so the Setup screen can show a
    checklist instead of letting the user hit Begin and watch the pipeline
    explode on a missing key.

    We deliberately don't validate the *contents* of these files (e.g. we
    don't try to call the Anthropic API to verify the key works). That kind
    of check is slow and brittle; the cleaner UX is to let the pipeline
    fail fast with a clear error if the key is wrong, and only block
    upfront on the obvious "you forgot to create the file" case.
    """
    from backend.config import PROJECT_ROOT
    env_path = PROJECT_ROOT / ".env"
    creds_path = PROJECT_ROOT / "credentials.json"

    env_ok = env_path.exists()
    creds_ok = creds_path.exists()

    # Light sanity check: if .env exists, look for ANTHROPIC_API_KEY in it.
    # Doesn't validate the key works, just that the user remembered to set it.
    anthropic_key_set = False
    if env_ok:
        try:
            with open(env_path) as f:
                for line in f:
                    if line.strip().startswith("ANTHROPIC_API_KEY="):
                        value = line.split("=", 1)[1].strip().strip('"').strip("'")
                        if value and not value.startswith("sk-ant-..."):
                            anthropic_key_set = True
                        break
        except OSError:
            pass

    return {
        "env_file": env_ok,
        "credentials_file": creds_ok,
        "anthropic_key_set": anthropic_key_set,
        "ready": env_ok and creds_ok and anthropic_key_set,
    }


# --- First-run setup wizard endpoints ------------------------------------
#
# These power the in-app setup screen the brief asked for. The user
# pastes their Anthropic key and uploads their Google OAuth credentials
# right in the browser instead of editing files in a text editor. Both
# endpoints validate before writing, so a typo doesn't get persisted.


class AnthropicSetupRequest(BaseModel):
    api_key: str


class GoogleSetupRequest(BaseModel):
    credentials_json: str


@app.post("/api/setup/anthropic")
def setup_anthropic(req: AnthropicSetupRequest):
    """
    Save and validate an Anthropic API key.

    We make a tiny real API call (Haiku, max_tokens=5) to confirm the key
    actually works before writing it to .env. The alternative, "just save
    and let the pipeline fail later," wastes the user's time and leaves
    them debugging a 20-minute-deep failure when the real problem was a
    typo in their key. Costs effectively nothing per validation.

    If .env already exists with other settings, we update only the
    ANTHROPIC_API_KEY line and leave the rest intact.
    """
    key = (req.api_key or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="API key cannot be empty.")
    if not key.startswith("sk-ant-"):
        raise HTTPException(
            status_code=400,
            detail="That doesn't look like an Anthropic key. They start with sk-ant-.",
        )

    # Real validation: make a tiny API call. Haiku is cheap (sub-cent) and
    # fast (sub-second). If the key is bad we get a 401 immediately.
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=key)
        client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=5,
            messages=[{"role": "user", "content": "Hi"}],
        )
    except anthropic.AuthenticationError:
        raise HTTPException(
            status_code=400,
            detail="Anthropic rejected this key. Double-check you copied it correctly.",
        )
    except anthropic.PermissionDeniedError:
        raise HTTPException(
            status_code=400,
            detail="This key doesn't have permission to use Claude Haiku 4.5. "
            "Check your Anthropic console for usage restrictions.",
        )
    except Exception as e:
        # Network errors, rate limits, etc. The key might be fine but we
        # can't be sure. We refuse to save until we can confirm it works.
        log.warning("anthropic key validation failed: %s", e)
        raise HTTPException(
            status_code=502,
            detail=f"Couldn't reach Anthropic to validate the key: {e}. "
            "Check your internet connection and try again.",
        )

    # Write to .env. Preserve other lines if the file already exists.
    from backend.config import PROJECT_ROOT
    env_path = PROJECT_ROOT / ".env"
    lines = []
    found = False
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                if line.strip().startswith("ANTHROPIC_API_KEY="):
                    lines.append(f"ANTHROPIC_API_KEY={key}\n")
                    found = True
                else:
                    lines.append(line)
    if not found:
        lines.append(f"ANTHROPIC_API_KEY={key}\n")

    with open(env_path, "w") as f:
        f.writelines(lines)

    # Make sure the new settings object picks up the change. Our settings
    # are cached via lru_cache, so we need to invalidate.
    get_settings.cache_clear()

    log.info("anthropic API key saved and validated")
    return {"ok": True}


@app.post("/api/setup/google")
def setup_google(req: GoogleSetupRequest):
    """
    Save and validate a Google OAuth client credentials JSON.

    The user downloads credentials.json from Google Cloud Console (Desktop
    app OAuth client) and pastes the contents here. We parse it, confirm
    it's a recognizable shape, and write it to credentials.json in the
    project root.

    Validation is structural only: we check the JSON parses and contains
    the expected "installed" or "web" client block. We don't try to start
    an OAuth flow here because that would require the user to actually
    sign in, which belongs in the pipeline run, not setup.
    """
    raw = (req.credentials_json or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="credentials.json content cannot be empty.")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=400,
            detail=f"That's not valid JSON: {e.msg}. Make sure you pasted the entire file.",
        )

    # Google's OAuth client JSON has a top-level "installed" (Desktop) or
    # "web" key. We want Desktop (we'll fail later if they gave us web,
    # since our flow uses InstalledAppFlow.run_local_server). Catch the
    # common mix-up upfront.
    if "installed" in data:
        client_block = data["installed"]
        client_type = "installed"
    elif "web" in data:
        raise HTTPException(
            status_code=400,
            detail="This looks like a Web OAuth client. TwinMind needs a Desktop client. "
            "In Google Cloud Console, create credentials with Application type = Desktop app.",
        )
    else:
        raise HTTPException(
            status_code=400,
            detail="This doesn't look like a Google OAuth credentials.json file. "
            "Expected a top-level 'installed' key.",
        )

    # The block must have client_id and client_secret to be useful.
    missing = [k for k in ("client_id", "client_secret") if not client_block.get(k)]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"OAuth client is missing required fields: {', '.join(missing)}",
        )

    # Write to credentials.json.
    from backend.config import PROJECT_ROOT
    creds_path = PROJECT_ROOT / "credentials.json"
    with open(creds_path, "w") as f:
        json.dump(data, f, indent=2)
    # Restrict permissions; the file contains secrets.
    try:
        creds_path.chmod(0o600)
    except OSError:
        # Windows doesn't have POSIX chmod; not fatal.
        pass

    log.info("google OAuth credentials saved (client_type=%s)", client_type)
    return {"ok": True}


@app.post("/api/reset")
def reset_pipeline(switch_account: bool = False):
    """
    Clear pipeline state so the user can start over. By default we keep the
    message cache and OAuth token: the user just wants to re-run with their
    same account, and reusing the cache makes the next run ~2 minutes
    instead of 25.

    Pass switch_account=true to also delete the OAuth token (forcing the
    Google consent popup on the next run) and the message cache (so we
    start completely fresh). This is what you want when handing the app to
    a different person to try.

    Refuses to reset if a pipeline is actively running, so the user can't
    rip state out from under a working job.
    """
    current = read_status()
    if current and current["phase"] not in (
        Phase.IDLE.value,
        Phase.DONE.value,
        Phase.ERROR.value,
    ):
        raise HTTPException(
            status_code=409,
            detail=f"Pipeline is running (phase={current['phase']}). Wait for it to finish.",
        )

    # Always clear status and the output artifacts. These are the
    # run-specific bits that gate the UI between setup/progress/wiki
    # views. We also remove insights.json so the dashboard surfaces
    # don't get stuck rendering data from the previous run.
    STATUS_PATH.unlink(missing_ok=True)
    PEOPLE_PATH.unlink(missing_ok=True)
    from backend.config import OUTPUT_DIR
    (OUTPUT_DIR / "insights.json").unlink(missing_ok=True)

    if switch_account:
        # Also nuke the message cache and OAuth token. The cache is keyed on
        # the user's own email; reusing it across accounts would mix data.
        # And the token must go so Google prompts for consent on the new
        # account next run.
        from backend.config import DB_PATH
        settings = get_settings()
        DB_PATH.unlink(missing_ok=True)
        token_path = Path(settings.google_token_path)
        token_path.unlink(missing_ok=True)

    return {"ok": True, "switch_account": switch_account}


# --- pipeline driver ---------------------------------------------------------


def _run_pipeline_in_thread() -> None:
    """
    Run the full pipeline (ingest -> deep fetch -> agents -> compose) in
    this thread, updating output/status.json after each phase. The actual
    business logic lives in backend/pipeline.py; this function only does
    the orchestration and error handling.

    Why a separate thread instead of an async task? The pipeline calls
    blocking libraries (googleapiclient, anthropic) that don't release the
    event loop. Running it in a thread is the simplest way to keep the
    FastAPI event loop responsive for status polls.
    """
    try:
        import asyncio

        # Imported here, not at module top, so the API process doesn't
        # eagerly load the heavy clients (gmail, calendar, anthropic) at
        # startup when all someone wants is to GET /api/status.
        from backend.clients.gmail import get_credentials
        from backend.pipeline import run_pipeline, EmptyInboxError
        from backend.storage.ingest import ingest_recent_window, ingest_calendar
        from backend.storage.db import init_db
        from backend.config import DB_PATH, ensure_dirs

        setup_logging("INFO")
        settings = get_settings()
        ensure_dirs()
        init_db(DB_PATH)

        write_status(phase=Phase.AUTH.value, message="Connecting to your Google account...")
        creds = get_credentials(settings.google_credentials_path, settings.google_token_path)

        write_status(
            phase=Phase.INGEST.value,
            message="Reading recent emails from Gmail...",
        )
        ingest_recent_window(creds, settings, DB_PATH)
        ingest_calendar(creds, DB_PATH)

        # Translate pipeline.emit() events into user-facing status messages.
        # The pipeline emits coarse stages ("ranking", "deep_fetch", "agents",
        # "done"); we map each to a friendly sentence + a current/total pair
        # the frontend can render as a progress bar.
        def on_progress(event: dict) -> None:
            stage = event.get("stage", "")
            current = event.get("current", 0)
            total = event.get("total", 0)
            raw = event.get("message", "")

            if stage == "ranking":
                msg = "Finding your most important people..."
            elif stage == "deep_fetch":
                msg = f"Reading conversation history ({current}/{total})..."
            elif stage == "agents":
                if current == 0:
                    msg = "Writing pages for your people..."
                else:
                    msg = f"Building pages ({current}/{total})..."
            elif stage == "done":
                msg = "Wrapping up..."
            else:
                msg = raw

            write_status(
                phase=Phase.GENERATE.value,
                message=msg,
                current=current,
                total=total,
            )

        # asyncio.run creates a fresh event loop in this thread, runs the
        # async pipeline to completion, then tears the loop down. Threads
        # don't share event loops, so this is the correct pattern.
        asyncio.run(run_pipeline(
            creds=creds,
            settings=settings,
            db_path=DB_PATH,
            output_path=PEOPLE_PATH,
            progress_callback=on_progress,
        ))

        write_status(
            phase=Phase.DONE.value,
            message=f"Done. Pages ready for your top {settings.top_n_people} people.",
            current=settings.top_n_people,
            total=settings.top_n_people,
            finished_at=time.time(),
        )

    except EmptyInboxError as e:
        # Not a crash; the inbox just doesn't have any humans to write
        # about. Show a friendly empty-state instead of a traceback.
        log.info("pipeline finished with empty-inbox state: %s", e)
        write_status(
            phase=Phase.ERROR.value,
            message=str(e),
            error="EMPTY_INBOX",
            finished_at=time.time(),
        )

    except Exception as e:
        # Capture the traceback so we can show it in the UI; printing it
        # to the log too is helpful for the developer running locally.
        tb = traceback.format_exc()
        log.error("pipeline failed: %s\n%s", e, tb)
        write_status(
            phase=Phase.ERROR.value,
            message=f"Something went wrong: {e}",
            error=tb,
            finished_at=time.time(),
        )


# --- static file serving -----------------------------------------------------
# Serve the built React frontend from frontend/dist. This is what makes the
# "one command, browser opens, done" experience work. In dev, `npm run dev`
# runs Vite on :5173 and proxies /api/* to us; this static mount is for the
# production build (`npm run build` writes to frontend/dist).

_FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"

if _FRONTEND_DIST.exists():
    # The order matters: mount /api routes BEFORE this catch-all, otherwise
    # the static handler swallows API requests. FastAPI declarations above
    # are already registered, so this is safe to mount last.
    app.mount("/assets", StaticFiles(directory=_FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str):
        """
        SPA fallback: any non-API path returns index.html so React Router
        (or our equivalent) can handle the route on the client. Doesn't
        intercept /api/* because those are registered above this catch-all.
        """
        index = _FRONTEND_DIST / "index.html"
        if not index.exists():
            raise HTTPException(status_code=404, detail="Frontend not built. Run `npm run build` in frontend/.")
        return FileResponse(index)

else:
    @app.get("/")
    def no_frontend_built():
        return JSONResponse(
            status_code=503,
            content={
                "error": "Frontend not built yet.",
                "hint": "From the frontend/ directory: `npm install && npm run build`. "
                        "Then refresh.",
            },
        )
