import { readFile, readdir } from "node:fs/promises";
import path from "node:path";

// Imported Hashnode posts sometimes contain a `description:` whose
// double-quoted value spans lines in a way that's ambiguous under strict YAML
// (Ruby's Psych accepts it; the `yaml` npm package doesn't). Extract only the
// handful of scalar fields we need with a tolerant line-based reader instead
// of a full YAML parse.
export function extractFrontMatterFields(block) {
  const lines = block.split("\n");
  const fields = {};
  let i = 0;
  while (i < lines.length) {
    const m = lines[i].match(/^([A-Za-z_][A-Za-z0-9_-]*):[ \t]?(.*)$/);
    if (!m) {
      i++;
      continue;
    }
    const [, key, rest] = m;
    const valueLines = [rest];
    let j = i + 1;
    while (j < lines.length && !/^[A-Za-z_][A-Za-z0-9_-]*:[ \t]?/.test(lines[j])) {
      valueLines.push(lines[j]);
      j++;
    }
    fields[key] = valueLines;
    i = j;
  }
  return fields;
}

export function scalarValue(valueLines) {
  if (!valueLines) return null;
  const joined = valueLines.join(" ").trim();
  const dq = joined.match(/^"([\s\S]*)"$/);
  if (dq) return dq[1].replace(/\\(["\\])/g, "$1");
  const sq = joined.match(/^'([\s\S]*)'$/);
  if (sq) return sq[1].replace(/''/g, "'");
  return joined || null;
}

export function splitFrontMatter(raw) {
  const match = raw.match(/^---\n([\s\S]*?)\n---\n?([\s\S]*)$/);
  if (!match) return { data: {}, content: raw };
  const fields = extractFrontMatterFields(match[1]);
  const data = {
    title: scalarValue(fields.title),
    category: scalarValue(fields.category),
    date: scalarValue(fields.date),
    description: scalarValue(fields.description),
    image: scalarValue(fields.image),
    slug: scalarValue(fields.slug),
  };
  return { data, content: match[2] };
}

// How a post's slug is derived; it must match the key the site's templates
// look up in the og_cards manifest.
//   date-prefixed  YYYY-MM-DD-title.md loses the date; a front-matter `slug:`
//                  wins over either (Bridgetown/Jekyll behavior)
//   filename       the file name without .md, as is
//   frontmatter    the front-matter `slug:`, falling back to the file name
export function computeSlug(filename, frontMatterSlug, strategy = "date-prefixed") {
  const stem = filename.replace(/\.md$/, "");
  if (strategy === "filename") return stem;
  if (strategy === "frontmatter") return frontMatterSlug || stem;
  const dateMatch = filename.match(/^(\d{2,4}-\d{1,2}-\d{1,2})-(.+)\.md$/);
  const filenameSlug = dateMatch ? dateMatch[2] : stem;
  return frontMatterSlug || filenameSlug;
}

// An unparseable date is treated as no date, so the card omits it instead of
// printing "Invalid Date".
export function parseDate(value) {
  if (!value) return null;
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? null : d;
}

export async function loadPosts(postsDir, slugStrategy) {
  const files = (await readdir(postsDir)).filter((f) => f.endsWith(".md"));
  const posts = [];
  for (const file of files) {
    const raw = await readFile(path.join(postsDir, file), "utf8");
    const { data } = splitFrontMatter(raw);
    if (!data.title) continue; // skip files without real front matter (e.g. drafts)
    posts.push({
      slug: computeSlug(file, data.slug, slugStrategy),
      title: String(data.title),
      description: data.description ? String(data.description) : "",
      category: data.category ? String(data.category) : null,
      date: parseDate(data.date),
      image: data.image ? String(data.image) : null, // explicit front-matter override
    });
  }
  return posts.sort((a, b) => a.slug.localeCompare(b.slug));
}
