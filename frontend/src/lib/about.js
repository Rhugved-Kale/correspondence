/**
 * Whether the About Them section has anything to render.
 *
 * This lives in its own module so a build-time check can assert it against
 * the shipped payload rather than relying on someone clicking through ten
 * people. See scripts/check-about.mjs.
 *
 * The subtlety that caused a live bug: `one_line` is NOT rendered inside
 * the About section. It appears in the hero, as the small-caps eyebrow
 * above the name. So a person whose only confirmed detail is one_line has
 * content on the page but nothing in this section, and gating the section
 * on all four fields rendered a heading over three empty blocks.
 *
 * The predicate has to match what the section DISPLAYS, not what the
 * payload CONTAINS.
 */
export const ABOUT_RENDERED_FIELDS = [
  "current_focus",
  "background",
  "three_things_to_know",
];

export function hasAbout(person) {
  const a = person?.about || {};
  return ABOUT_RENDERED_FIELDS.some((f) => {
    const v = a[f];
    if (Array.isArray(v)) return v.length > 0;
    return typeof v === "string" && v.trim().length > 0;
  });
}
