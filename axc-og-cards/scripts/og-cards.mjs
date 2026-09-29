#!/usr/bin/env node
// Generates unique 1200x630 Open Graph cards for a site's blog posts.
//
// Usage (from the site's root):
//   node og-cards.mjs [--config og-cards.config.json]
//        [--yes] [--only a,b,c] [--regen a,b] [--render-only]
//
//   (no flags)        dry run: prints the plan and cost estimate
//   --yes             generate a card for every post missing one
//   --only a,b,c      limit the run to these slugs
//   --regen a,b       force-regenerate these slugs (new illustration + card)
//   --render-only     rebuild cards from saved illustrations; costs nothing
//
// All text on the card is rendered by satori (never by the image model). Only
// the right-hand illustration comes from OpenRouter's image API, and it's
// cached so a re-render never pays again.
//
// Requires OPENROUTER_API_KEY in the environment to generate illustrations.
// The key is never logged.

import { readFile, writeFile, mkdir } from "node:fs/promises";
import path from "node:path";
import YAML from "yaml";
import { parseArgs } from "./lib/args.mjs";
import { loadConfig } from "./lib/config.mjs";
import { loadPosts } from "./lib/posts.mjs";
import { exists, loadLedger, saveLedger, ledgerTotal } from "./lib/ledger.mjs";
import { syncManifest } from "./lib/manifest.mjs";
import { loadFonts } from "./lib/fonts.mjs";
import { renderCard } from "./lib/card.mjs";
import { generateIllustration } from "./lib/illustration.mjs";

// Set once posts are loaded so the top-level error handler can sync too.
let syncOnExit = null;

async function loadCategories(file) {
  const byKey = new Map();
  if (!file || !(await exists(file))) return byKey;
  const list = YAML.parse(await readFile(file, "utf8")) ?? [];
  if (!Array.isArray(list)) {
    throw new Error(`${file} must be a YAML list of { key, name } entries.`);
  }
  for (const entry of list) if (entry?.key != null) byKey.set(entry.key, entry.name);
  return byKey;
}

