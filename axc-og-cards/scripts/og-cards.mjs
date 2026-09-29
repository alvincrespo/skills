#!/usr/bin/env node
// Generates unique 1200x630 Open Graph cards for a site's blog posts.
//
// Usage (from the site's root):
//   node og-cards.mjs                          status report; never spends
//   node og-cards.mjs post.md [more.md ...]    dry run for these posts
//   node og-cards.mjs --backfill               dry run for every post missing a card
//   ... --spend strict|auto|yolo               do the work (see below)
//
// Targets and modifiers:
//   --regen                 replace the illustration and card of the named posts
//   --render-only           rebuild cards from saved illustrations; costs nothing
//   --include-overridden    also cover posts whose front matter sets image:
//   --limit N               backfill only: at most N new illustrations
//   --since D / --before D  backfill only: by post date (YYYY-MM-DD)
//   --config path           default og-cards.config.json
//
// Spending:
//   --spend strict   the caller has already shown the estimate and got approval
//   --spend auto     no approval step; the config's total budget still applies
//   --spend yolo     no approval step and the total budget is ignored
//   --budget AMOUNT  limit this one run to AMOUNT dollars, in every mode
// Without --spend a run is a dry run. Every paid call is recorded in the
// ledger, and a missing cost from the API always stops the run.
//
// All text on the card is rendered by satori (never by the image model). Only
// the right-hand illustration comes from OpenRouter's image API, and it's
// cached so a re-render never pays again. Requires OPENROUTER_API_KEY to
// generate illustrations; the key is never logged.

import { run } from "./lib/run.mjs";

process.exitCode = await run(process.argv.slice(2));
