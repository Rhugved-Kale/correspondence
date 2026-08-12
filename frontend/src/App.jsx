import { useEffect, useRef, useState } from "react";
import PeopleWiki from "./components/PeopleWiki.jsx";
import SetupScreen from "./SetupScreen.jsx";
import SetupWizard from "./SetupWizard.jsx";
import ProgressView from "./ProgressView.jsx";

/**
 * Top-level coordinator. Polls /api/status every second to decide which
 * screen to show:
 *
 *   idle / done-but-no-data  -> SetupScreen (with start button)
 *   starting / auth / ingest / generate  -> ProgressView
 *   done + people.json exists -> PeopleWiki
 *   error -> ProgressView in error mode
 *
 * Account info and preflight checks are fetched once when SetupScreen
 * mounts, refreshed after a reset, and re-fetched once the pipeline
 * finishes (so the Wiki view can show "Connected as ...").
 *
 * Polling interval is 1s. The pipeline takes ~25 min so sub-second
 * precision is unnecessary; we use setTimeout chaining instead of
 * setInterval so a slow status response can't pile up overlapping
 * requests.
 */
// Demo build. When VITE_DEMO is set the app skips the API and the whole
// setup/progress flow and reads prebuilt JSON, because the public demo has
// no backend to talk to. Imported rather than fetched so there is no
// loading flash on a cold visit.
const DEMO = import.meta.env.VITE_DEMO === "1";


