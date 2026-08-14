/**
 * Assert the insights payload carries everything the UI reads.
 *
 * This exists because two producers feed the same surfaces and drifted
 * apart silently. The demo baked its JSON with a script under demo/ that
 * ran The Read and the card gate. The pipeline, which is what a real
 * install runs, called neither. So the demo had a self-portrait and share
 * cards and a real inbox had an empty card list, which rendered as a
 * rejection on every person. Each path worked on its own terms and
 * neither knew the other existed.
 *
 * The rule that falls out: when two code paths produce the same surface,
 * something has to assert they produce equivalent results. This is that
 * something, at the cheapest useful level: the keys the components
 * actually read.
 *
 *   node scripts/check-payload.mjs
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const read = (p) => JSON.parse(readFileSync(resolve(here, p), "utf8"));

// Every key a component dereferences off the insights payload, with the
// surface that would break if it went missing.
const CONTRACT = [
  ["forgotten", "the Forgotten dashboard", (v) => Array.isArray(v)],
  ["upcoming", "the Upcoming dashboard", (v) => Array.isArray(v)],
  ["the_read", "The Read", (v) => v && Array.isArray(v.vignettes)],
  ["cards", "the Share Card", (v) => Array.isArray(v)],
];

const insights = read("../src/demo/insights.json");
const people = read("../src/demo/people.json");

let failures = 0;
console.log("insights payload contract\n");

for (const [key, surface, ok] of CONTRACT) {
  const present = ok(insights[key]);
  const count = Array.isArray(insights[key])
    ? insights[key].length
    : insights[key]?.vignettes?.length;
  if (!present) failures++;
  console.log(
    `  [${present ? "ok  " : "FAIL"}] ${key.padEnd(10)} ${String(count ?? "-").padStart(3)}  ${surface}`
  );
}

// A payload that satisfies the contract but is empty still renders a dead
// surface, which is what the rejection message was.
const empties = CONTRACT.filter(([k]) => {
  const v = insights[k];
  const n = Array.isArray(v) ? v.length : v?.vignettes?.length;
  return n === 0;
});
for (const [key, surface] of empties) {
  console.log(`  [warn] ${key.padEnd(10)}   0  ${surface} will render empty`);
}

// hero_line is produced by the timeline agent and read by the hero band.
const noHero = people.filter((p) => !(p.hero_line || "").trim());
console.log(
  `\n  [${noHero.length ? "warn" : "ok  "}] hero_line   ` +
  `${people.length - noHero.length}/${people.length} people`
);

console.log(failures ? `\n${failures} contract failures` : "\ncontract satisfied");
process.exit(failures ? 1 : 0);
