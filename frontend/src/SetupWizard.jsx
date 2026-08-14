import { useState } from "react";
import {
  CheckCircle2, AlertCircle, ChevronDown, ChevronRight,
  Key, Cloud, Loader2,
} from "lucide-react";

/**
 * First-run setup wizard.
 *
 * Shown when preflight reports either Anthropic key missing or Google
 * credentials.json missing. The user pastes their Anthropic key and the
 * contents of their downloaded credentials.json into two cards, hits
 * Save on each, and we validate + persist server-side before letting
 * them continue to the main flow.
 *
 * Why paste-text and not a file picker for credentials.json: file pickers
 * on macOS Safari can be finicky with non-extension-typed JSON, and a
 * text paste lets the user audit exactly what's about to be saved. They
 * just open the downloaded file in any text editor and copy. Works
 * identically on every platform.
 *
 * The wizard is intentionally accordion-style (only one card expanded at
 * a time) so the user is never overwhelmed by both unfamiliar tasks
 * shown at once. The Anthropic step is first because it's faster, gives
 * an immediate dopamine hit, and de-risks the longer Google setup.
 */
export default function SetupWizard({ preflight, onContinue, onComplete }) {
  const serif = `'Fraunces', 'Iowan Old Style', Palatino, Georgia, serif`;

  const anthropicSaved = !!preflight?.anthropic_key_set;
  const googleSaved = !!preflight?.credentials_file;
  const bothSaved = anthropicSaved && googleSaved;

  // Which card is expanded. Default: the first incomplete one. Once
  // saved, a card auto-collapses and we open the next one.
  const [openCard, setOpenCard] = useState(() => {
    if (!anthropicSaved) return "anthropic";
    if (!googleSaved) return "google";
    return null;
  });

  return (
    <div
      className="min-h-screen w-full flex items-center justify-center px-6"
      style={{ background: "#FAF8F4", color: "#1A1815" }}
    >
      <div className="max-w-2xl w-full py-16">
        <div className="flex items-center gap-2 mb-10">
          <span
            className="w-2 h-2 rounded-full"
            style={{ background: "#3D3A8E" }}
          />
          <span
            className="text-[11px] uppercase tracking-[0.22em] font-semibold"
            style={{ color: "#272555" }}
          >
            First-run setup
          </span>
        </div>

        <h1
          style={{
            fontFamily: serif,
            fontWeight: 500,
            fontSize: "clamp(36px, 5vw, 56px)",
            lineHeight: 1.05,
            letterSpacing: "-0.02em",
            color: "#15110D",
          }}
        >
          Two things, then we&rsquo;re off.
        </h1>

        <p
          className="mt-6 max-w-[520px]"
          style={{ fontSize: 17, lineHeight: 1.55, color: "#5C544A" }}
        >
          Correspondence runs on your machine and talks directly to your own
          accounts. Give it an Anthropic API key so it can write your
          pages, and a Google OAuth client so it can read your Gmail and
          calendar. Both stay on your laptop.
        </p>

        <div className="mt-12 space-y-4">
          <AnthropicCard
            saved={anthropicSaved}
            open={openCard === "anthropic"}
            onToggle={() => setOpenCard(openCard === "anthropic" ? null : "anthropic")}
            onSaved={() => {
              // Move focus to the next incomplete step.
              if (!googleSaved) setOpenCard("google");
              else setOpenCard(null);
              onComplete?.();
            }}
          />
          <GoogleCard
            saved={googleSaved}
            open={openCard === "google"}
            onToggle={() => setOpenCard(openCard === "google" ? null : "google")}
            onSaved={() => {
              setOpenCard(null);
              onComplete?.();
            }}
          />
        </div>

        <div className="mt-10">
          <button
            onClick={onContinue}
            disabled={!bothSaved}
            className="inline-flex items-center gap-2 px-7 py-3.5 rounded-full text-[15px] font-medium transition-opacity"
            style={{
              fontFamily: serif,
              background: bothSaved ? "#15110D" : "#C7C0B5",
              color: "#FAF8F4",
              cursor: bothSaved ? "pointer" : "not-allowed",
            }}
          >
            {bothSaved ? "Continue" : "Complete both steps to continue"}
          </button>
        </div>
      </div>
    </div>
  );
}


// --- Anthropic card ---------------------------------------------------------

