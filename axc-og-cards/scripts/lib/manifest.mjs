import { writeFile } from "node:fs/promises";
import path from "node:path";
import YAML from "yaml";
import { exists } from "./ledger.mjs";

// Rebuilds the manifest of which posts have cards from whichever card PNGs
// actually exist on disk, rather than tracking additions across invocations in
// memory. That keeps it correct even if a previous run was interrupted.
//
// Written as a mapping (slug: true), not a bare list. Bridgetown 2.x loads
// each _data file as a "resource", and a top-level array falls through a
// `.rows` special case that behaves unpredictably with Liquid's
// `contains`/`for`. A mapping supports simple `og_cards[slug]` lookups.
export function serializeManifest(slugs, format) {
  const mapping = Object.fromEntries(slugs.map((slug) => [slug, true]));
  return format === "json" ? JSON.stringify(mapping, null, 2) + "\n" : YAML.stringify(mapping);
}

export async function syncManifest({ posts, cardsDir, manifestPath, format }) {
  const slugs = [];
  for (const post of posts) {
    if (await exists(path.join(cardsDir, `${post.slug}.png`))) slugs.push(post.slug);
  }
  slugs.sort();
  await writeFile(manifestPath, serializeManifest(slugs, format), "utf8");
  return slugs;
}
