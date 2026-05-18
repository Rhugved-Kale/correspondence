import { RefreshCw, RotateCcw, Inbox } from "lucide-react";

/**
 * Progress view rendered while the pipeline runs.
 *
 * Phases are coarse: auth -> ingest -> generate -> done. For ingest and
 * generate we get true current/total counts from the backend, so we show
 * a real progress bar. For auth and starting we have no enumerable work,
 * so we show an indeterminate shimmer.
 *
 * Copy is intentionally calm and present-tense. Avoid marketing-y verbs
 * ("Crunching!") that would feel out of place in this editorial design.
 *
 * Three error modes:
 *   - No error                : in-progress UI with bar + timer
 *   - error === "EMPTY_INBOX" : friendly empty-state (your inbox has no
 *                                humans to write about). Common case for
 *                                fresh accounts or notification-only inboxes;
 *                                NOT a crash.
 *   - any other error string  : generic error UI with traceback for debug.
 */
export default function ProgressView({
  status,
  error,
  elapsed,
  onTryAgain,
  onReset,
}) {
  const serif = `'Fraunces', 'Iowan Old Style', Palatino, Georgia, serif`;

  const phase = status?.phase || "starting";
  const message = status?.message || "Starting up...";
  const current = status?.current || 0;
  const total = status?.total || 0;

  // Empty inbox is its own surface, not a crash.
  const isEmptyInbox = error === "EMPTY_INBOX";

  if (isEmptyInbox) {
    return (
      <EmptyInboxView
        message={message}
        onTryAgain={onTryAgain}
        onSwitchAccount={() => onReset(true)}
        serif={serif}
      />
    );
  }

  const phaseLabel = labelFor(phase);
  const hasDeterminateBar = total > 0;
  const pct = hasDeterminateBar
    ? Math.min(100, Math.round((current / total) * 100))
    : 0;

  return (
    <div
      className="min-h-screen w-full flex items-center justify-center px-6"
      style={{ background: "#FAF8F4", color: "#1A1815" }}
    >
      <div className="max-w-xl w-full py-16">
        <div className="flex items-center gap-2 mb-10">
          <span
            className="w-2 h-2 rounded-full animate-pulse"
            style={{ background: error ? "#A6452F" : "#3D3A8E" }}
          />
          <span
            className="text-[11px] uppercase tracking-[0.22em] font-semibold"
            style={{ color: error ? "#7A371A" : "#272555" }}
          >
            {error ? "Something went wrong" : phaseLabel}
          </span>
        </div>

        <h1
          style={{
            fontFamily: serif,
            fontWeight: 500,
            fontSize: "clamp(32px, 5vw, 52px)",
            lineHeight: 1.08,
            letterSpacing: "-0.015em",
            color: "#15110D",
            minHeight: "1.5em",
          }}
        >
          {error ? "We hit a snag." : message}
        </h1>

        {!error && (
          <div className="mt-10">
            {hasDeterminateBar ? (
              <DeterminateBar pct={pct} current={current} total={total} />
            ) : (
              <IndeterminateBar />
            )}
            <p
              className="mt-6"
              style={{
                color: "#7A726A",
                fontSize: 14,
                fontVariantNumeric: "tabular-nums",
              }}
            >
              {formatElapsed(elapsed)} elapsed
              {phase === "ingest" || phase === "generate" ? (
                <span style={{ color: "#9B9088" }}>
                  {"  ·  "}Time varies with inbox size
                </span>
              ) : null}
            </p>
          </div>
        )}

        {error && (
          <div className="mt-8">
            <pre
              className="text-[12px] p-4 rounded-lg whitespace-pre-wrap overflow-x-auto"
              style={{
                background: "#F7E6E0",
                color: "#6E2D1E",
                maxHeight: 280,
                fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
              }}
            >
              {error}
            </pre>
            <p className="mt-4 text-sm" style={{ color: "#7A726A" }}>
              Check the terminal where you started the server for more detail.
            </p>

            <div className="mt-6 flex flex-wrap gap-3">
              <button
                onClick={onTryAgain}
                className="inline-flex items-center gap-2 px-5 py-2.5 rounded-full text-[13.5px] font-medium"
                style={{
                  fontFamily: serif,
                  background: "#15110D",
                  color: "#FAF8F4",
                  cursor: "pointer",
                }}
              >
                <RefreshCw size={14} />
                Try again
              </button>
              <button
                onClick={() => onReset(false)}
                className="inline-flex items-center gap-2 px-5 py-2.5 rounded-full text-[13.5px] font-medium"
                style={{
                  fontFamily: serif,
                  background: "#FFFFFF",
                  color: "#15110D",
                  border: "1px solid #E5DFD3",
                  cursor: "pointer",
                }}
              >
                <RotateCcw size={14} />
                Start over
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}


function EmptyInboxView({ message, onTryAgain, onSwitchAccount, serif }) {
  return (
    <div
      className="min-h-screen w-full flex items-center justify-center px-6"
      style={{ background: "#FAF8F4", color: "#1A1815" }}
    >
      <div className="max-w-xl w-full py-16">
        <div className="flex items-center gap-2 mb-10">
          <span
            className="w-2 h-2 rounded-full"
            style={{ background: "#A8945A" }}
          />
          <span
            className="text-[11px] uppercase tracking-[0.22em] font-semibold"
            style={{ color: "#7A6840" }}
          >
            Nothing to summarize yet
          </span>
        </div>

        <div
          className="flex items-center justify-center mb-8"
          style={{
            width: 64, height: 64, borderRadius: 16,
            background: "#F4EFE0", color: "#A8945A",
          }}
        >
          <Inbox size={28} strokeWidth={1.8} />
        </div>

        <h1
          style={{
            fontFamily: serif,
            fontWeight: 500,
            fontSize: "clamp(32px, 5vw, 48px)",
            lineHeight: 1.08,
            letterSpacing: "-0.015em",
            color: "#15110D",
          }}
        >
          This inbox is quiet.
        </h1>

        <p
          className="mt-5 max-w-[480px]"
          style={{ fontSize: 16.5, lineHeight: 1.6, color: "#5C544A" }}
        >
          {message}
        </p>

        <p
          className="mt-4 max-w-[480px]"
          style={{ fontSize: 14, lineHeight: 1.55, color: "#7A726A" }}
        >
          We checked your messages but couldn&rsquo;t find enough real
          back-and-forth with other humans to build pages. This happens
          with brand-new accounts or inboxes that mostly receive
          notifications and receipts.
        </p>

        <div className="mt-8 flex flex-wrap gap-3">
          <button
            onClick={onSwitchAccount}
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-full text-[13.5px] font-medium"
            style={{
              fontFamily: serif,
              background: "#15110D",
              color: "#FAF8F4",
              cursor: "pointer",
            }}
          >
            <RotateCcw size={14} />
            Try a different account
          </button>
          <button
            onClick={onTryAgain}
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-full text-[13.5px] font-medium"
            style={{
              fontFamily: serif,
              background: "#FFFFFF",
              color: "#15110D",
              border: "1px solid #E5DFD3",
              cursor: "pointer",
            }}
          >
            <RefreshCw size={14} />
            Try again
          </button>
        </div>
      </div>
    </div>
  );
}


function DeterminateBar({ pct, current, total }) {
  return (
    <>
      <div
        className="w-full overflow-hidden"
        style={{ height: 6, borderRadius: 999, background: "#EAE5DC" }}
      >
        <div
          style={{
            height: "100%",
            width: `${pct}%`,
            background: "#3D3A8E",
            borderRadius: 999,
            transition: "width 600ms ease-out",
          }}
        />
      </div>
      <p
        className="mt-3"
        style={{
          color: "#7A726A",
          fontSize: 13.5,
          fontVariantNumeric: "tabular-nums",
        }}
      >
        {current.toLocaleString()} of {total.toLocaleString()}
      </p>
    </>
  );
}


function IndeterminateBar() {
  // CSS-only sliding shimmer. We don't have current/total for this phase
  // so we render a 30%-wide bar oscillating left/right. Pure CSS keeps
  // this lightweight and accessibility-friendly (no JS frame loop).
  return (
    <>
      <style>{`
        @keyframes twinmind-slide {
          0%   { transform: translateX(-100%); }
          100% { transform: translateX(330%); }
        }
      `}</style>
      <div
        className="w-full overflow-hidden"
        style={{ height: 6, borderRadius: 999, background: "#EAE5DC" }}
      >
        <div
          style={{
            width: "30%",
            height: "100%",
            background: "#3D3A8E",
            borderRadius: 999,
            animation: "twinmind-slide 1.8s ease-in-out infinite",
          }}
        />
      </div>
    </>
  );
}


function labelFor(phase) {
  switch (phase) {
    case "starting": return "Starting";
    case "auth":     return "Authorizing";
    case "ingest":   return "Reading email";
    case "generate": return "Building your pages";
    case "done":     return "Done";
    case "error":    return "Error";
    default:         return "Working";
  }
}


function formatElapsed(seconds) {
  if (!seconds || seconds < 1) return "0:00";
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}