function AnthropicCard({ saved, open, onToggle, onSaved }) {
  const [key, setKey] = useState("");
  const [showHow, setShowHow] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      const resp = await fetch("/api/setup/anthropic", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ api_key: key.trim() }),
      });
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        setError(data.detail || "Couldn't save the key. Please try again.");
      } else {
        setKey("");
        onSaved?.();
      }
    } catch (e) {
      setError(`Network error: ${e.message}`);
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card>
      <CardHeader
        icon={<Key size={16} />}
        title="Anthropic API key"
        sub="Powers the Claude agents that write your pages"
        saved={saved}
        open={open}
        onToggle={onToggle}
      />
      {open && !saved && (
        <div className="px-6 pb-6 pt-2">
          <input
            type="password"
            value={key}
            onChange={(e) => setKey(e.target.value)}
            placeholder="sk-ant-..."
            disabled={saving}
            className="w-full px-4 py-3 rounded-lg outline-none transition-colors"
            style={{
              background: "#FAF8F4",
              border: error ? "1px solid #A6452F" : "1px solid #E5DFD3",
              fontSize: 14,
              fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
              color: "#1A1815",
            }}
            onFocus={(e) => {
              if (!error) e.target.style.border = "1px solid #3D3A8E";
            }}
            onBlur={(e) => {
              if (!error) e.target.style.border = "1px solid #E5DFD3";
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && key.trim() && !saving) handleSave();
            }}
          />

          {error && (
            <div
              className="mt-3 flex items-start gap-2 text-[13px]"
              style={{ color: "#7A371A" }}
            >
              <AlertCircle size={14} className="mt-0.5 flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <div className="mt-4 flex items-center gap-3">
            <button
              onClick={handleSave}
              disabled={saving || !key.trim()}
              className="inline-flex items-center gap-2 px-5 py-2 rounded-full text-[13px] font-medium transition-opacity"
              style={{
                background: !key.trim() || saving ? "#C7C0B5" : "#15110D",
                color: "#FAF8F4",
                cursor: !key.trim() || saving ? "not-allowed" : "pointer",
              }}
            >
              {saving ? (
                <>
                  <Loader2 size={13} className="animate-spin" />
                  Verifying...
                </>
              ) : (
                "Save and validate"
              )}
            </button>
            <button
              onClick={() => setShowHow(!showHow)}
              className="inline-flex items-center gap-1 text-[12.5px]"
              style={{ color: "#7A726A" }}
            >
              {showHow ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
              How do I get one?
            </button>
          </div>

          {showHow && <AnthropicHowTo />}
        </div>
      )}
    </Card>
  );
}


function AnthropicHowTo() {
  return (
    <div
      className="mt-5 px-5 py-4 rounded-lg text-[13.5px]"
      style={{ background: "#FAF8F4", color: "#5C544A", lineHeight: 1.6 }}
    >
      <ol className="space-y-2" style={{ listStyle: "decimal", paddingLeft: 18 }}>
        <li>
          Go to{" "}
          <a
            href="https://console.anthropic.com"
            target="_blank"
            rel="noopener noreferrer"
            style={{ color: "#3D3A8E", textDecoration: "underline" }}
          >
            console.anthropic.com
          </a>{" "}
          and sign in.
        </li>
        <li>
          Click <strong>API Keys</strong> in the sidebar, then{" "}
          <strong>Create Key</strong>.
        </li>
        <li>
          Copy the key (starts with <code>sk-ant-</code>) and paste it above.
        </li>
      </ol>
      <div className="mt-3 text-[12.5px]" style={{ color: "#7A726A" }}>
        Cost per run: roughly $1. You can monitor usage from the same console.
      </div>
    </div>
  );
}


// --- Google card ------------------------------------------------------------

function GoogleCard({ saved, open, onToggle, onSaved }) {
  const [contents, setContents] = useState("");
  const [showHow, setShowHow] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      const resp = await fetch("/api/setup/google", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ credentials_json: contents.trim() }),
      });
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        setError(data.detail || "Couldn't save the credentials. Please try again.");
      } else {
        setContents("");
        onSaved?.();
      }
    } catch (e) {
      setError(`Network error: ${e.message}`);
    } finally {
      setSaving(false);
    }
  }

  async function handleFile(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const text = await file.text();
      setContents(text);
    } catch (err) {
      setError(`Couldn't read file: ${err.message}`);
    }
  }

  return (
    <Card>
      <CardHeader
        icon={<Cloud size={16} />}
        title="Google OAuth credentials"
        sub="Lets the app read your Gmail and calendar"
        saved={saved}
        open={open}
        onToggle={onToggle}
      />
      {open && !saved && (
        <div className="px-6 pb-6 pt-2">
          <p
            className="text-[13px] mb-3"
            style={{ color: "#7A726A", lineHeight: 1.5 }}
          >
            Upload your <code>credentials.json</code> file, or paste its
            contents below.
          </p>

          <label
            className="inline-flex items-center gap-2 cursor-pointer mb-3"
            style={{
              padding: "8px 14px",
              borderRadius: 8,
              background: "#FAF8F4",
              border: "1px solid #E5DFD3",
              color: "#5C544A",
              fontSize: 13,
            }}
          >
            <input
              type="file"
              accept=".json,application/json"
              onChange={handleFile}
              disabled={saving}
              className="hidden"
            />
            Choose file
          </label>

          <textarea
            value={contents}
            onChange={(e) => setContents(e.target.value)}
            placeholder='{"installed": {"client_id": "...", "client_secret": "...", ...}}'
            disabled={saving}
            rows={6}
            className="w-full px-4 py-3 rounded-lg outline-none transition-colors resize-y"
            style={{
              background: "#FAF8F4",
              border: error ? "1px solid #A6452F" : "1px solid #E5DFD3",
              fontSize: 12.5,
              fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
              color: "#1A1815",
              minHeight: 120,
            }}
            onFocus={(e) => {
              if (!error) e.target.style.border = "1px solid #3D3A8E";
            }}
            onBlur={(e) => {
              if (!error) e.target.style.border = "1px solid #E5DFD3";
            }}
          />

          {error && (
            <div
              className="mt-3 flex items-start gap-2 text-[13px]"
              style={{ color: "#7A371A" }}
            >
              <AlertCircle size={14} className="mt-0.5 flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <div className="mt-4 flex items-center gap-3 flex-wrap">
            <button
              onClick={handleSave}
              disabled={saving || !contents.trim()}
              className="inline-flex items-center gap-2 px-5 py-2 rounded-full text-[13px] font-medium transition-opacity"
              style={{
                background: !contents.trim() || saving ? "#C7C0B5" : "#15110D",
                color: "#FAF8F4",
                cursor: !contents.trim() || saving ? "not-allowed" : "pointer",
              }}
            >
              {saving ? (
                <>
                  <Loader2 size={13} className="animate-spin" />
                  Validating...
                </>
              ) : (
                "Save credentials"
              )}
            </button>
            <button
              onClick={() => setShowHow(!showHow)}
              className="inline-flex items-center gap-1 text-[12.5px]"
              style={{ color: "#7A726A" }}
            >
              {showHow ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
              How do I get this?
            </button>
          </div>

          {showHow && <GoogleHowTo />}
        </div>
      )}
    </Card>
  );
}


function GoogleHowTo() {
  return (
    <div
      className="mt-5 px-5 py-4 rounded-lg text-[13.5px]"
      style={{ background: "#FAF8F4", color: "#5C544A", lineHeight: 1.6 }}
    >
      <p style={{ marginBottom: 10 }}>
        Each user provides their own OAuth client because Google
        requires app-specific verification before unverified apps can
        request Gmail or Calendar access from arbitrary users. Setting
        this up takes about 10 minutes.
      </p>
      <ol className="space-y-2" style={{ listStyle: "decimal", paddingLeft: 18 }}>
        <li>
          Open{" "}
          <a
            href="https://console.cloud.google.com"
            target="_blank"
            rel="noopener noreferrer"
            style={{ color: "#3D3A8E", textDecoration: "underline" }}
          >
            console.cloud.google.com
          </a>{" "}
          while signed into the Google account whose Gmail you want to
          analyze.
        </li>
        <li>Create a new project (any name).</li>
        <li>
          <strong>APIs &amp; Services → Library:</strong> enable{" "}
          <strong>Gmail API</strong> and <strong>Google Calendar API</strong>.
        </li>
        <li>
          <strong>OAuth consent screen:</strong> choose <strong>External</strong>,
          fill in the app name and your email. Find the section called{" "}
          <strong>Test users</strong> (or <strong>Audience</strong> in the
          newer console) and add the email you&rsquo;re signed in with.
          Leave publishing as <strong>Testing</strong>.
        </li>
        <li>
          <strong>Credentials → Create Credentials → OAuth client ID:</strong>{" "}
          Application type <strong>Desktop app</strong>, any name. Click
          Create, then <strong>Download JSON</strong>.
        </li>
        <li>Paste the contents of that file above (or upload directly).</li>
      </ol>
    </div>
  );
}


// --- Shared card primitives -------------------------------------------------

function Card({ children }) {
  return (
    <div
      className="rounded-2xl overflow-hidden"
      style={{ background: "#FFFFFF", border: "1px solid #E5DFD3" }}
    >
      {children}
    </div>
  );
}


function CardHeader({ icon, title, sub, saved, open, onToggle }) {
  return (
    <button
      onClick={onToggle}
      disabled={saved}
      className="w-full px-6 py-5 flex items-center gap-4 text-left transition-colors"
      style={{ cursor: saved ? "default" : "pointer" }}
    >
      <div
        className="flex items-center justify-center flex-shrink-0"
        style={{
          width: 36, height: 36, borderRadius: 10,
          background: saved ? "#E0EDDB" : "#EDECF7",
          color: saved ? "#3A8E4E" : "#272555",
        }}
      >
        {saved ? <CheckCircle2 size={18} /> : icon}
      </div>
      <div className="flex-1 min-w-0">
        <div
          className="font-medium"
          style={{ color: "#1A1815", fontSize: 15 }}
        >
          {title}
        </div>
        <div style={{ color: "#7A726A", fontSize: 13, marginTop: 1 }}>
          {saved ? "Saved" : sub}
        </div>
      </div>
      {!saved && (
        <ChevronDown
          size={16}
          style={{
            color: "#7A726A",
            transform: open ? "rotate(180deg)" : "rotate(0)",
            transition: "transform 200ms",
          }}
        />
      )}
    </button>
  );
}
