/**
 * Assert the About Them gate against the shipped payload.
 *
 * Written because the gate was surface-tested by clicking through a few
 * people, which is how a live bug survived: the four fully-empty contacts
 * were checked and the two whose only content was `one_line` were not.
 * Clicking around verifies this run. This verifies every run.
 *
 *   node scripts/check-about.mjs
 *
 * Exits non-zero on any disagreement, so it can gate a build.
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { hasAbout, ABOUT_RENDERED_FIELDS } from "../src/lib/about.js";

const here = dirname(fileURLToPath(import.meta.url));
const people = JSON.parse(
  readFileSync(resolve(here, "../src/demo/people.json"), "utf8")
);

let failures = 0;
console.log(`checking ${people.length} people\n`);

for (const p of people) {
  const a = p.about || {};

  // Independent of hasAbout: would the section body actually paint
  // anything? Computed here from first principles so the check cannot
  // agree with the implementation by sharing its bug.
  const painted = ABOUT_RENDERED_FIELDS.filter((f) => {
    const v = a[f];
    return Array.isArray(v) ? v.length > 0 : String(v ?? "").trim() !== "";
  });

  const gate = hasAbout(p);
  const ok = gate === painted.length > 0;
  if (!ok) failures++;

  const state = painted.length > 0 ? `renders ${painted.join(", ")}` : "renders nothing";
  console.log(
    `  [${ok ? "ok  " : "FAIL"}] ${p.name.padEnd(24)} gate=${String(gate).padEnd(5)} ${state}`
  );

  // A section that paints nothing must not be shown, and a section with
  // content must not be hidden. Both directions matter.
  if (!ok && gate) console.log(`         would show an empty section`);
  if (!ok && !gate) console.log(`         would hide content: ${painted.join(", ")}`);
}

console.log(
  `\n${people.length - failures}/${people.length} agree` +
  (failures ? `  (${failures} would render wrong)` : "")
);
process.exit(failures ? 1 : 0);
