import React, { useRef, useState, useEffect } from "react";
// Imported as a raw string at build time so the export never has to
// discover it. See the note on render().
import fontEmbedCSS from "../fonts.css?raw";
import { Download, Copy, Shuffle, Check, X } from "lucide-react";

/**
 * The share card.
 *
 * The card is the only surface that travels. Everything else in the app
 * is seen by somebody who already arrived, so this is the one place where
 * the reviewer's question ("would you send this to a friend") is answered
 * literally rather than in spirit.
 *
 * Three decisions worth knowing before editing:
 *
 * The card carries ONE thing. v1 had a header band, a stats band, a
 * story, a prep hook and a footer, which is a page rendered small. One
 * quote, one kicker, one wordmark.
 *
 * It renders at exact output pixels and is scaled down for preview,
 * rather than rendering responsively and being scaled up on export. What
 * you see is literally the node that gets rasterised, so the PNG cannot
 * disagree with the preview about line breaks or type size.
 *
 * Nothing here names a third party. That is enforced upstream in
 * backend/agents/card_selector.py, where anonymisation is a selection
 * gate: findings that need a name to mean anything stay in The Read,
 * which is private. By the time text reaches this component it is already
 * safe to post.
 */

const FORMATS = {
  square: { w: 1080, h: 1080, label: "Square", sub: "Twitter, LinkedIn" },
  story: { w: 1080, h: 1920, label: "Portrait", sub: "Stories" },
};

// Instagram overlays its own UI on Stories. Text inside these bands gets
// covered by the profile row at the top and the reply bar at the bottom,
// so the composition is inset rather than centred on the raw canvas.
const STORY_SAFE_TOP = 250;
const STORY_SAFE_BOTTOM = 350;

const INK = "#15110D";
const CREAM = "#FAF8F4";

function pickPalette(accent) {
  // A field of colour, not a white card on a coloured page. The quote sits
  // on the accent and the accent carries the brand, so a screenshot with
  // no wordmark visible is still recognisably from here.
  return {
    bg: accent?.solid || "#3D3A8E",
    ink: CREAM,
    muted: "rgba(250,248,244,0.62)",
    rule: "rgba(250,248,244,0.22)",
  };
}

/** The actual export node. Fixed pixels, never responsive. */
function CardCanvas({ card, format, palette, forwardRef, demoUrl }) {
  const { w, h } = FORMATS[format];
  const isStory = format === "story";
  const pad = 96;

  // Long quotes need to step down or they overflow the canvas. Ranges are
  // chosen so the longest quote the selector allows (48 words) still sets
  // on two thirds of the square canvas.
  const words = (card?.quote || "").split(/\s+/).length;
  // Stories has 1320px of usable height against the square's 888, so it
  // can carry noticeably larger type at the same word count.
  const quoteSize = isStory
    ? words > 38 ? 76 : words > 26 ? 88 : 100
    : words > 38 ? 54 : words > 26 ? 62 : 72;

  return (
    <div
      ref={forwardRef}
      style={{
        width: w,
        height: h,
        background: palette.bg,
        position: "relative",
        overflow: "hidden",
        display: "flex",
        flexDirection: "column",
        // Both formats pin the quote to the top of the usable area and the
        // wordmark to the bottom. Centring the block inside the Stories
        // safe area looked balanced in the abstract and left a third of
        // the canvas empty in practice.
        justifyContent: "space-between",
        padding: isStory
          ? `${STORY_SAFE_TOP}px ${pad}px ${STORY_SAFE_BOTTOM}px`
          : `${pad}px`,
        fontFamily: "'Inter', system-ui, sans-serif",
        // Fraunces and Inter are inlined as base64 in src/fonts.css. A
        // <link> to Google does not survive canvas serialisation and the
        // PNG comes out in Times New Roman.
      }}
    >
      {/* A single soft light source, so the field is not flat. */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          background:
            "radial-gradient(900px 700px at 15% 12%, rgba(255,255,255,0.13), transparent 62%)",
          pointerEvents: "none",
        }}
      />

      <div style={{ position: "relative" }}>
        {card?.kicker && (
          <div
            style={{
              fontSize: 22,
              letterSpacing: "0.2em",
              textTransform: "uppercase",
              fontWeight: 600,
              color: palette.muted,
              marginBottom: 44,
            }}
          >
            {card.kicker}
          </div>
        )}

        <div
          style={{
            fontFamily: "'Fraunces', Georgia, serif",
            fontWeight: 500,
            fontSize: quoteSize,
            lineHeight: 1.22,
            letterSpacing: "-0.02em",
            color: palette.ink,
            maxWidth: w - pad * 2,
          }}
        >
          {card?.quote}
        </div>
      </div>

      <div
        style={{
          position: "relative",
          marginTop: 0,
          paddingTop: 32,
          borderTop: `1px solid ${palette.rule}`,
          display: "flex",
          alignItems: "baseline",
          justifyContent: "space-between",
        }}
      >
        <div
          style={{
            fontFamily: "'Fraunces', Georgia, serif",
            fontSize: 30,
            fontWeight: 500,
            color: palette.ink,
            letterSpacing: "-0.01em",
          }}
        >
          Correspondence
        </div>
        {demoUrl && (
          <div style={{ fontSize: 22, color: palette.muted, fontWeight: 500 }}>
            {demoUrl}
          </div>
        )}
      </div>
    </div>
  );
}

