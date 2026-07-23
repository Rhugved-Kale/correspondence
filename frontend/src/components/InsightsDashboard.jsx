import { motion } from "framer-motion";
import {
  Clock,
  Calendar,
  Sparkles,
  ArrowRight,
  Inbox,
} from "lucide-react";

/**
 * Top-level dashboard. Renders in the main slot when the user selects
 * one of the dashboard sections from the sidebar (Forgotten / Upcoming
 * / About you). Each section is independently optional: if the
 * backend produced no data for it, we don't render the section, we
 * render a small empty state for THAT section only.
 *
 * Each forgotten thread and upcoming meeting card has an "Open page"
 * affordance that calls onOpenPerson(person_id) so the user can jump
 * directly to that person's wiki page from the dashboard.
 *
 * The visual register stays consistent with PeopleWiki: cream background,
 * Fraunces serif headers, generous spacing, accent color per person
 * derived the same way (caller passes the accentFor function down so
 * we don't duplicate the palette logic).
 */
export default function InsightsDashboard({
  view,                 // "forgotten" | "upcoming" | "about_you"
  insights,             // result of /api/insights
  accentFor,            // function(name) -> { solid, soft, ink, ... }
  onOpenPerson,         // (personId) => void
}) {
  const serif = `'Fraunces', 'Iowan Old Style', Palatino, Georgia, serif`;

  if (view === "forgotten") {
    return (
      <ForgottenView
        items={insights?.forgotten || []}
        accentFor={accentFor}
        onOpenPerson={onOpenPerson}
        serif={serif}
      />
    );
  }
  if (view === "upcoming") {
    return (
      <UpcomingView
        items={insights?.upcoming || []}
        accentFor={accentFor}
        onOpenPerson={onOpenPerson}
        serif={serif}
      />
    );
  }
  return (
    <TheReadView
      read={insights?.the_read || {}}
      serif={serif}
    />
  );
}


// --- The Read ---------------------------------------------------------------
//
// This replaces a grid of stat tiles. The grid was the problem: it answered
// "how much" when the interesting question is "what do you do", and a grid
// reads as a dashboard no matter what numbers are in it.
//
// So: a single column, one vignette per card, generous vertical rhythm. The
// page opens on the sharpest finding set large with no lede above it,
// because a lede would explain the thing the finding is supposed to land on
// its own. Numbers live inside sentences rather than in tiles.

