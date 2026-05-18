import { useState } from "react";
import { Mail, Calendar, Sparkles, CheckCircle2, AlertCircle, User } from "lucide-react";

/**
 * Setup screen. First thing a new user sees.
 *
 * Three jobs:
 *   1. Explain what's about to happen.
 *   2. Show preflight status (.env, credentials.json) so a misconfigured
 *      install fails BEFORE the user clicks Begin, not after.
 *   3. Show which Google account is currently authenticated (if any) so
 *      the user knows what inbox the pipeline will run against.
 *
 * The visual register matches PeopleWiki: Fraunces serif for the headline,
 * stone/cream palette, generous spacing. No form fields here. The user
 * configures credentials in .env and credentials.json before launching;
 * this screen is just for context + the Begin button.
 */
export default function SetupScreen({ onStart, starting, account, preflight }) {
  const serif = `'Fraunces', 'Iowan Old Style', Palatino, Georgia, serif`;
  const [agreed, setAgreed] = useState(false);

  const preflightReady = preflight?.ready ?? false;
  const canBegin = agreed && !starting && preflightReady;

  return (
    <div
      className="min-h-screen w-full flex items-center justify-center px-6"
      style={{ background: "#FAF8F4", color: "#1A1815" }}
    >
      <div className="max-w-xl w-full py-16">
        <div className="flex items-center gap-2 mb-12">
          <span
            className="w-2 h-2 rounded-full"
            style={{ background: "#3D3A8E" }}
          />
          <span
            className="text-[11px] uppercase tracking-[0.22em] font-semibold"
            style={{ color: "#272555" }}
          >
            TwinMind preview
          </span>
        </div>

        <h1
          style={{
            fontFamily: serif,
            fontWeight: 500,
            fontSize: "clamp(40px, 6vw, 64px)",
            lineHeight: 1.04,
            letterSpacing: "-0.02em",
            color: "#15110D",
          }}
        >
          Pages about the people who matter to you, built from your inbox.
        </h1>

        <p
          className="mt-7 max-w-[480px]"
          style={{ fontSize: 18, lineHeight: 1.55, color: "#5C544A" }}
        >
          We&rsquo;ll read recent Gmail and your calendar, find the people you
          actually talk with, and write a short page for each one. The first
          run takes a while; later runs are quick.
        </p>

        <div className="mt-12 space-y-4">
          <Row
            icon={<Mail size={16} />}
            title="Reads your recent email"
            sub="180 days, locally cached on your machine"
          />
          <Row
            icon={<Calendar size={16} />}
            title="Notes who you meet with"
            sub="To bias toward people you actually see"
          />
          <Row
            icon={<Sparkles size={16} />}
            title="Writes a page for your top 10"
            sub="Timeline, stories, what to bring up next"
          />
        </div>

        {/* Preflight: show which prerequisites are met. Hidden entirely
            when everything is ready, since in that case the user has done
            this before and doesn't need reminding. */}
        {!preflightReady && (
          <div
            className="mt-10 px-5 py-4 rounded-xl"
            style={{ background: "#FFFFFF", border: "1px solid #E5DFD3" }}
          >
            <div
              className="text-[11px] uppercase tracking-[0.18em] mb-3 font-semibold"
              style={{ color: "#7A726A" }}
            >
              Before you begin
            </div>
            <PreflightItem
              ok={preflight?.env_file}
              label=".env file in project root"
              hint="Copy .env.example to .env and add your Anthropic key"
            />
            <PreflightItem
              ok={preflight?.anthropic_key_set}
              label="ANTHROPIC_API_KEY set in .env"
              hint="Get a key at console.anthropic.com"
            />
            <PreflightItem
              ok={preflight?.credentials_file}
              label="credentials.json in project root"
              hint="Download OAuth client from Google Cloud Console"
            />
          </div>
        )}

        {/* Account row: shows which Google account we'll run against.
            Subtle, but always present so the user is never surprised. */}
        {account?.email ? (
          <div
            className="mt-6 px-5 py-4 rounded-xl flex items-center gap-3"
            style={{ background: "#EDECF7", border: "1px solid #D4D2EB" }}
          >
            <User size={16} style={{ color: "#272555", flexShrink: 0 }} />
            <div className="flex-1 min-w-0">
              <div
                className="text-[11px] uppercase tracking-[0.18em] font-semibold"
                style={{ color: "#272555" }}
              >
                Connected as
              </div>
              <div
                className="truncate"
                style={{ fontSize: 14, color: "#15110D", marginTop: 1 }}
              >
                {account.email}
              </div>
            </div>
          </div>
        ) : preflightReady ? (
          <div
            className="mt-6 px-5 py-4 rounded-xl"
            style={{ background: "#FFFFFF", border: "1px solid #E5DFD3" }}
          >
            <div className="flex items-center gap-3">
              <User size={16} style={{ color: "#7A726A", flexShrink: 0 }} />
              <div style={{ fontSize: 13.5, color: "#5C544A" }}>
                You&rsquo;ll be asked to sign in with Google when you click Begin.
              </div>
            </div>
          </div>
        ) : null}

        <div className="mt-8">
          <label
            className="flex items-start gap-3 cursor-pointer select-none"
            style={{ color: "#5C544A", fontSize: 14, lineHeight: 1.5 }}
          >
            <input
              type="checkbox"
              checked={agreed}
              onChange={(e) => setAgreed(e.target.checked)}
              className="mt-1 cursor-pointer"
              style={{ accentColor: "#3D3A8E" }}
            />
            <span>
              I understand this app reads my email and calendar locally,
              processes them with Claude, and writes the result to my disk.
              Nothing is sent anywhere else.
            </span>
          </label>

          <button
            onClick={onStart}
            disabled={!canBegin}
            className="mt-8 inline-flex items-center gap-2 px-7 py-3.5 rounded-full text-[15px] font-medium transition-opacity"
            style={{
              fontFamily: serif,
              background: canBegin ? "#15110D" : "#C7C0B5",
              color: "#FAF8F4",
              cursor: canBegin ? "pointer" : "not-allowed",
            }}
          >
            {starting ? "Starting..." : "Begin"}
          </button>

          {!preflightReady && (
            <p
              className="mt-3 text-[12.5px]"
              style={{ color: "#9B6346" }}
            >
              Complete the setup steps above to enable Begin.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}


function Row({ icon, title, sub }) {
  return (
    <div className="flex items-start gap-4">
      <div
        className="flex items-center justify-center mt-0.5"
        style={{
          width: 32, height: 32, borderRadius: 8,
          background: "#EDECF7", color: "#272555",
          flexShrink: 0,
        }}
      >
        {icon}
      </div>
      <div>
        <div className="font-medium" style={{ color: "#1A1815", fontSize: 15 }}>
          {title}
        </div>
        <div style={{ color: "#7A726A", fontSize: 13.5, marginTop: 1 }}>
          {sub}
        </div>
      </div>
    </div>
  );
}


function PreflightItem({ ok, label, hint }) {
  return (
    <div className="flex items-start gap-3 py-2">
      <div className="mt-0.5" style={{ flexShrink: 0 }}>
        {ok ? (
          <CheckCircle2 size={16} style={{ color: "#3A8E4E" }} />
        ) : (
          <AlertCircle size={16} style={{ color: "#A6452F" }} />
        )}
      </div>
      <div className="flex-1 min-w-0">
        <div
          style={{
            fontSize: 13.5,
            color: ok ? "#3A553F" : "#7A371A",
            fontWeight: 500,
          }}
        >
          {label}
        </div>
        {!ok && (
          <div style={{ fontSize: 12, color: "#7A726A", marginTop: 1 }}>
            {hint}
          </div>
        )}
      </div>
    </div>
  );
}
