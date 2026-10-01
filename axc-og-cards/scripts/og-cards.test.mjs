import { test } from "node:test";
import assert from "node:assert/strict";
import { readFile, mkdtemp, writeFile, mkdir } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { splitFrontMatter, computeSlug, scalarValue, parseDate } from "./lib/posts.mjs";
import { fitTitleFontSize, estimateLineCount, formatMonthYear } from "./lib/title.mjs";
import { ledgerTotal } from "./lib/ledger.mjs";
import { validateConfig } from "./lib/config.mjs";
import { findFontProblems } from "./lib/fonts.mjs";
import { serializeManifest } from "./lib/manifest.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const template = JSON.parse(await readFile(path.join(here, "../templates/og-cards.config.json"), "utf8"));
const clone = (o) => JSON.parse(JSON.stringify(o));

// --- front matter -------------------------------------------------------

test("splitFrontMatter reads the fields it needs", () => {
  const { data } = splitFrontMatter('---\ntitle: "Hello: world"\ncategory: dev\ndate: 2024-05-01\nslug: custom\n---\nBody');
  assert.equal(data.title, "Hello: world");
  assert.equal(data.category, "dev");
  assert.equal(data.slug, "custom");
  assert.equal(data.image, null);
});

test("splitFrontMatter tolerates a multi-line quoted description", () => {
  const raw = '---\ntitle: T\ndescription: "first line\n  second line"\ncategory: c\n---\nBody';
  const { data } = splitFrontMatter(raw);
  assert.equal(data.description, "first line   second line");
  assert.equal(data.category, "c");
});

test("splitFrontMatter returns no title for a file without front matter", () => {
  assert.equal(splitFrontMatter("Just text").data.title ?? null, null);
});

test("scalarValue strips matching quotes and returns null for empty", () => {
  assert.equal(scalarValue(['"a"']), "a");
  assert.equal(scalarValue(["'b'"]), "b");
  assert.equal(scalarValue([""]), null);
  assert.equal(scalarValue(undefined), null);
});

test("keys with hyphens or digits end the previous field", () => {
  const { data } = splitFrontMatter('---\ntitle: T\ndescription: "abc"\ncover-image: x.png\nh2: y\ncategory: c\n---\n');
  assert.equal(data.description, "abc");
  assert.equal(data.category, "c");
});

test("scalarValue unescapes quotes", () => {
  assert.equal(scalarValue(['"Say \\"hi\\""']), 'Say "hi"');
  assert.equal(scalarValue(["'it''s'"]), "it's");
});

test("parseDate returns null for empty or unparseable dates", () => {
  assert.equal(parseDate(null), null);
  assert.equal(parseDate("not a date"), null);
  assert.equal(parseDate("2024-05-01").toISOString(), "2024-05-01T00:00:00.000Z");
});

// --- slugs --------------------------------------------------------------

test("date-prefixed strips the date; front-matter slug wins", () => {
  assert.equal(computeSlug("2024-05-01-my-post.md", null), "my-post");
  assert.equal(computeSlug("2024-05-01-my-post.md", "custom"), "custom");
  assert.equal(computeSlug("plain.md", null), "plain");
});

test("filename keeps the whole stem and ignores front matter", () => {
  assert.equal(computeSlug("2024-05-01-my-post.md", "custom", "filename"), "2024-05-01-my-post");
});

test("frontmatter uses the slug, falling back to the stem", () => {
  assert.equal(computeSlug("2024-05-01-my-post.md", "custom", "frontmatter"), "custom");
  assert.equal(computeSlug("2024-05-01-my-post.md", null, "frontmatter"), "2024-05-01-my-post");
});

// --- title sizing -------------------------------------------------------

test("a short title gets the maximum size", () => {
  assert.equal(fitTitleFontSize("Short", 600, 3), 68);
});

test("a long title shrinks, never below the minimum", () => {
  const long = "word ".repeat(80);
  assert.equal(fitTitleFontSize(long, 600, 3), 38);
  const medium = "A reasonably long title that needs a little shrinking to fit";
  const size = fitTitleFontSize(medium, 600, 3);
  assert.ok(size < 68 && size >= 38);
  assert.ok(estimateLineCount(medium, size, 600) <= 3);
});