// Every early exit after cards may have been written goes through here so the
// manifest reflects the cards that exist on disk. Otherwise a run stopped by
// the budget, an API error or a missing cost leaves finished cards unused by
// the site until the next successful run.
async function exitAfterSync(code) {
  if (syncOnExit) await syncOnExit();
  process.exit(code);
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const { config, root } = await loadConfig(args.config);
  const abs = (p) => path.resolve(root, p);

  const postsDir = abs(config.postsDir);
  const cardsDir = abs(config.cardsDir);
  const rawDir = abs(config.rawDir);
  const ledgerFile = abs(config.ledger);
  const relToRoot = (p) => path.relative(root, p);

  const apiKey = process.env.OPENROUTER_API_KEY;

  await mkdir(cardsDir, { recursive: true });
  await mkdir(rawDir, { recursive: true });
  // The ledger and manifest may live in folders that don't exist yet. Create
  // them now: a ledger write that fails after a paid call would lose the record
  // of that spend.
  await mkdir(path.dirname(ledgerFile), { recursive: true });
  await mkdir(path.dirname(abs(config.manifest.path)), { recursive: true });

  const [allPosts, categories, ledger] = await Promise.all([
    loadPosts(postsDir, config.slugStrategy),
    loadCategories(config.categoriesFile ? abs(config.categoriesFile) : null),
    loadLedger(ledgerFile),
  ]);

  syncOnExit = () =>
    syncManifest({
      posts: allPosts,
      cardsDir,
      manifestPath: abs(config.manifest.path),
      format: config.manifest.format,
    });

  let spent = ledgerTotal(ledger, ledgerFile);

  let candidates = allPosts;
  if (args.only) {
    const onlySet = new Set(args.only);
    candidates = candidates.filter((p) => onlySet.has(p.slug));
  }

  const regenSet = new Set(args.regen ?? []);

  // --render-only rebuilds from saved illustrations, so it needs no API key,
  // makes no ledger entries and skips posts with no saved illustration.
  const jobs = [];
  for (const post of candidates) {
    const hasCard = await exists(path.join(cardsDir, `${post.slug}.png`));
    const hasRaw = await exists(path.join(rawDir, `${post.slug}.png`));
    if (args.renderOnly) {
      if (hasRaw) jobs.push(post);
      continue;
    }
    if (hasCard && !regenSet.has(post.slug)) continue;
    jobs.push(post);
  }

  if (args.renderOnly) {
    console.log(`Render only: rebuilding ${jobs.length} card(s) from saved illustrations (no API calls, no cost).`);
  } else {
    console.log(`Model: ${config.model} (~$${config.estimatedCostPerImage}/image estimated)`);
    console.log(`Ledger total so far: $${spent.toFixed(4)} of $${config.budget.toFixed(2)} budget`);
  }

  if (jobs.length === 0) {
    console.log("Nothing to do: no posts need a card.");
    await syncOnExit();
    return;
  }

  // Only jobs whose raw illustration isn't already cached will actually call the API.
  const callsNeeded = [];
  if (!args.renderOnly) {
    for (const post of jobs) {
      const hasRaw = await exists(path.join(rawDir, `${post.slug}.png`));
      if (!hasRaw || regenSet.has(post.slug)) callsNeeded.push(post);
    }
    const estimatedCost = callsNeeded.length * config.estimatedCostPerImage;
    console.log(`Planned cards: ${jobs.length} (${callsNeeded.length} need a new illustration API call)`);
    console.log(`Estimated cost of this run: $${estimatedCost.toFixed(4)}`);
    console.log(`Remaining budget before run: $${(config.budget - spent).toFixed(4)}`);

    if (!args.yes) {
      console.log("\nDry run only. Re-run with --yes to proceed.");
      return;
    }

    if (callsNeeded.length > 0 && !apiKey) {
      console.error("OPENROUTER_API_KEY is not set; cannot generate new illustrations.");
      process.exit(1);
    }
  }

  const fontData = await loadFonts(config.fonts, root);

  for (const post of jobs) {
    const rawPath = path.join(rawDir, `${post.slug}.png`);
    const cardPath = path.join(cardsDir, `${post.slug}.png`);
    const needsCall = !args.renderOnly && (!(await exists(rawPath)) || regenSet.has(post.slug));

    if (needsCall) {
      spent = ledgerTotal(ledger, ledgerFile);
      if (spent + config.estimatedCostPerImage > config.budget) {
        const remaining = jobs.slice(jobs.indexOf(post)).map((p) => p.slug);
        console.error(`\nStopping: $${spent.toFixed(4)} spent so far; the next call would risk exceeding the $${config.budget.toFixed(2)} budget.`);
        console.error(`Posts not yet generated: ${remaining.join(", ")}`);
        await exitAfterSync(1);
      }

      console.log(`Generating illustration for "${post.slug}"...`);
      let result;
      try {
        result = await generateIllustration({ post, apiKey, model: config.model, stylePrompt: config.stylePrompt });
      } catch (err) {
        console.error(err.message);
        await exitAfterSync(1);
      }
      await writeFile(rawPath, result.buffer);
      ledger.push({
        slug: post.slug,
        model: config.model,
        cost: result.cost,
        timestamp: new Date().toISOString(),
      });
      await saveLedger(ledgerFile, ledger);

      if (result.cost === null) {
        console.error(
          `\nOpenRouter didn't report a numeric usage.cost for "${post.slug}". The image was generated (and likely billed) so it's cached at ${relToRoot(rawPath)} and a ledger entry was recorded with cost: null, but the actual spend is unresolved. Fix that entry in ${relToRoot(ledgerFile)} by hand before running again.`
        );
        await exitAfterSync(1);
      }

      spent += result.cost;
      console.log(`  cost: $${result.cost.toFixed(4)} (running total: $${spent.toFixed(4)})`);
    } else if (!args.renderOnly) {
      console.log(`Reusing cached illustration for "${post.slug}" (no API call).`);
    }

    const rawBuffer = await readFile(rawPath);
    const categoryName = post.category ? categories.get(post.category) ?? post.category : "";
    const cardBuffer = await renderCard({
      post,
      categoryName,
      illustrationPngBuffer: rawBuffer,
      fontData,
      brand: config.brand,
      fonts: config.fonts,
    });
    await writeFile(cardPath, cardBuffer);
    console.log(`  wrote ${relToRoot(cardPath)}`);
  }

  await syncOnExit();

  const finalTotal = ledgerTotal(ledger, ledgerFile);
  console.log(`\nDone. Ledger total: $${finalTotal.toFixed(4)} of $${config.budget.toFixed(2)}.`);
}

main().catch(async (err) => {
  console.error(err.message ?? err);
  // An unexpected error mid-run (e.g. a render failure) must not leave cards
  // that were already written out of the manifest. Never let a failed sync
  // hide the original error.
  if (syncOnExit) {
    try {
      await syncOnExit();
    } catch (syncErr) {
      console.error("Also failed to update the og_cards manifest:", syncErr.message);
    }
  }
  process.exit(1);
});
