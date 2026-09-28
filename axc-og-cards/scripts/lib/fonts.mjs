import { readFile } from "node:fs/promises";
import path from "node:path";
import { exists } from "./ledger.mjs";

// Lists every problem with the configured fonts, or [] if they're usable:
// each source file must exist, and each role (title, meta, byline) must have
// a source with that exact family and weight. A wrong weight never falls back
// to a different one, since the card would silently render in the wrong font.
export async function findFontProblems(fonts, root) {
  const problems = [];
  for (const src of fonts.sources) {
    if (!(await exists(path.resolve(root, src.path)))) {
      problems.push(`Font file not found: ${src.path} (${src.family} ${src.weight})`);
    }
  }
  for (const role of ["title", "meta", "byline"]) {
    const { family, weight } = fonts[role];
    if (!fonts.sources.some((s) => s.family === family && s.weight === weight)) {
      problems.push(`fonts.${role} needs "${family}" at weight ${weight}, but no entry in fonts.sources provides it`);
    }
  }
  return problems;
}

// Loads the configured font files in the shape satori expects.
export async function loadFonts(fonts, root) {
  const problems = await findFontProblems(fonts, root);
  if (problems.length > 0) {
    throw new Error(`Can't render cards until the fonts are fixed:\n  - ${problems.join("\n  - ")}`);
  }
  return Promise.all(
    fonts.sources.map(async (src) => ({
      name: src.family,
      data: await readFile(path.resolve(root, src.path)),
      weight: src.weight,
      style: "normal",
    }))
  );
}