test("formatMonthYear handles a missing date", () => {
  assert.equal(formatMonthYear(null), "");
  assert.equal(formatMonthYear(new Date("2024-05-15T12:00:00Z")), "May 2024");
  // Date-only values parse as UTC midnight; the month must not depend on the machine's zone.
  assert.equal(formatMonthYear(new Date("2024-05-01")), "May 2024");
});

// --- ledger -------------------------------------------------------------

test("ledgerTotal sums costs", () => {
  assert.equal(ledgerTotal([{ slug: "a", cost: 0.03 }, { slug: "b", cost: 0.02 }]), 0.05);
  assert.equal(ledgerTotal([]), 0);
});

test("ledgerTotal refuses an entry with no numeric cost", () => {
  assert.throws(() => ledgerTotal([{ slug: "a", cost: null, timestamp: "t" }], "ledger.json"), /no numeric cost.*ledger\.json/);
  assert.throws(() => ledgerTotal([{ slug: "a", cost: Number.NaN }]), /no numeric cost/);
});

// --- config -------------------------------------------------------------

test("the shipped template is a valid config", () => {
  assert.equal(validateConfig(clone(template)).slugStrategy, "date-prefixed");
});

test("config validation names the first problem", () => {
  const bad = (mutate, pattern) => {
    const c = clone(template);
    mutate(c);
    assert.throws(() => validateConfig(c), pattern);
  };
  bad((c) => delete c.postsDir, /postsDir/);
  bad((c) => (c.budget = -1), /budget/);
  bad((c) => (c.slugStrategy = "nope"), /slugStrategy/);
  bad((c) => (c.manifest.format = "toml"), /manifest\.format/);
  bad((c) => delete c.brand.accent, /brand\.accent/);
  bad((c) => delete c.fonts.title, /fonts\.title/);
  bad((c) => (c.fonts.sources = []), /fonts\.sources/);
});

test("pricing and modelParams are validated", () => {
  const bad = (mutate, pattern) => {
    const c = clone(template);
    mutate(c);
    assert.throws(() => validateConfig(c), pattern);
  };
  bad((c) => delete c.pricing, /pricing must be an object/);
  bad((c) => (c.pricing = { [c.model]: 0 }), /must be a positive number/);
  bad((c) => (c.pricing = { "other/model": 0.01 }), /no entry for the default model/);
  bad((c) => (c.estimatedCostPerImage = 0.035), /replaced by "pricing"/);
  bad((c) => (c.modelParams = [1]), /modelParams must be an object/);
  bad((c) => (c.modelParams = { [c.model]: "seed=1" }), /modelParams\["[^"]+"\] must be an object/);
  const ok = clone(template);
  ok.pricing["vendor/other"] = 0.02;
  ok.modelParams = { "vendor/other": { seed: 1 } };
  assert.doesNotThrow(() => validateConfig(ok));
});

test("og_model is read from front matter", () => {
  assert.equal(splitFrontMatter("---\ntitle: T\nog_model: vendor/m\n---\n").data.og_model, "vendor/m");
  assert.equal(splitFrontMatter("---\ntitle: T\n---\n").data.og_model, null);
});

test("config validation rejects WOFF2 font sources", () => {
  const c = clone(template);
  c.fonts.sources[0].path = "fonts/x.woff2";
  assert.throws(() => validateConfig(c), /WOFF2/);
});

// --- fonts --------------------------------------------------------------

test("findFontProblems reports missing files and unmatched roles", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "og-fonts-"));
  await mkdir(path.join(root, "fonts"));
  await writeFile(path.join(root, "fonts/a.ttf"), "x");
  const fonts = {
    title: { family: "A", weight: 700 },
    meta: { family: "A", weight: 400 },
    byline: { family: "A", weight: 600 },
    sources: [
      { family: "A", weight: 700, path: "fonts/a.ttf" },
      { family: "A", weight: 400, path: "fonts/missing.ttf" },
    ],
  };
  const problems = await findFontProblems(fonts, root);
  assert.equal(problems.length, 2);
  assert.match(problems[0], /missing\.ttf/);
  assert.match(problems[1], /fonts\.byline needs "A" at weight 600/);
});

// --- manifest -----------------------------------------------------------

test("serializeManifest writes a mapping in either format", () => {
  assert.equal(serializeManifest(["a", "b"], "yaml-map"), "a: true\nb: true\n");
  assert.deepEqual(JSON.parse(serializeManifest(["a", "b"], "json")), { a: true, b: true });
});
