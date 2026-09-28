import { readFile } from "node:fs/promises";
import path from "node:path";

const SLUG_STRATEGIES = ["date-prefixed", "filename", "frontmatter"];
const MANIFEST_FORMATS = ["yaml-map", "json"];
const FONT_ROLES = ["title", "meta", "byline"];

function fail(message) {
  throw new Error(`Invalid config: ${message}`);
}

function requireString(obj, key, where = "") {
  if (typeof obj?.[key] !== "string" || obj[key].trim() === "") fail(`${where}${key} must be a non-empty string`);
}

function requirePositiveNumber(obj, key) {
  if (typeof obj?.[key] !== "number" || !Number.isFinite(obj[key]) || obj[key] <= 0) {
    fail(`${key} must be a positive number`);
  }
}

// Validates the parsed config and returns it. Throws with a message naming the
// first problem, so a typo is reported before anything is read or paid for.
export function validateConfig(config) {
  if (config === null || typeof config !== "object" || Array.isArray(config)) fail("expected a JSON object");

  for (const key of ["postsDir", "cardsDir", "rawDir", "ledger", "model", "stylePrompt"]) requireString(config, key);
  requirePositiveNumber(config, "budget");
  requirePositiveNumber(config, "estimatedCostPerImage");

  if (config.categoriesFile != null) requireString(config, "categoriesFile");

  const slugStrategy = config.slugStrategy ?? "date-prefixed";
  if (!SLUG_STRATEGIES.includes(slugStrategy)) {
    fail(`slugStrategy must be one of ${SLUG_STRATEGIES.join(", ")} (got "${slugStrategy}")`);
  }

  if (typeof config.manifest !== "object" || config.manifest === null) fail("manifest must be an object");
  requireString(config.manifest, "path", "manifest.");
  if (!MANIFEST_FORMATS.includes(config.manifest.format)) {
    fail(`manifest.format must be one of ${MANIFEST_FORMATS.join(", ")} (got "${config.manifest.format}")`);
  }

  if (typeof config.brand !== "object" || config.brand === null) fail("brand must be an object");
  for (const key of ["byline", "url", "text", "muted", "accent", "background"]) requireString(config.brand, key, "brand.");

  if (typeof config.fonts !== "object" || config.fonts === null) fail("fonts must be an object");
  for (const role of FONT_ROLES) {
    const f = config.fonts[role];
    if (typeof f?.family !== "string" || typeof f?.weight !== "number") {
      fail(`fonts.${role} must be { "family": string, "weight": number }`);
    }
  }
  if (!Array.isArray(config.fonts.sources) || config.fonts.sources.length === 0) {
    fail("fonts.sources must be a non-empty array of { family, weight, path }");
  }
  for (const [i, src] of config.fonts.sources.entries()) {
    if (typeof src?.family !== "string" || typeof src?.weight !== "number" || typeof src?.path !== "string") {
      fail(`fonts.sources[${i}] must be { "family": string, "weight": number, "path": string }`);
    }
    if (/\.woff2$/i.test(src.path)) {
      fail(`fonts.sources[${i}] is WOFF2, which satori can't read. Use a TTF, OTF or WOFF file.`);
    }
  }

  return { ...config, slugStrategy };
}

// Loads and validates a config file. Every relative path in it is resolved
// against the directory the config file lives in (the project root).
export async function loadConfig(configPath) {
  const absolute = path.resolve(configPath);
  let raw;
  try {
    raw = await readFile(absolute, "utf8");
  } catch (err) {
    throw new Error(`Can't read config file ${absolute}: ${err.message}`);
  }
  let parsed;
  try {
    parsed = JSON.parse(raw);
  } catch (err) {
    throw new Error(`Config file ${absolute} isn't valid JSON: ${err.message}`);
  }
  const config = validateConfig(parsed);
  return { config, root: path.dirname(absolute) };
}