export default function App() {
  const [status, setStatus] = useState(null);
  const [demoData, setDemoData] = useState(null);
  const [people, setPeople] = useState(null);
  const [insights, setInsights] = useState(null);
  const [account, setAccount] = useState(null);
  const [preflight, setPreflight] = useState(null);
  const [starting, setStarting] = useState(false);
  const [elapsed, setElapsed] = useState(0);

  // Elapsed timer runs at 1Hz, independent of status polls, so the
  // counter is smooth instead of lurching.
  const startedAtRef = useRef(null);
  useEffect(() => {
    if (status?.started_at && !status?.finished_at) {
      startedAtRef.current = status.started_at * 1000;
    } else {
      startedAtRef.current = null;
    }
  }, [status?.started_at, status?.finished_at]);

  useEffect(() => {
    const id = setInterval(() => {
      if (startedAtRef.current) {
        setElapsed(Math.floor((Date.now() - startedAtRef.current) / 1000));
      }
    }, 1000);
    return () => clearInterval(id);
  }, []);

  // Demo data load. Static files, served from the build.
  useEffect(() => {
    if (!DEMO) return;
    (async () => {
      try {
        const [people, insights, config] = await Promise.all([
          fetch("/output/people.json").then((r) => r.json()),
          fetch("/output/insights.json").then((r) => r.json()),
          fetch("/demo/config.json").then((r) => r.json()).catch(() => ({})),
        ]);
        setDemoData({ people, insights, config });
      } catch (e) {
        console.error("demo data load failed:", e);
      }
    })();
  }, []);

  // Status poll loop.
  useEffect(() => {
    if (DEMO) return;
    let cancelled = false;
    let timeoutId;
    async function poll() {
      try {
        const resp = await fetch("/api/status");
        if (resp.ok) {
          const data = await resp.json();
          if (!cancelled) setStatus(data);
        }
      } catch (e) {
        console.warn("status poll failed:", e);
      }
      if (!cancelled) timeoutId = setTimeout(poll, 1000);
    }
    poll();
    return () => {
      cancelled = true;
      clearTimeout(timeoutId);
    };
  }, []);

  // Load account + preflight once on mount, and re-fetch them when the
  // phase flips back to idle (after a reset). This is what keeps the
  // Setup screen accurate when the user switches accounts.
  async function fetchAccountAndPreflight() {
    // Demo builds have no backend. Without this guard the demo fires
    // /api/account and /api/preflight on every mount and logs a pair of
    // 500s in the console of a page that is otherwise entirely static.
    if (DEMO) return;
    try {
      const [accountResp, preflightResp] = await Promise.all([
        fetch("/api/account"),
        fetch("/api/preflight"),
      ]);
      if (accountResp.ok) setAccount(await accountResp.json());
      if (preflightResp.ok) setPreflight(await preflightResp.json());
    } catch (e) {
      console.warn("could not load account/preflight:", e);
    }
  }

  useEffect(() => {
    fetchAccountAndPreflight();
  }, []);

  useEffect(() => {
    // Re-fetch when transitioning into idle (post-reset) or done states.
    if (status?.phase === "idle" || status?.phase === "done") {
      fetchAccountAndPreflight();
    }
  }, [status?.phase]);

  // Load people.json and insights.json once the pipeline finishes.
  // Insights is optional: if it fails or returns empty, the wiki still
  // renders, just without the dashboard surfaces.
  useEffect(() => {
    if (status?.phase === "done" && people === null) {
      (async () => {
        try {
          const [peopleResp, insightsResp] = await Promise.all([
            fetch("/api/people"),
            fetch("/api/insights"),
          ]);
          if (peopleResp.ok) setPeople(await peopleResp.json());
          if (insightsResp.ok) setInsights(await insightsResp.json());
        } catch (e) {
          console.error("failed to load people/insights:", e);
        }
      })();
    }
  }, [status?.phase, people]);

  async function handleStart() {
    setStarting(true);
    try {
      const resp = await fetch("/api/start", { method: "POST" });
      if (!resp.ok) {
        const detail = await resp.json().catch(() => ({}));
        alert(`Could not start: ${detail.detail || resp.statusText}`);
      }
    } catch (e) {
      alert(`Could not start: ${e.message}`);
    } finally {
      setTimeout(() => setStarting(false), 1200);
    }
  }

  async function handleReset(switchAccount) {
    const url = `/api/reset${switchAccount ? "?switch_account=true" : ""}`;
    try {
      const resp = await fetch(url, { method: "POST" });
      if (!resp.ok) {
        const detail = await resp.json().catch(() => ({}));
        alert(`Could not reset: ${detail.detail || resp.statusText}`);
        return;
      }
      // Drop local state immediately so we don't wait for the next poll.
      setPeople(null);
      setInsights(null);
      setStatus({ phase: "idle", message: "", current: 0, total: 0, error: null });
      // Refresh account info: if we did a switch_account reset, the token
      // is gone so we'll show "you'll be asked to sign in" on Setup.
      fetchAccountAndPreflight();
    } catch (e) {
      alert(`Could not reset: ${e.message}`);
    }
  }

  // "Try again" on the error screen: clear the error status and restart.
  // We don't blow away the cache (so any partial ingestion still counts);
  // just reset the status file and re-fire /api/start.
  async function handleTryAgain() {
    await handleReset(false);
    // Tiny delay so the reset propagates before /api/start fires.
    setTimeout(() => handleStart(), 300);
  }

  // Demo build renders the artifact directly. No polling, no setup, no
  // progress: there is nothing to wait for.
  if (DEMO) {
    if (!demoData) return <BlankSplash />;
    return (
      <PeopleWiki
        people={demoData.people}
        insights={demoData.insights}
        landingPersonId={demoData.config?.landing_person_id}
        demoUrl={demoData.config?.demo_url}
      />
    );
  }

  // Decide what to render.
  if (status === null) return <BlankSplash />;

  const phase = status.phase;

  if (phase === "done" && people !== null) {
    return (
      <>
        <PeopleWiki people={people} insights={insights} />
        <WikiOverlay
          account={account}
          onReset={handleReset}
          finishedAt={status?.finished_at}
        />
      </>
    );
  }

  if (phase === "idle" || (phase === "done" && people === null)) {
    // If the user hasn't completed first-run setup yet (no Anthropic key
    // saved or no credentials.json present), show the wizard instead of
    // the regular Setup screen. Once both are saved, we let them proceed.
    const needsWizard = preflight && !preflight.ready;
    if (needsWizard) {
      return (
        <SetupWizard
          preflight={preflight}
          onComplete={fetchAccountAndPreflight}
          onContinue={fetchAccountAndPreflight}
        />
      );
    }
    return (
      <SetupScreen
        onStart={handleStart}
        starting={starting}
        account={account}
        preflight={preflight}
      />
    );
  }

  return (
    <ProgressView
      status={status}
      error={phase === "error" ? status.error : null}
      elapsed={elapsed}
      onTryAgain={handleTryAgain}
      onReset={handleReset}
    />
  );
}


function BlankSplash() {
  return <div className="min-h-screen w-full" style={{ background: "#FAF8F4" }} />;
}


/**
 * Overlay rendered on top of the Wiki view. Holds:
 *   - "Connected as ..." chip (top-left)
 *   - "Start over" menu (top-left, next to the chip)
 *
 * Anchored to the LEFT corner so it doesn't compete with PeopleWiki's
 * own "Share card" button in the top-right. Both elements sit in the
 * same horizontal row so they look like one cohesive bar.
 */
