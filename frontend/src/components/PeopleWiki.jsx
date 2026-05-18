import React, { useState, useMemo, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Calendar,
  Circle,
  Sparkles,
  Lightbulb,
  Compass,
  Heart,
  ArrowUpRight,
  Quote,
  Share2,
  Clock,
  X,
  Inbox,
  TrendingUp,
} from "lucide-react";

import InsightsDashboard from "./InsightsDashboard.jsx";


// ---------------------------------------------------------------------------
// Color system: deterministic accent per name. Each entry is a rich palette
// with hex values used across the page for backgrounds, borders, and text.
// ---------------------------------------------------------------------------
const ACCENT_PALETTE = [
  // deep indigo
  { name: "indigo", solid: "#3D3A8E", soft: "#EDECF7", tint: "#F7F6FC", ink: "#272555" },
  // burnt orange
  { name: "orange", solid: "#B8542A", soft: "#FBEDE3", tint: "#FDF7F2", ink: "#7A371A" },
  // forest
  { name: "forest", solid: "#2F5D4F", soft: "#E6EFEC", tint: "#F3F7F5", ink: "#1F3D34" },
  // plum
  { name: "plum", solid: "#6E3454", soft: "#F1E5EC", tint: "#F8F1F5", ink: "#4A2238" },
  // teal
  { name: "teal", solid: "#2A6F7A", soft: "#E3EFF1", tint: "#F2F8F9", ink: "#1B484F" },
  // terracotta
  { name: "terracotta", solid: "#A6452F", soft: "#F7E6E0", tint: "#FBF3EF", ink: "#6E2D1E" },
  // ochre
  { name: "ochre", solid: "#8A6A1F", soft: "#F3ECD8", tint: "#F9F5E8", ink: "#5C4615" },
  // slate-blue
  { name: "slateblue", solid: "#3F567A", soft: "#E5EBF3", tint: "#F2F5F9", ink: "#293957" },
];

function hashString(s) {
  let h = 0;
  for (let i = 0; i < s.length; i++) {
    h = (h * 31 + s.charCodeAt(i)) >>> 0;
  }
  return h;
}

function accentFor(name) {
  return ACCENT_PALETTE[hashString(name) % ACCENT_PALETTE.length];
}

// True when the lede paragraph and the small-caps role tag are the same
// string in content (after normalizing case and trailing punctuation).
// Used by the hero and share card to avoid rendering the same sentence
// twice when the backend filled both fields from one source. We strip
// trailing periods because the small-caps version often loses them.
function isSameAsRoleHint(oneLine, roleHint) {
  if (!oneLine || !roleHint) return false;
  const norm = (s) => s.trim().toLowerCase().replace(/[.\s]+$/, "");
  return norm(oneLine) === norm(roleHint);
}