function TheReadView({ read, serif }) {
  const vignettes = read?.vignettes || [];

  if (vignettes.length === 0) {
    return (
      <div className="max-w-[720px] mx-auto px-6 md:px-12 py-16">
        <EmptyState
          icon={<Sparkles size={28} strokeWidth={1.8} />}
          title="Nothing to say yet."
          body="The Read needs a few months of correspondence before it can find anything worth pointing at."
        />
      </div>
    );
  }

  const [opening, ...rest] = vignettes;

  return (
    <div className="max-w-[720px] mx-auto px-6 md:px-12 py-16 md:py-24">
      {/* Opening. No eyebrow, no lede. The finding is the entrance. */}
      <motion.section
        initial={{ opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: "easeOut" }}
      >
        <h1
          style={{
            fontFamily: serif,
            fontWeight: 500,
            fontSize: "clamp(34px, 5.2vw, 54px)",
            lineHeight: 1.08,
            letterSpacing: "-0.022em",
            color: "#15110D",
          }}
        >
          {opening.headline}
        </h1>
        <p
          className="mt-7"
          style={{ fontSize: 19, lineHeight: 1.68, color: "#2E2A24" }}
        >
          {opening.body}
        </p>
      </motion.section>

      <div
        className="my-16 h-px w-full"
        style={{
          background:
            "linear-gradient(to right, #D9D2C4, rgba(217,210,196,0.15))",
        }}
      />

      <div className="space-y-16 md:space-y-20">
        {rest.map((v, i) => (
          <motion.section
            key={i}
            initial={{ opacity: 0, y: 18 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-70px" }}
            transition={{ duration: 0.5, ease: "easeOut" }}
          >
            <h2
              style={{
                fontFamily: serif,
                fontWeight: 500,
                fontSize: "clamp(24px, 3.2vw, 32px)",
                lineHeight: 1.15,
                letterSpacing: "-0.016em",
                color: "#15110D",
              }}
            >
              {v.headline}
            </h2>
            <p
              className="mt-5"
              style={{ fontSize: 17, lineHeight: 1.7, color: "#3A342D" }}
            >
              {v.body}
            </p>
          </motion.section>
        ))}
      </div>

      {/* The only number on the page that is not inside a sentence. */}
      {read?.window && (
        <div
          className="mt-20 pt-8"
          style={{ borderTop: "1px solid #EAE5DC" }}
        >
          <p className="text-[12.5px]" style={{ color: "#9B907F" }}>
            Read from {read.volume?.total?.toLocaleString?.() || "your"} messages,{" "}
            {read.window.first} to {read.window.last}.
          </p>
        </div>
      )}
    </div>
  );
}


// --- Forgotten threads view -------------------------------------------------

function ForgottenView({ items, accentFor, onOpenPerson, serif }) {
  return (
    <DashboardLayout
      eyebrow="Threads to revisit"
      title="Things you might have forgotten."
      lede="Open threads with people you haven't talked to in a while, surfaced from your inbox so they don't quietly slip away."
      serif={serif}
    >
      {items.length === 0 ? (
        <EmptyState
          icon={<Inbox size={28} strokeWidth={1.8} />}
          title="No forgotten threads."
          body="Nothing's gone stale. You're caught up with everyone we wrote a page for."
        />
      ) : (
        <div className="space-y-4">
          {items.map((entry, i) => {
            const accent = accentFor(entry.person_name);
            return (
              <motion.div
                key={`${entry.person_id}-${i}`}
                initial={{ opacity: 0, y: 12 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.35, delay: i * 0.04 }}
                className="rounded-xl p-5 md:p-6 flex flex-col md:flex-row md:items-start gap-4"
                style={{
                  background: "#FFFFFF",
                  border: `1px solid ${accent.soft}`,
                }}
              >
                <div
                  className="flex-shrink-0 px-3 py-1.5 rounded-full text-[11px] uppercase tracking-[0.16em] font-semibold inline-flex items-center gap-1.5 self-start"
                  style={{
                    background: accent.soft,
                    color: accent.ink,
                  }}
                >
                  <Clock size={11} strokeWidth={2.5} />
                  {entry.freshness_label}
                </div>
                <div className="flex-1 min-w-0">
                  <div
                    className="text-[12px] uppercase tracking-[0.14em] font-semibold mb-1.5"
                    style={{ color: accent.solid }}
                  >
                    {entry.person_name}
                  </div>
                  <p
                    style={{
                      fontSize: 16,
                      lineHeight: 1.55,
                      color: "#2E2A24",
                    }}
                  >
                    {entry.thread}
                  </p>
                </div>
                <button
                  onClick={() => onOpenPerson(entry.person_id)}
                  className="inline-flex items-center gap-1.5 self-end md:self-center flex-shrink-0"
                  style={{
                    fontSize: 12.5,
                    color: accent.solid,
                    fontWeight: 600,
                  }}
                  onMouseEnter={(e) => { e.currentTarget.style.opacity = "0.7"; }}
                  onMouseLeave={(e) => { e.currentTarget.style.opacity = "1"; }}
                >
                  Open page
                  <ArrowRight size={13} strokeWidth={2.5} />
                </button>
              </motion.div>
            );
          })}
        </div>
      )}
    </DashboardLayout>
  );
}


// --- Upcoming meetings view -------------------------------------------------

function UpcomingView({ items, accentFor, onOpenPerson, serif }) {
  return (
    <DashboardLayout
      eyebrow="Coming up on your calendar"
      title="Walk in prepared."
      lede="Your next calendar meetings. The ones with people we wrote a page for include a quick refresher of where you left off."
      serif={serif}
    >
      {items.length === 0 ? (
        <EmptyState
          icon={<Calendar size={28} strokeWidth={1.8} />}
          title="Nothing on the calendar."
          body="Your next two weeks of calendar events came back empty."
        />
      ) : (
        <div className="space-y-4">
          {items.map((m, i) => {
            // Anchor is the top-10 person who's also attending this
            // meeting, if any. Without an anchor we still render the
            // meeting but skip the "with X" line, the prep blurb, and
            // the "Open page" button.
            const hasAnchor = !!m.anchor_person_id;
            const accent = accentFor(m.anchor_person_name || "default");
            const when = formatMeetingTime(m.start_utc);
            return (
              <motion.div
                key={m.event_id}
                initial={{ opacity: 0, y: 12 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.35, delay: i * 0.04 }}
                className="rounded-xl overflow-hidden"
                style={{
                  background: "#FFFFFF",
                  border: `1px solid ${accent.soft}`,
                }}
              >
                <div
                  className="px-5 md:px-6 py-3 flex items-center gap-3"
                  style={{
                    background: accent.soft,
                  }}
                >
                  <Calendar size={14} strokeWidth={2.2} style={{ color: accent.solid }} />
                  <div
                    className="text-[12px] uppercase tracking-[0.14em] font-semibold"
                    style={{ color: accent.ink }}
                  >
                    {when}
                  </div>
                </div>
                <div className="px-5 md:px-6 py-5">
                  <h3
                    style={{
                      fontFamily: serif,
                      fontSize: 22,
                      lineHeight: 1.25,
                      letterSpacing: "-0.01em",
                      color: "#15110D",
                      fontWeight: 500,
                    }}
                  >
                    {m.summary}
                  </h3>
                  <div
                    className="mt-1.5 text-[13.5px] flex flex-wrap items-center gap-x-3 gap-y-1"
                    style={{ color: "#7A726A" }}
                  >
                    {hasAnchor && (
                      <span style={{ color: accent.solid, fontWeight: 600 }}>
                        with {m.anchor_person_name}
                      </span>
                    )}
                    {m.other_attendees_count > 0 && (
                      <span>
                        {hasAnchor ? "+ " : ""}{m.other_attendees_count} attendee{m.other_attendees_count === 1 ? "" : "s"}
                      </span>
                    )}
                    {m.location && <span>· {m.location}</span>}
                  </div>

                  {m.prep_blurb && (
                    <div
                      className="mt-4 px-4 py-3 rounded-lg"
                      style={{
                        background: "#FAF8F4",
                        borderLeft: `2px solid ${accent.solid}`,
                      }}
                    >
                      <div
                        className="text-[11px] uppercase tracking-[0.14em] font-semibold mb-1"
                        style={{ color: accent.solid }}
                      >
                        Where you left off
                      </div>
                      <p
                        style={{
                          fontSize: 14,
                          lineHeight: 1.55,
                          color: "#2E2A24",
                        }}
                      >
                        {m.prep_blurb}
                      </p>
                    </div>
                  )}

                  {m.talking_points && m.talking_points.length > 0 && (
                    <div className="mt-4">
                      <div
                        className="text-[11px] uppercase tracking-[0.14em] font-semibold mb-2"
                        style={{ color: "#5C544A" }}
                      >
                        Bring up
                      </div>
                      <ul className="space-y-1.5">
                        {m.talking_points.map((tp, ti) => (
                          <li
                            key={ti}
                            className="flex gap-2.5 items-start"
                            style={{
                              fontSize: 14,
                              lineHeight: 1.55,
                              color: "#2E2A24",
                            }}
                          >
                            <span
                              className="flex-shrink-0 mt-1"
                              style={{
                                width: 18,
                                height: 18,
                                borderRadius: 999,
                                background: accent.soft,
                                color: accent.solid,
                                fontSize: 10,
                                fontWeight: 700,
                                display: "inline-flex",
                                alignItems: "center",
                                justifyContent: "center",
                              }}
                            >
                              {ti + 1}
                            </span>
                            <span>{tp}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {hasAnchor && (
                    <button
                      onClick={() => onOpenPerson(m.anchor_person_id)}
                      className="mt-5 inline-flex items-center gap-1.5"
                      style={{
                        fontSize: 12.5,
                        color: accent.solid,
                        fontWeight: 600,
                      }}
                      onMouseEnter={(e) => { e.currentTarget.style.opacity = "0.7"; }}
                      onMouseLeave={(e) => { e.currentTarget.style.opacity = "1"; }}
                    >
                      Open their page
                      <ArrowRight size={13} strokeWidth={2.5} />
                    </button>
                  )}
                </div>
              </motion.div>
            );
          })}
        </div>
      )}
    </DashboardLayout>
  );
}


// --- About-you view ---------------------------------------------------------

// --- Shared primitives ------------------------------------------------------

function DashboardLayout({ eyebrow, title, lede, serif, children }) {
  return (
    <div className="max-w-[920px] mx-auto px-6 md:px-12 py-12 md:py-16">
      <div className="flex items-center gap-2 mb-6">
        <Sparkles size={14} strokeWidth={2.2} style={{ color: "#3D3A8E" }} />
        <span
          className="text-[11px] uppercase tracking-[0.22em] font-semibold"
          style={{ color: "#272555" }}
        >
          {eyebrow}
        </span>
      </div>
      <h1
        style={{
          fontFamily: serif,
          fontWeight: 500,
          fontSize: "clamp(34px, 5vw, 52px)",
          lineHeight: 1.05,
          letterSpacing: "-0.02em",
          color: "#15110D",
        }}
      >
        {title}
      </h1>
      <p
        className="mt-5 max-w-[640px]"
        style={{ fontSize: 17, lineHeight: 1.55, color: "#5C544A" }}
      >
        {lede}
      </p>
      <div className="mt-10">
        {children}
      </div>
    </div>
  );
}


function EmptyState({ icon, title, body }) {
  return (
    <div
      className="rounded-xl px-6 py-10 text-center"
      style={{
        background: "#FFFFFF",
        border: "1px dashed #DDD5C7",
      }}
    >
      <div
        className="inline-flex items-center justify-center mb-4"
        style={{
          width: 56, height: 56, borderRadius: 14,
          background: "#F4F0E8", color: "#A39888",
        }}
      >
        {icon}
      </div>
      <div
        className="font-medium"
        style={{ fontSize: 16, color: "#1A1815" }}
      >
        {title}
      </div>
      <p
        className="mt-1.5 max-w-[400px] mx-auto"
        style={{ fontSize: 14, lineHeight: 1.55, color: "#7A726A" }}
      >
        {body}
      </p>
    </div>
  );
}


// --- helpers ----------------------------------------------------------------

function formatMeetingTime(utcString) {
  if (!utcString) return "";
  try {
    const d = new Date(utcString);
    const now = new Date();
    const diffMs = d - now;
    const diffHr = diffMs / (1000 * 60 * 60);
    const diffDay = diffHr / 24;

    const dayLabel =
      diffDay < 0 ? "just now" :
      diffDay < 1 && d.getDate() === now.getDate() ? "today" :
      diffDay < 1 ? "tomorrow" :
      diffDay < 7
        ? d.toLocaleDateString(undefined, { weekday: "long" })
        : d.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });

    const timeLabel = d.toLocaleTimeString(undefined, {
      hour: "numeric",
      minute: "2-digit",
    });

    return `${dayLabel} at ${timeLabel}`;
  } catch (e) {
    return utcString;
  }
}