function WikiOverlay({ account, onReset, finishedAt }) {
  return (
    <div
      // Mobile: no sidebar, so tuck against the left edge.
      // md+: sidebar is 280px wide, so offset by 296px (280 + 16) so the
      // overlay sits cleanly within the main content area instead of
      // overlapping the people list.
      className="fixed top-6 left-6 md:left-[296px] z-50 flex items-center gap-2"
      style={{ fontFamily: "ui-sans-serif, system-ui, sans-serif" }}
    >
      {account?.email && (
        <AccountChip email={account.email} finishedAt={finishedAt} />
      )}
      <ResetMenuButton onReset={onReset} />
    </div>
  );
}


function AccountChip({ email, finishedAt }) {
  const freshness = useFreshness(finishedAt);
  return (
    <div
      className="px-3 py-2 rounded-full text-[12px] flex items-center gap-2"
      style={{
        background: "rgba(255,255,255,0.85)",
        color: "#5C544A",
        border: "1px solid #E5DFD3",
        backdropFilter: "blur(8px)",
        maxWidth: 340,
      }}
      title={`Signed in as ${email}${freshness ? `, last refreshed ${freshness}` : ""}`}
    >
      <span className="truncate" style={{ maxWidth: 200 }}>
        {email}
      </span>
      {freshness && (
        <>
          <span style={{ color: "#C7C0B5" }}>·</span>
          <span style={{ color: "#7A726A", whiteSpace: "nowrap" }}>
            refreshed {freshness}
          </span>
        </>
      )}
    </div>
  );
}


/**
 * Tracks a "X ago" relative time string for a given unix timestamp.
 * Rerenders every 60 seconds so a "just now" eventually becomes "1m ago".
 * Returns null if finishedAt isn't set yet (pipeline still running).
 */
function useFreshness(finishedAt) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 60_000);
    return () => clearInterval(id);
  }, []);
  if (!finishedAt) return null;
  const ageMs = now - finishedAt * 1000;
  const m = Math.floor(ageMs / 60_000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  if (d < 7) return `${d}d ago`;
  const w = Math.floor(d / 7);
  return `${w}w ago`;
}


/**
 * "Start over" menu. Reveals two options on click: re-run on the same
 * account, or fully switch accounts. Closes on Escape or outside click.
 */
function ResetMenuButton({ onReset }) {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    function handleEsc(e) {
      if (e.key === "Escape") setOpen(false);
    }
    function handleClick(e) {
      if (!e.target.closest("[data-reset-menu]")) setOpen(false);
    }
    window.addEventListener("keydown", handleEsc);
    window.addEventListener("click", handleClick);
    return () => {
      window.removeEventListener("keydown", handleEsc);
      window.removeEventListener("click", handleClick);
    };
  }, [open]);

  async function confirmAndReset(switchAccount) {
    const msg = switchAccount
      ? "This will delete your cached emails and sign you out. Continue?"
      : "This will start a fresh run on the same account. Continue?";
    if (!window.confirm(msg)) return;
    setOpen(false);
    await onReset(switchAccount);
  }

  return (
    <div data-reset-menu className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="px-4 py-2 rounded-full text-[12px] font-medium transition-colors"
        style={{
          background: open ? "#15110D" : "rgba(255,255,255,0.85)",
          color: open ? "#FAF8F4" : "#5C544A",
          border: "1px solid #E5DFD3",
          backdropFilter: "blur(8px)",
        }}
      >
        Start over
      </button>

      {open && (
        <div
          className="absolute top-full left-0 mt-2 rounded-xl shadow-lg overflow-hidden"
          style={{
            background: "#FFFFFF",
            border: "1px solid #E5DFD3",
            minWidth: 240,
          }}
        >
          <MenuItem
            label="Re-run on this account"
            sub="Refreshes pages from latest email"
            onClick={() => confirmAndReset(false)}
          />
          <div style={{ height: 1, background: "#E5DFD3" }} />
          <MenuItem
            label="Switch account"
            sub="Sign out and pick a different inbox"
            onClick={() => confirmAndReset(true)}
            danger
          />
        </div>
      )}
    </div>
  );
}


function MenuItem({ label, sub, onClick, danger }) {
  return (
    <button
      onClick={onClick}
      className="w-full text-left px-4 py-3 transition-colors hover:bg-stone-50"
      style={{ color: danger ? "#7A371A" : "#1A1815" }}
    >
      <div style={{ fontSize: 13, fontWeight: 500 }}>{label}</div>
      <div style={{ fontSize: 11.5, color: "#7A726A", marginTop: 2 }}>{sub}</div>
    </button>
  );
}