function initialsOf(name) {
  return name
    .split(/\s+/)
    .map((w) => w[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
}


/**
 * Desktop sidebar pill used for the dashboard surfaces (Forgotten,
 * Upcoming, About you). Visual register matches a sidebar people-row
 * so the three pills feel like part of the same nav. Active state uses
 * a neutral indigo accent rather than a person-specific color, since
 * these surfaces aren't tied to any one person.
 */
function SidebarPill({ icon, label, count, active, onClick }) {
  return (
    <button
      onClick={onClick}
      className="w-full text-left rounded-lg pl-3 pr-3 py-2.5 flex items-center gap-3 group relative"
      style={{
        background: active ? "#EDECF7" : "transparent",
        transition: "background 250ms ease-out",
        borderLeft: `3px solid ${active ? "#3D3A8E" : "transparent"}`,
      }}
      onMouseEnter={(e) => {
        if (!active) e.currentTarget.style.background = "#ECE6DA";
      }}
      onMouseLeave={(e) => {
        if (!active) e.currentTarget.style.background = "transparent";
      }}
    >
      <span
        className="flex items-center justify-center flex-shrink-0"
        style={{
          width: 24, height: 24,
          color: active ? "#272555" : "#7A726A",
        }}
      >
        {icon}
      </span>
      <span
        className="flex-1 text-[13px] font-medium"
        style={{ color: active ? "#15110D" : "#5C544A" }}
      >
        {label}
      </span>
      {count !== undefined && count > 0 && (
        <span
          className="text-[11px] tabular-nums font-medium px-1.5 py-0.5 rounded"
          style={{
            background: active ? "#FFFFFF" : "transparent",
            color: active ? "#272555" : "#A39888",
          }}
        >
          {count}
        </span>
      )}
    </button>
  );
}


/**
 * Compact dashboard tab for the mobile horizontal strip. Always
 * full-width-fit text-only; no icon (mobile space is tight).
 */
function MobileDashTab({ label, count, active, onClick }) {
  return (
    <button
      onClick={onClick}
      className="flex-shrink-0 px-3 py-1.5 rounded-full text-[12px] font-medium inline-flex items-center gap-1.5"
      style={{
        background: active ? "#272555" : "rgba(255,255,255,0.7)",
        color: active ? "#FAF8F4" : "#5C544A",
        border: active ? "1px solid #272555" : "1px solid #E5DFD3",
      }}
    >
      {label}
      {count !== undefined && count > 0 && (
        <span
          className="tabular-nums text-[10.5px] px-1 rounded"
          style={{
            background: active ? "rgba(255,255,255,0.18)" : "#E5DFD3",
            color: active ? "#FAF8F4" : "#7A726A",
          }}
        >
          {count}
        </span>
      )}
    </button>
  );
}


function formatDate(iso) {
  try {
    const d = new Date(iso);
    return d.toLocaleDateString("en-US", {
      month: "long",
      day: "numeric",
      year: "numeric",
    });
  } catch {
    return iso;
  }
}

// Derive quantitative "Spotify Wrapped"-style stats from the data we already have.
// In the real backend these will come straight from the email aggregation pipeline,
// but we surface what we can from the artifact's own inputs so the slot is filled today.
function computeStats(person) {
  const events = [...(person.timeline || [])].sort((a, b) =>
    a.date.localeCompare(b.date)
  );
  const first = events[0]?.date;
  const last = events[events.length - 1]?.date;

  let spanLabel = "—";
  if (first && last) {
    const ms = new Date(last) - new Date(first);
    const days = Math.max(1, Math.round(ms / 86400000));
    if (days < 45) spanLabel = `${days} days`;
    else if (days < 365) spanLabel = `${Math.round(days / 30)} months`;
    else {
      const years = (days / 365).toFixed(days >= 730 ? 0 : 1);
      spanLabel = `${years} ${years === "1" ? "year" : "years"}`;
    }
  }

  const milestones = events.length;

  let recencyLabel = "—";
  if (last) {
    const ms = Date.now() - new Date(last);
    const days = Math.round(ms / 86400000);
    if (days <= 0) recencyLabel = "today";
    else if (days === 1) recencyLabel = "yesterday";
    else if (days < 14) recencyLabel = `${days} days ago`;
    else if (days < 60) recencyLabel = `${Math.round(days / 7)} weeks ago`;
    else if (days < 365) recencyLabel = `${Math.round(days / 30)} months ago`;
    else recencyLabel = `${Math.round(days / 365)}+ years ago`;
  }

  // Meeting count comes from the calendar table via the backend payload.
  // Older artifacts (generated before this field existed) won't have it;
  // default to a zero-state so the wiki doesn't crash.
  const meetingsCount = person.meetings?.count ?? 0;
  const meetingsLabel = meetingsCount === 0 ? "—" : String(meetingsCount);

  const stats = [
    { label: "Span", value: spanLabel },
    { label: "Milestones", value: String(milestones) },
  ];
  // Only show the Meetings stat when there's something to say. Showing
  // "Meetings: —" for everyone clutters the layout for inboxes where the
  // user doesn't have many calendar invites in scope.
  if (meetingsCount > 0) {
    stats.push({ label: "Meetings", value: meetingsLabel });
  }
  stats.push({ label: "Last contact", value: recencyLabel });
  return stats;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------
export default function PeopleWiki({ people, insights }) {
  const [selectedId, setSelectedId] = useState(people[0]?.id || "");
  const [viewMode, setViewMode] = useState("detail"); // "detail" | "share"

  // Which surface is the main panel showing? "person" = the usual
  // per-person page. The other three names match keys in the insights
  // payload. Defaulting to "person" preserves the original UX for
  // anyone who lands on the wiki with a known selected person.
  const [view, setView] = useState("person"); // "person" | "forgotten" | "upcoming" | "about_you"

  const person = useMemo(
    () => people.find((p) => p.id === selectedId) || people[0],
    [selectedId]
  );
  const accent = accentFor(person?.name || "");

  // Reset to detail view when switching people so we never get stuck in the share modal.
  useEffect(() => {
    setViewMode("detail");
  }, [selectedId]);

  // Clicking a person in the sidebar always lands them on the
  // per-person view, even if they were previously on the dashboard.
  function openPerson(personId) {
    setSelectedId(personId);
    setView("person");
  }

  // Inject the serif display font + body font once.
  useEffect(() => {
    if (document.getElementById("people-wiki-fonts")) return;
    const link = document.createElement("link");
    link.id = "people-wiki-fonts";
    link.rel = "stylesheet";
    link.href =
      "https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,300;9..144,400;9..144,500;9..144,600;9..144,700&family=Inter:wght@400;500;600;700&display=swap";
    document.head.appendChild(link);
  }, []);

  const serif = `'Fraunces', 'Iowan Old Style', 'Palatino Linotype', Palatino, Georgia, serif`;
  const sans = `'Inter', ui-sans-serif, system-ui, -apple-system, 'Segoe UI', sans-serif`;

  // After all hooks are declared, bail early if we somehow have no data.
  // Placing this here (not at the top of the function) keeps the rules-of-hooks
  // happy: every render calls the same hooks in the same order.
  if (!people || people.length === 0 || !person) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-stone-50">
        <p className="text-stone-500 text-sm">No people to show.</p>
      </div>
    );
  }

  return (
    <div
      className="min-h-screen w-full"
      style={{
        background: "#FAF8F4",
        color: "#1A1815",
        fontFamily: sans,
        fontFeatureSettings: '"ss01", "cv11"',
      }}
    >
      <div className="flex flex-col md:flex-row min-h-screen">
        {/* SIDEBAR (desktop) ------------------------------------------------ */}
        <aside
          className="hidden md:flex flex-col flex-shrink-0 border-r"
          style={{
            width: 280,
            borderColor: "#EAE5DC",
            background: "#F4F0E8",
          }}
        >
          {/* Dashboard pills: Forgotten / Upcoming / About you. Rendered
              only when the backend produced an insights.json. Each pill
              flips the main panel to the corresponding surface; the
              "person" view is reactivated whenever a person is clicked. */}
          {insights && (
            <div className="px-3 pt-6 pb-3 space-y-1 border-b" style={{ borderColor: "#EAE5DC" }}>
              <SidebarPill
                icon={<Inbox size={14} strokeWidth={2.2} />}
                label="Forgotten"
                count={insights.forgotten?.length || 0}
                active={view === "forgotten"}
                onClick={() => setView("forgotten")}
              />
              <SidebarPill
                icon={<Calendar size={14} strokeWidth={2.2} />}
                label="Upcoming"
                count={insights.upcoming?.length || 0}
                active={view === "upcoming"}
                onClick={() => setView("upcoming")}
              />
              <SidebarPill
                icon={<TrendingUp size={14} strokeWidth={2.2} />}
                label="About you"
                active={view === "about_you"}
                onClick={() => setView("about_you")}
              />
            </div>
          )}

          <div className={insights ? "px-6 pt-5 pb-3" : "px-6 pt-8 pb-5"}>
            <div className="flex items-baseline justify-between">
              <span
                className="text-[11px] uppercase tracking-[0.18em] font-semibold"
                style={{ color: "#7A726A" }}
              >
                Your people
              </span>
              <span
                className="text-[11px] font-medium tabular-nums"
                style={{ color: "#A39888" }}
              >
                {String(people.length).padStart(2, "0")}
              </span>
            </div>
          </div>

          <nav className="flex-1 px-3 pb-6 space-y-1 overflow-y-auto">
            {people.map((p) => {
              const a = accentFor(p.name);
              const active = p.id === selectedId && view === "person";
              return (
                <button
                  key={p.id}
                  onClick={() => openPerson(p.id)}
                  className="w-full text-left rounded-lg pl-3 pr-3 py-3 flex items-center gap-3 group relative"
                  style={{
                    background: active ? a.soft : "transparent",
                    transition: "background 250ms ease-out",
                    borderLeft: `3px solid ${active ? a.solid : "transparent"}`,
                  }}
                  onMouseEnter={(e) => {
                    if (!active) e.currentTarget.style.background = "#ECE6DA";
                  }}
                  onMouseLeave={(e) => {
                    if (!active) e.currentTarget.style.background = "transparent";
                  }}
                >
                  <div
                    className="flex-shrink-0 w-10 h-10 rounded-full flex items-center justify-center text-white font-semibold text-sm"
                    style={{
                      background: a.solid,
                      letterSpacing: "0.02em",
                    }}
                  >
                    {initialsOf(p.name)}
                  </div>
                  <div className="min-w-0">
                    <div
                      className="text-[14px] font-semibold leading-tight truncate"
                      style={{ color: "#1A1815" }}
                    >
                      {p.name}
                    </div>
                    <div
                      className="text-[12px] leading-tight truncate mt-0.5"
                      style={{ color: "#8A8174" }}
                    >
                      {p.role_hint}
                    </div>
                  </div>
                </button>
              );
            })}
          </nav>

          <div className="px-6 py-5 border-t" style={{ borderColor: "#EAE5DC" }}>
            <div
              className="text-[11px] leading-relaxed"
              style={{ color: "#A39888" }}
            >
              Built from your email and calendar.
            </div>
          </div>
        </aside>

        {/* MOBILE strip ----------------------------------------------------- */}
        <div
          className="md:hidden sticky top-0 z-20 border-b"
          style={{ background: "#F4F0E8", borderColor: "#EAE5DC" }}
        >
          {insights && (
            <div className="flex gap-2 overflow-x-auto px-4 pt-4 pb-1">
              <MobileDashTab
                label="Forgotten"
                count={insights.forgotten?.length || 0}
                active={view === "forgotten"}
                onClick={() => setView("forgotten")}
              />
              <MobileDashTab
                label="Upcoming"
                count={insights.upcoming?.length || 0}
                active={view === "upcoming"}
                onClick={() => setView("upcoming")}
              />
              <MobileDashTab
                label="About you"
                active={view === "about_you"}
                onClick={() => setView("about_you")}
              />
            </div>
          )}
          <div className="px-4 pt-4 pb-2 flex items-baseline justify-between">
            <span
              className="text-[11px] uppercase tracking-[0.18em] font-semibold"
              style={{ color: "#7A726A" }}
            >
              Your people
            </span>
            <span className="text-[11px]" style={{ color: "#A39888" }}>
              {String(people.length).padStart(2, "0")}
            </span>
          </div>
          <div className="flex gap-3 overflow-x-auto px-4 pb-4">
            {people.map((p) => {
              const a = accentFor(p.name);
              const active = p.id === selectedId && view === "person";
              return (
                <button
                  key={p.id}
                  onClick={() => openPerson(p.id)}
                  className="flex-shrink-0 flex flex-col items-center gap-1.5"
                  style={{ transition: "all 250ms ease-out" }}
                >
                  <div
                    className="w-12 h-12 rounded-full flex items-center justify-center text-white font-semibold text-sm"
                    style={{
                      background: a.solid,
                      boxShadow: active
                        ? `0 0 0 2px #F4F0E8, 0 0 0 4px ${a.solid}`
                        : "none",
                    }}
                  >
                    {initialsOf(p.name)}
                  </div>
                  <span
                    className="text-[11px] font-medium max-w-[64px] truncate"
                    style={{ color: active ? "#1A1815" : "#8A8174" }}
                  >
                    {p.name.split(" ")[0]}
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        {/* MAIN PANEL ------------------------------------------------------- */}
        <main className="flex-1 min-w-0 relative">
          {/* Share-mode toggle (floating, top right). Only meaningful for
              the per-person view; hidden when one of the dashboard
              surfaces is active. */}
          {view === "person" && (
          <div className="absolute top-6 right-6 md:top-8 md:right-8 z-30">
            {viewMode === "detail" ? (
              <button
                onClick={() => setViewMode("share")}
                className="inline-flex items-center gap-2"
                style={{
                  padding: "9px 16px",
                  borderRadius: 999,
                  background: "rgba(255,255,255,0.85)",
                  border: `1px solid ${accent.soft}`,
                  color: accent.ink,
                  fontSize: 13,
                  fontWeight: 600,
                  backdropFilter: "blur(8px)",
                  boxShadow: `0 4px 14px -8px ${accent.solid}66`,
                  transition: "transform 200ms ease-out, box-shadow 200ms ease-out",
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.transform = "translateY(-1px)";
                  e.currentTarget.style.boxShadow = `0 8px 18px -8px ${accent.solid}99`;
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.transform = "translateY(0)";
                  e.currentTarget.style.boxShadow = `0 4px 14px -8px ${accent.solid}66`;
                }}
              >
                <Share2 size={14} strokeWidth={2.2} />
                Share card
              </button>
            ) : (
              <button
                onClick={() => setViewMode("detail")}
                className="inline-flex items-center gap-2"
                style={{
                  padding: "9px 14px",
                  borderRadius: 999,
                  background: "rgba(255,255,255,0.9)",
                  border: `1px solid ${accent.soft}`,
                  color: "#5C544A",
                  fontSize: 13,
                  fontWeight: 600,
                  backdropFilter: "blur(8px)",
                }}
              >
                <X size={14} strokeWidth={2.4} />
                Back to full view
              </button>
            )}
          </div>
          )}

          {view !== "person" ? (
            <InsightsDashboard
              view={view}
              insights={insights}
              accentFor={accentFor}
              onOpenPerson={openPerson}
            />
          ) : (
          <AnimatePresence mode="wait">
            {viewMode === "detail" ? (
              <motion.div
                key={`detail-${person.id}`}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.25, ease: "easeOut" }}
              >
                <PersonPage person={person} accent={accent} serif={serif} />
              </motion.div>
            ) : (
              <motion.div
                key={`share-${person.id}`}
                initial={{ opacity: 0, scale: 0.985 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.99 }}
                transition={{ duration: 0.3, ease: "easeOut" }}
              >
                <ShareCard person={person} accent={accent} serif={serif} />
              </motion.div>
            )}
          </AnimatePresence>
          )}
        </main>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Person page
// ---------------------------------------------------------------------------
function PersonPage({ person, accent, serif }) {
  return (
    <div>
      {/* HERO */}
      <section
        className="relative overflow-hidden"
        style={{
          paddingTop: 112,
          paddingBottom: 112,
        }}
      >
        {/* Radial backdrop */}
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            background: `radial-gradient(900px 600px at 18% 30%, ${accent.solid}22, transparent 60%), radial-gradient(700px 500px at 85% 70%, ${accent.solid}14, transparent 65%)`,
          }}
        />
        {/* Subtle grain */}
        <div
          className="absolute inset-0 pointer-events-none opacity-[0.035] mix-blend-multiply"
          style={{
            backgroundImage:
              "url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='160' height='160'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/></filter><rect width='100%' height='100%' filter='url(%23n)'/></svg>\")",
          }}
        />

        <div className="relative max-w-[920px] mx-auto px-6 md:px-12">
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, ease: "easeOut", delay: 0.05 }}
            className="flex items-center gap-3 mb-8"
          >
            <span
              className="inline-block w-2 h-2 rounded-full"
              style={{ background: accent.solid }}
            />
            <span
              className="text-[12px] uppercase tracking-[0.2em] font-semibold"
              style={{ color: accent.ink }}
            >
              {person.role_hint}
            </span>
          </motion.div>

          <motion.h1
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, ease: "easeOut", delay: 0.1 }}
            style={{
              fontFamily: serif,
              fontWeight: 500,
              fontSize: "clamp(44px, 7vw, 80px)",
              lineHeight: 1.02,
              letterSpacing: "-0.02em",
              color: "#15110D",
              fontVariationSettings: '"opsz" 144',
            }}
          >
            {person.name}
          </motion.h1>

          <motion.p
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, ease: "easeOut", delay: 0.2 }}
            className="mt-7 max-w-[640px]"
            style={{
              fontSize: 20,
              lineHeight: 1.55,
              color: "#5C544A",
              fontWeight: 400,
            }}
          >
            {/* Hide the lede paragraph if the backend filled it with the
                same string as role_hint above; the editorial layout reads
                better with a single positioning line, not two. */}
            {!isSameAsRoleHint(person.about.one_line, person.role_hint) &&
              person.about.one_line}
          </motion.p>

          {/* Stats row */}
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, ease: "easeOut", delay: 0.3 }}
            className="mt-10 flex flex-wrap items-stretch gap-3"
          >
            {computeStats(person).map((stat, i) => (
              <div
                key={i}
                className="flex flex-col"
                style={{
                  padding: "12px 18px",
                  background: "rgba(255,255,255,0.55)",
                  border: `1px solid ${accent.soft}`,
                  borderRadius: 12,
                  backdropFilter: "blur(4px)",
                  minWidth: 110,
                }}
              >
                <span
                  className="text-[10px] uppercase tracking-[0.18em] font-semibold"
                  style={{ color: accent.ink }}
                >
                  {stat.label}
                </span>
                <span
                  className="mt-1 tabular-nums"
                  style={{
                    fontFamily: serif,
                    fontWeight: 500,
                    fontSize: 22,
                    letterSpacing: "-0.01em",
                    color: "#15110D",
                    lineHeight: 1.1,
                  }}
                >
                  {stat.value}
                </span>
              </div>
            ))}
          </motion.div>
        </div>
      </section>

      {/* ABOUT */}
      <Section title="About them" accent={accent}>
        <div className="grid md:grid-cols-3 gap-x-10 gap-y-10">
          {person.about.current_focus && person.about.current_focus.trim() && (
            <AboutBlock
              label="Current focus"
              icon={<Compass size={14} strokeWidth={2.25} />}
              accent={accent}
            >
              <p style={proseStyle}>{person.about.current_focus}</p>
            </AboutBlock>
          )}
          {person.about.background && person.about.background.trim() && (
            <AboutBlock
              label="Background"
              icon={<Compass size={14} strokeWidth={2.25} />}
              accent={accent}
            >
              <p style={proseStyle}>{person.about.background}</p>
            </AboutBlock>
          )}
          {person.about.three_things_to_know && person.about.three_things_to_know.length > 0 && (
            <AboutBlock
              label="Things to know"
              icon={<Sparkles size={14} strokeWidth={2.25} />}
              accent={accent}
            >
              <ul className="space-y-3">
                {person.about.three_things_to_know.map((t, i) => (
                <li
                  key={i}
                  className="flex gap-2.5 items-start rounded-md px-3 py-2.5"
                  style={{
                    background: accent.tint,
                    border: `1px solid ${accent.soft}`,
                  }}
                >
                  <span
                    className="flex-shrink-0 mt-1"
                    style={{ color: accent.solid }}
                  >
                    {i === 0 ? (
                      <Sparkles size={13} strokeWidth={2.25} />
                    ) : i === 1 ? (
                      <Lightbulb size={13} strokeWidth={2.25} />
                    ) : (
                      <Compass size={13} strokeWidth={2.25} />
                    )}
                  </span>
                  <span
                    style={{
                      fontSize: 14,
                      lineHeight: 1.55,
                      color: "#2E2A24",
                    }}
                  >
                    {t}
                  </span>
                </li>
              ))}
            </ul>
          </AboutBlock>
          )}
        </div>
      </Section>

      {/* TIMELINE */}
      <Section title="Timeline" accent={accent}>
        <div className="relative pl-8 md:pl-10">
          {/* the vertical line */}
          <div
            className="absolute top-2 bottom-2"
            style={{
              left: 11,
              width: 2,
              background: accent.solid,
              opacity: 0.18,
            }}
          />
          <div className="space-y-7">
            {person.timeline.map((ev, i) => (
              <TimelineCard key={i} event={ev} accent={accent} index={i} />
            ))}
          </div>
        </div>
      </Section>

      {/* STORIES */}
      <Section title="Stories" accent={accent}>
        <div className="space-y-7">
          {person.stories.map((s, i) => (
            <StoryCard key={i} story={s} accent={accent} index={i} />
          ))}
        </div>
      </Section>

      {/* FORGOTTEN THREADS */}
      {person.forgotten && person.forgotten.length > 0 && (
        <ForgottenSection person={person} accent={accent} serif={serif} />
      )}

      {/* PREP */}
      <PrepSection person={person} accent={accent} serif={serif} />

      {/* FOOTER */}
      <Footer accent={accent} serif={serif} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Section shell