export default function ShareCard({ cards, accent, onClose, demoUrl }) {
  const [index, setIndex] = useState(0);
  const [format, setFormat] = useState("square");
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(false);
  const nodeRef = useRef(null);

  const card = cards?.[index];
  const palette = pickPalette(accent);
  const { w, h } = FORMATS[format];

  // Preview scale: fit the real node into the viewport without changing it.
  const [scale, setScale] = useState(0.4);
  useEffect(() => {
    function fit() {
      const maxW = Math.min(window.innerWidth - 96, 560);
      const maxH = window.innerHeight - 300;
      setScale(Math.min(maxW / w, maxH / h, 0.6));
    }
    fit();
    window.addEventListener("resize", fit);
    return () => window.removeEventListener("resize", fit);
  }, [w, h]);

  // Export is hand-rolled rather than done with a library.
  //
  // html-to-image was here and could not finish. It discovers fonts by
  // walking every stylesheet and running a url() regex over each rule,
  // and our @font-face rules carry two base64 payloads of about 90KB. An
  // export ran past thirty seconds and often never resolved. Handing it
  // pre-built font CSS did not help, which ruled out font discovery as
  // the only cost.
  //
  // Measuring settled it: the browser rasterises a 161KB font-carrying
  // SVG in ten milliseconds. All of the time was library JavaScript and
  // none of it was work we need, so the dependency came out.
  //
  // The node is already laid out at the exact output size, so this is a
  // serialise and a draw, with no re-layout and no upscale.
  function documentCSS() {
    let out = "";
    for (const sheet of document.styleSheets) {
      try {
        for (const rule of sheet.cssRules) out += rule.cssText + "\n";
      } catch {
        // Cross-origin stylesheet. Nothing of ours lives in one.
      }
    }
    return out;
  }

  async function render() {
    const node = nodeRef.current;
    const css = fontEmbedCSS + "\n" + documentCSS();

    // XHTML namespace is required: an SVG foreignObject will not render
    // HTML without it.
    const html = node.outerHTML.replace(
      /^<div/,
      '<div xmlns="http://www.w3.org/1999/xhtml"'
    );
    const svg =
      `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}">` +
      `<foreignObject x="0" y="0" width="100%" height="100%">` +
      `<style xmlns="http://www.w3.org/1999/xhtml">${css}</style>` +
      html +
      `</foreignObject></svg>`;

    const img = new Image();
    img.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svg);
    await img.decode();

    const canvas = document.createElement("canvas");
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext("2d");
    ctx.drawImage(img, 0, 0, w, h);
    return canvas.toDataURL("image/png");
  }

  async function download() {
    setBusy(true);
    try {
      const url = await render();
      const a = document.createElement("a");
      a.download = `correspondence-${card?.kind || "card"}-${format}.png`;
      a.href = url;
      a.click();
    } finally {
      setBusy(false);
    }
  }

  async function copy() {
    setBusy(true);
    try {
      const url = await render();
      const blob = await (await fetch(url)).blob();
      await navigator.clipboard.write([
        new ClipboardItem({ "image/png": blob }),
      ]);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      // Clipboard image write is unsupported in some browsers. Falling
      // back to download beats failing silently.
      await download();
    } finally {
      setBusy(false);
    }
  }

  if (!cards || cards.length === 0) {
    // The gate can legitimately produce nothing, and roughly four in ten
    // people land here: their strongest finding only means something with
    // a name attached, and a name is the one thing a public card cannot
    // carry.
    //
    // The copy matters more than it looks. The first version read
    // "Nothing here is worth a card yet", which describes an app with
    // nothing to say. The same outcome, framed as protecting someone who
    // never agreed to appear on a timeline, reads as the discipline
    // working. Same state, opposite impression.
    return (
      <div className="min-h-screen flex items-center justify-center px-6">
        <div className="text-center max-w-[420px]">
          <p style={{ fontSize: 16, color: "#3A342D", lineHeight: 1.65 }}>
            No card for this page. The strongest findings here only hold
            together with someone's name attached, and they did not agree to
            appear on anyone's timeline.
          </p>
          <p
            className="mt-3"
            style={{ fontSize: 14.5, color: "#7A726A", lineHeight: 1.6 }}
          >
            The full observations are still on the page behind this. They
            stay private.
          </p>
          <button
            onClick={onClose}
            className="mt-6 text-[13px] font-semibold"
            style={{ color: "#3D3A8E" }}
          >
            Back
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen w-full flex flex-col items-center pt-8 pb-16 px-6">
      <div className="w-full max-w-[620px] flex items-center justify-between mb-6">
        <div className="flex gap-1.5">
          {Object.entries(FORMATS).map(([key, f]) => (
            <button
              key={key}
              onClick={() => setFormat(key)}
              className="px-3.5 py-2 rounded-full text-[12.5px] font-semibold"
              style={{
                background: format === key ? INK : "rgba(255,255,255,0.7)",
                color: format === key ? CREAM : "#5C544A",
                border: "1px solid #E5DFD3",
              }}
              title={f.sub}
            >
              {f.label}
            </button>
          ))}
        </div>
        <button
          onClick={onClose}
          className="inline-flex items-center gap-1.5 text-[12.5px] font-semibold"
          style={{ color: "#5C544A" }}
        >
          <X size={14} strokeWidth={2.4} />
          Close
        </button>
      </div>

      {/* Scaled preview of the real export node. */}
      <div
        style={{
          width: w * scale,
          height: h * scale,
          overflow: "hidden",
          borderRadius: 14,
          boxShadow: "0 30px 70px -30px rgba(0,0,0,0.45)",
        }}
      >
        <div
          style={{
            transform: `scale(${scale})`,
            transformOrigin: "top left",
            width: w,
            height: h,
          }}
        >
          <CardCanvas
            card={card}
            format={format}
            palette={palette}
            forwardRef={nodeRef}
            demoUrl={demoUrl}
          />
        </div>
      </div>

      <div className="mt-7 flex items-center gap-2">
        {cards.length > 1 && (
          <button
            onClick={() => setIndex((i) => (i + 1) % cards.length)}
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-full text-[13px] font-semibold"
            style={{
              background: "rgba(255,255,255,0.8)",
              border: "1px solid #E5DFD3",
              color: "#5C544A",
            }}
          >
            <Shuffle size={14} strokeWidth={2.2} />
            Next finding
          </button>
        )}
        <button
          onClick={copy}
          disabled={busy}
          className="inline-flex items-center gap-2 px-4 py-2.5 rounded-full text-[13px] font-semibold"
          style={{
            background: "rgba(255,255,255,0.8)",
            border: "1px solid #E5DFD3",
            color: "#5C544A",
            opacity: busy ? 0.5 : 1,
          }}
        >
          {copied ? <Check size={14} strokeWidth={2.6} /> : <Copy size={14} strokeWidth={2.2} />}
          {copied ? "Copied" : "Copy image"}
        </button>
        <button
          onClick={download}
          disabled={busy}
          className="inline-flex items-center gap-2 px-5 py-2.5 rounded-full text-[13px] font-semibold"
          style={{ background: palette.bg, color: CREAM, opacity: busy ? 0.5 : 1 }}
        >
          <Download size={14} strokeWidth={2.4} />
          {busy ? "Rendering" : "Download PNG"}
        </button>
      </div>

      <div className="mt-4 text-[11.5px]" style={{ color: "#9B907F" }}>
        {index + 1} of {cards.length} · no names, safe to post
      </div>
    </div>
  );
}