// ---------------------------------------------------------------------------
function Section({ title, accent, children }) {
  return (
    <section className="py-16 md:py-24">
      <div className="max-w-[920px] mx-auto px-6 md:px-12">
        <motion.div
          initial={{ opacity: 0, y: 14 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.5, ease: "easeOut" }}
          className="mb-10 flex items-baseline gap-4"
        >
          <h2
            style={{
              fontFamily: `'Fraunces', Georgia, serif`,
              fontWeight: 500,
              fontSize: 32,
              letterSpacing: "-0.015em",
              color: "#15110D",
              fontVariationSettings: '"opsz" 144',
            }}
          >
            {title}
          </h2>
          <div
            className="flex-1 h-px"
            style={{
              background: `linear-gradient(to right, ${accent.solid}33, transparent)`,
            }}
          />
        </motion.div>
        {children}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// About block
// ---------------------------------------------------------------------------
function AboutBlock({ label, icon, accent, children }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-60px" }}
      transition={{ duration: 0.4, ease: "easeOut" }}
    >
      <div
        className="flex items-center gap-2 mb-3"
        style={{ color: accent.ink }}
      >
        <span style={{ color: accent.solid }}>{icon}</span>
        <span
          className="text-[11px] uppercase tracking-[0.16em] font-semibold"
        >
          {label}
        </span>
      </div>
      {children}
    </motion.div>
  );
}

const proseStyle = {
  fontSize: 15,
  lineHeight: 1.7,
  color: "#3A342D",
  fontWeight: 400,
};

// ---------------------------------------------------------------------------
// Timeline card
// ---------------------------------------------------------------------------
function TimelineCard({ event, accent, index }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-60px" }}
      transition={{ duration: 0.4, ease: "easeOut", delay: index * 0.04 }}
      className="relative"
    >
      {/* dot */}
      <div
        className="absolute rounded-full"
        style={{
          left: -28,
          top: 26,
          width: 12,
          height: 12,
          background: accent.solid,
          boxShadow: `0 0 0 4px #FAF8F4`,
        }}
      />
      <div
        className="rounded-xl px-6 py-5"
        style={{
          background: "#FFFFFF",
          border: "1px solid #ECE6DA",
          boxShadow:
            "0 1px 2px rgba(20,15,10,0.02), 0 6px 18px rgba(20,15,10,0.04)",
        }}
      >
        <div
          className="text-[12px] uppercase tracking-[0.14em] font-semibold mb-2"
          style={{ color: "#9B907F" }}
        >
          {formatDate(event.date)}
        </div>
        <h3
          style={{
            fontFamily: `'Fraunces', Georgia, serif`,
            fontWeight: 500,
            fontSize: 20,
            lineHeight: 1.25,
            letterSpacing: "-0.01em",
            color: "#15110D",
            marginBottom: 10,
          }}
        >
          {event.title}
        </h3>
        <p style={{ ...proseStyle, marginBottom: 14 }}>{event.description}</p>
        <blockquote
          className="relative pl-4 py-1"
          style={{
            borderLeft: `3px solid ${accent.solid}`,
            color: accent.ink,
            fontStyle: "italic",
            fontSize: 14.5,
            lineHeight: 1.55,
            fontFamily: `'Fraunces', Georgia, serif`,
            fontWeight: 400,
          }}
        >
          <span
            aria-hidden
            className="absolute -top-1 -left-0.5 text-3xl leading-none"
            style={{ color: accent.solid, opacity: 0.35 }}
          >
            “
          </span>
          {event.evidence}
        </blockquote>
      </div>
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Story card
// ---------------------------------------------------------------------------
function StoryCard({ story, accent, index }) {
  return (
    <motion.article
      initial={{ opacity: 0, y: 20 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-60px" }}
      transition={{ duration: 0.45, ease: "easeOut", delay: index * 0.05 }}
      className="rounded-2xl px-7 md:px-10 py-8 md:py-10"
      style={{
        background: "#FBF8F2",
        border: `1px solid #ECE6DA`,
      }}
    >
      <div
        className="text-[12px] uppercase tracking-[0.16em] font-semibold mb-3"
        style={{ color: accent.solid }}
      >
        {story.when}
      </div>
      <h3
        style={{
          fontFamily: `'Fraunces', Georgia, serif`,
          fontWeight: 500,
          fontSize: 26,
          lineHeight: 1.18,
          letterSpacing: "-0.015em",
          color: "#15110D",
          marginBottom: 16,
        }}
      >
        {story.title}
      </h3>
      <p
        style={{
          fontSize: 17,
          lineHeight: 1.7,
          color: "#2E2A24",
          fontWeight: 400,
        }}
      >
        {story.moment}
      </p>
      <div
        className="mt-6 flex items-start gap-2"
        style={{
          paddingTop: 18,
          borderTop: `1px dashed ${accent.solid}55`,
        }}
      >
        <span
          aria-hidden
          style={{
            color: accent.solid,
            fontWeight: 600,
            fontSize: 18,
            lineHeight: 1.55,
            marginRight: 2,
          }}
        >
          —
        </span>
        <p
          style={{
            fontStyle: "italic",
            fontSize: 15.5,
            lineHeight: 1.6,
            color: accent.ink,
            fontFamily: `'Fraunces', Georgia, serif`,
            fontWeight: 400,
          }}
        >
          {story.why_it_matters}
        </p>
      </div>
    </motion.article>
  );
}

// ---------------------------------------------------------------------------
// Prep section
// ---------------------------------------------------------------------------
function PrepSection({ person, accent, serif }) {
  return (
    <section className="py-16 md:py-24">
      <div className="max-w-[920px] mx-auto px-6 md:px-12">
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.5, ease: "easeOut" }}
          className="rounded-2xl overflow-hidden"
          style={{
            background: accent.tint,
            borderLeft: `6px solid ${accent.solid}`,
            border: `1px solid ${accent.soft}`,
            borderLeftWidth: 6,
          }}
        >
          <div className="px-7 md:px-10 py-9 md:py-11">
            <div className="flex items-center gap-3 mb-8">
              <div
                className="flex items-center justify-center rounded-full"
                style={{
                  width: 36,
                  height: 36,
                  background: accent.solid,
                  color: "white",
                }}
              >
                <Calendar size={17} strokeWidth={2.25} />
              </div>
              <h2
                style={{
                  fontFamily: serif,
                  fontWeight: 500,
                  fontSize: 30,
                  letterSpacing: "-0.015em",
                  color: "#15110D",
                }}
              >
                If you meet them next
              </h2>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-x-10 gap-y-9">
              {/* Last we talked */}
              <PrepBlock label="Last we talked" accent={accent}>
                <p style={proseStyle}>{person.prep.last_substantive_interaction}</p>
              </PrepBlock>

              {/* Still open */}
              <PrepBlock label="Still open" accent={accent}>
                <ul className="space-y-3">
                  {person.prep.open_threads.map((t, i) => (
                    <li key={i} className="flex gap-2.5 items-start">
                      <Circle
                        size={15}
                        strokeWidth={1.8}
                        className="flex-shrink-0 mt-1"
                        style={{ color: accent.solid }}
                      />
                      <span
                        style={{
                          fontSize: 14.5,
                          lineHeight: 1.6,
                          color: "#2E2A24",
                        }}
                      >
                        {t}
                      </span>
                    </li>
                  ))}
                </ul>
              </PrepBlock>

              {/* Bring up */}
              <PrepBlock label="Bring up" accent={accent}>
                <ol className="space-y-4">
                  {person.prep.three_talking_points.map((t, i) => (
                    <li key={i} className="flex gap-3 items-start">
                      <span
                        className="flex-shrink-0 flex items-center justify-center rounded-full tabular-nums"
                        style={{
                          width: 24,
                          height: 24,
                          background: "#FFFFFF",
                          border: `1.5px solid ${accent.solid}`,
                          color: accent.solid,
                          fontFamily: serif,
                          fontWeight: 600,
                          fontSize: 13,
                          marginTop: 1,
                        }}
                      >
                        {i + 1}
                      </span>
                      <span
                        style={{
                          fontSize: 14.5,
                          lineHeight: 1.6,
                          color: "#2E2A24",
                        }}
                      >
                        {t}
                      </span>
                    </li>
                  ))}
                </ol>
              </PrepBlock>
            </div>

            {/* Something personal. Hidden when empty because rendering a
                header with no body content looks like the page is broken. */}
            {person.prep.something_personal && person.prep.something_personal.trim() && (
              <div
                className="mt-8 rounded-xl px-6 py-5 flex gap-4 items-start"
                style={{
                  background: "#FFFFFF",
                  border: `1px solid ${accent.soft}`,
                }}
              >
                <div
                  className="flex-shrink-0 flex items-center justify-center rounded-full"
                  style={{
                    width: 32,
                    height: 32,
                    background: accent.soft,
                    color: accent.solid,
                  }}
                >
                  <Heart size={15} strokeWidth={2.2} fill="currentColor" />
                </div>
                <div>
                  <div
                    className="text-[11px] uppercase tracking-[0.16em] font-semibold mb-1.5"
                    style={{ color: accent.solid }}
                  >
                    Something personal
                  </div>
                  <p
                    style={{
                      fontSize: 15,
                      lineHeight: 1.65,
                      color: "#2E2A24",
                    }}
                  >
                    {person.prep.something_personal}
                  </p>
                </div>
              </div>
            )}
          </div>
        </motion.div>
      </div>
    </section>
  );
}

function PrepBlock({ label, accent, children }) {
  return (
    <div>
      <div
        className="text-[11px] uppercase tracking-[0.16em] font-semibold mb-3"
        style={{ color: accent.ink }}
      >
        {label}
      </div>
      {children}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Footer
// ---------------------------------------------------------------------------
function Footer({ accent, serif }) {
  return (
    <footer className="pb-20">
      <div className="max-w-[920px] mx-auto px-6 md:px-12">
        <div
          className="h-px w-full mb-10"
          style={{
            background:
              "linear-gradient(to right, transparent, #D9D2C4, transparent)",
          }}
        />
        <div className="text-center">
          <div
            style={{
              fontFamily: serif,
              fontWeight: 500,
              fontSize: 18,
              color: "#3A342D",
              letterSpacing: "-0.01em",
              marginBottom: 18,
            }}
          >
            Made with TwinMind
          </div>
          <a
            href="https://twinmind.com"
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-2"
            style={{
              padding: "14px 24px",
              borderRadius: 999,
              background: accent.solid,
              color: "#FFFFFF",
              fontSize: 15.5,
              fontWeight: 600,
              letterSpacing: "-0.005em",
              transition: "transform 250ms ease-out, box-shadow 250ms ease-out, opacity 250ms ease-out",
              boxShadow: `0 8px 20px -10px ${accent.solid}88`,
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.transform = "translateY(-1px)";
              e.currentTarget.style.boxShadow = `0 12px 24px -10px ${accent.solid}aa`;
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.transform = "translateY(0)";
              e.currentTarget.style.boxShadow = `0 8px 20px -10px ${accent.solid}88`;
            }}
          >
            Get TwinMind to see your own
            <ArrowUpRight size={17} strokeWidth={2.4} />
          </a>
          <div
            className="text-[12.5px]"
            style={{ color: "#9B907F", marginTop: 18 }}
          >
            Built from your email and calendar.
          </div>
        </div>
      </div>
    </footer>
  );
}

// ---------------------------------------------------------------------------
// Forgotten threads section
// Surfaces 1-3 things that quietly fell off: promises not kept, follow-ups
// that decayed, threads that never landed. The point is to make the user
// feel "huh, I forgot about that" before they even capture a meeting.
// ---------------------------------------------------------------------------
function ForgottenSection({ person, accent, serif }) {
  return (
    <section className="py-14 md:py-20">
      <div className="max-w-[920px] mx-auto px-6 md:px-12">
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.5, ease: "easeOut" }}
        >
          <div className="mb-8 flex items-end justify-between gap-6">
            <div>
              <div
                className="text-[11px] uppercase tracking-[0.18em] font-semibold mb-2"
                style={{ color: accent.ink }}
              >
                Threads that fell quiet
              </div>
              <h2
                style={{
                  fontFamily: serif,
                  fontWeight: 500,
                  fontSize: 38,
                  letterSpacing: "-0.018em",
                  color: "#15110D",
                  lineHeight: 1.05,
                }}
              >
                What you might have <em style={{ fontStyle: "italic" }}>forgotten</em>.
              </h2>
            </div>
            <div
              className="hidden md:block flex-1 h-px"
              style={{
                background:
                  "linear-gradient(to right, transparent, #D9D2C4 30%, #D9D2C4 70%, transparent)",
                marginBottom: 14,
              }}
            />
          </div>

          <div className="space-y-4">
            {person.forgotten.map((f, i) => (
              <ForgottenCard key={i} item={f} accent={accent} serif={serif} index={i} />
            ))}
          </div>
        </motion.div>
      </div>
    </section>
  );
}

function ForgottenCard({ item, accent, serif, index }) {
  const sevColor =
    item.severity === "high"
      ? "#B8542A"
      : item.severity === "medium"
      ? accent.solid
      : "#9B907F";
  return (
    <motion.div
      initial={{ opacity: 0, y: 14 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-50px" }}
      transition={{ duration: 0.4, ease: "easeOut", delay: index * 0.08 }}
      className="rounded-xl overflow-hidden"
      style={{
        background: "#FFFFFF",
        border: `1px solid ${accent.soft}`,
        borderLeft: `3px solid ${sevColor}`,
      }}
    >
      <div className="px-6 md:px-7 py-5 md:py-6">
        <div className="flex items-center gap-2 mb-3">
          <Clock size={13} strokeWidth={2} style={{ color: sevColor }} />
          <span
            className="text-[11.5px] uppercase tracking-[0.16em] font-semibold"
            style={{ color: sevColor }}
          >
            {item.when}
          </span>
        </div>
        <p
          style={{
            fontSize: 15.5,
            lineHeight: 1.6,
            color: "#2E2A24",
            marginBottom: 14,
          }}
        >
          {item.summary}
        </p>
        <div
          className="flex items-start gap-2.5 pt-3"
          style={{ borderTop: `1px dashed ${accent.soft}` }}
        >
          <ArrowUpRight
            size={15}
            strokeWidth={2.2}
            style={{ color: accent.solid, marginTop: 3, flexShrink: 0 }}
          />
          <p
            style={{
              fontSize: 14,
              lineHeight: 1.55,
              color: accent.ink,
              fontStyle: "italic",
              fontFamily: serif,
              fontWeight: 400,
            }}
          >
            {item.suggested_action}
          </p>
        </div>
      </div>
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Share card
// A single-screen, portrait-leaning export view designed for screenshot.
// One hero, three stats, one signature story, one prep hook, footer.
// Same data, different visual register: bolder, simpler, more poster-like.
// ---------------------------------------------------------------------------
function ShareCard({ person, accent, serif }) {
  const stats = computeStats(person);
  const signatureStory = person.stories[0]; // first story = most prominent
  const topTalk = person.prep.three_talking_points[0];

  return (
    <div className="min-h-screen w-full flex items-start justify-center py-10 md:py-16 px-4">
      <div
        className="w-full max-w-[560px] rounded-3xl overflow-hidden relative"
        style={{
          background: "#FFFFFF",
          boxShadow: `0 30px 80px -30px ${accent.solid}55, 0 8px 24px -12px rgba(0,0,0,0.12)`,
          border: `1px solid ${accent.soft}`,
        }}
      >
        {/* HEADER BAND with gradient */}
        <div
          className="relative px-9 pt-12 pb-10"
          style={{
            background: `linear-gradient(135deg, ${accent.tint} 0%, #FFFFFF 70%), radial-gradient(700px 400px at 80% 0%, ${accent.solid}22, transparent 60%)`,
          }}
        >
          {/* Brand strip */}
          <div className="flex items-center justify-between mb-10">
            <div
              className="flex items-center gap-2"
              style={{ color: accent.ink }}
            >
              <span
                className="inline-block rounded-full"
                style={{
                  width: 8,
                  height: 8,
                  background: accent.solid,
                }}
              />
              <span
                className="text-[10.5px] uppercase tracking-[0.22em] font-semibold"
              >
                TwinMind · A page about
              </span>
            </div>
            <span
              className="text-[10.5px] uppercase tracking-[0.18em] font-semibold"
              style={{ color: "#9B907F" }}
            >
              {new Date().toLocaleDateString("en-US", {
                month: "short",
                year: "numeric",
              })}
            </span>
          </div>

          {/* Avatar + name */}
          <div className="flex items-center gap-5 mb-6">
            <div
              className="flex-shrink-0 flex items-center justify-center rounded-full"
              style={{
                width: 64,
                height: 64,
                background: accent.solid,
                color: "#FFFFFF",
                fontFamily: serif,
                fontWeight: 500,
                fontSize: 24,
                letterSpacing: "-0.01em",
              }}
            >
              {initialsOf(person.name)}
            </div>
            <div className="min-w-0">
              <h1
                style={{
                  fontFamily: serif,
                  fontWeight: 500,
                  fontSize: 38,
                  lineHeight: 1.02,
                  letterSpacing: "-0.02em",
                  color: "#15110D",
                }}
              >
                {person.name}
              </h1>
              <p
                className="mt-1.5 text-[13.5px]"
                style={{ color: "#5C544A", lineHeight: 1.4 }}
              >
                {person.role_hint}
              </p>
            </div>
          </div>

          {/* One-line bio. Hidden if it matches role_hint above to avoid
              the same-text duplication on the share card. */}
          {!isSameAsRoleHint(person.about.one_line, person.role_hint) && (
            <p
              style={{
                fontFamily: serif,
                fontWeight: 400,
                fontStyle: "italic",
                fontSize: 17.5,
                lineHeight: 1.5,
                color: "#3A342D",
              }}
            >
              {person.about.one_line}
            </p>
          )}
        </div>

        {/* STATS BAND */}
        <div
          className="grid grid-cols-3 px-2"
          style={{
            borderTop: `1px solid ${accent.soft}`,
            borderBottom: `1px solid ${accent.soft}`,
            background: "#FBF8F2",
          }}
        >
          {stats.map((s, i) => (
            <div
              key={i}
              className="py-5 px-3 text-center"
              style={{
                borderRight:
                  i < stats.length - 1 ? `1px solid ${accent.soft}` : "none",
              }}
            >
              <div
                className="text-[10px] uppercase tracking-[0.18em] font-semibold mb-1.5"
                style={{ color: accent.ink }}
              >
                {s.label}
              </div>
              <div
                className="tabular-nums"
                style={{
                  fontFamily: serif,
                  fontWeight: 500,
                  fontSize: 22,
                  letterSpacing: "-0.012em",
                  color: "#15110D",
                  lineHeight: 1.05,
                }}
              >
                {s.value}
              </div>
            </div>
          ))}
        </div>

        {/* SIGNATURE STORY */}
        <div className="px-9 py-9">
          <div
            className="text-[10.5px] uppercase tracking-[0.18em] font-semibold mb-3"
            style={{ color: accent.ink }}
          >
            A moment
          </div>
          <h2
            style={{
              fontFamily: serif,
              fontWeight: 500,
              fontSize: 26,
              letterSpacing: "-0.015em",
              lineHeight: 1.12,
              color: "#15110D",
              marginBottom: 12,
            }}
          >
            {signatureStory.title}
          </h2>
          <p
            style={{
              fontSize: 14.5,
              lineHeight: 1.6,
              color: "#3A342D",
              marginBottom: 14,
            }}
          >
            {/* Trim the moment so the card stays single-screen friendly */}
            {truncate(signatureStory.moment, 280)}
          </p>
          <p
            style={{
              fontFamily: serif,
              fontStyle: "italic",
              fontSize: 14,
              lineHeight: 1.5,
              color: accent.ink,
              paddingLeft: 14,
              borderLeft: `2px solid ${accent.solid}`,
            }}
          >
            {signatureStory.why_it_matters}
          </p>
        </div>

        {/* PREP HOOK */}
        <div
          className="px-9 py-7"
          style={{
            background: accent.tint,
            borderTop: `1px solid ${accent.soft}`,
          }}
        >
          <div className="flex items-start gap-3">
            <Calendar
              size={17}
              strokeWidth={2.2}
              style={{ color: accent.solid, marginTop: 2, flexShrink: 0 }}
            />
            <div>
              <div
                className="text-[10.5px] uppercase tracking-[0.18em] font-semibold mb-1.5"
                style={{ color: accent.ink }}
              >
                When we meet next
              </div>
              <p
                style={{
                  fontSize: 14.5,
                  lineHeight: 1.55,
                  color: "#2E2A24",
                }}
              >
                {truncate(topTalk, 220)}
              </p>
            </div>
          </div>
        </div>

        {/* FOOTER */}
        <div
          className="px-9 py-8 text-center"
          style={{
            background: "#15110D",
            color: "#FAF8F4",
          }}
        >
          <div
            style={{
              fontFamily: serif,
              fontWeight: 500,
              fontSize: 17,
              letterSpacing: "-0.005em",
              marginBottom: 6,
            }}
          >
            Made with TwinMind
          </div>
          <a
            href="https://twinmind.com"
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5"
            style={{
              color: "#FAF8F4",
              fontSize: 13.5,
              fontWeight: 500,
              opacity: 0.85,
              textDecoration: "underline",
              textUnderlineOffset: 3,
            }}
          >
            Get TwinMind to see your own
            <ArrowUpRight size={13} strokeWidth={2.4} />
          </a>
        </div>
      </div>
    </div>
  );
}

function truncate(text, n) {
  if (!text) return "";
  if (text.length <= n) return text;
  // Trim to last sentence boundary if possible
  const sliced = text.slice(0, n);
  const lastStop = Math.max(
    sliced.lastIndexOf(". "),
    sliced.lastIndexOf("? "),
    sliced.lastIndexOf("! ")
  );
  if (lastStop > n * 0.6) return text.slice(0, lastStop + 1);
  return sliced.replace(/[,;:\s]+\S*$/, "") + "…";
}
