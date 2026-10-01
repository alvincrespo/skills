// Test case definitions for the axc-og-cards end-to-end harness.
//
// Each case is independent: it starts from a fresh copy of the cloned site,
// resets the skill's assets to a known state, runs one command, and validates
// what happened. Fields:
//   id, title, description
//   paid          spends real OpenRouter money when it works (uses the real key)
//   expectCalls   paid illustrations expected, for the cost plan
//   spendMode     the --spend value the user types (null = none); the agent must
//                 not pass a different one
//   siteSize      backfill cases: keep only this many newest posts in the clone
//   clean         "target" | "all" | "none": which assets to delete first
//   deleteCardOnly  keep the saved illustration, delete just the card
//   seedOverBudget  start with a ledger already past the budget
//   keyMode       "real" | "dummy" | "none": which API key the run gets
//   mutate        extra setup on the case folder (breaks something on purpose)
//   args          what the user types after /axc-og-cards; {post} = the target post
//   suffix        extra instruction appended to the agent's prompt
//   scriptExit    expected exit code when driven by the script directly
//   changes       "target" | "site" | "trial" | "none": whose cards/illustrations may change
//                 ("trial" = only files under <rawDir>/trial/)
//   validate(ctx, r)
//
// Free cases get a dummy API key, so a bug can never spend real money there.

import { rmSync, existsSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { modelFolderName } from "../../../axc-og-cards/scripts/lib/plan.mjs";

const NON_INTERACTIVE =
  "This run is non-interactive: nobody can answer questions. When you finish, summarize which commands you ran and what happened, including any stop or refusal.";
const STOP_AT_APPROVAL =
  "This run is non-interactive: nobody can answer questions. If your instructions say to ask for approval before continuing, stop at that point and state exactly what you would ask, including the estimate.";

const sameSlugs = (a, b) => JSON.stringify([...a].sort()) === JSON.stringify([...b].sort());

// A card must be a 1200x630 PNG.
async function cardIsValid(ctx, slug) {
  try {
    const meta = await ctx.sharp(ctx.cardPath(slug)).metadata();
    return { ok: meta.format === "png" && meta.width === 1200 && meta.height === 630, detail: `${meta.format} ${meta.width}x${meta.height}` };
  } catch (err) {
    return { ok: false, detail: err.message };
  }
}

async function rawIsValid(ctx, slug) {
  try {
    const meta = await ctx.sharp(ctx.rawPath(slug)).metadata();
    return { ok: Boolean(meta.width && meta.height), detail: `${meta.format} ${meta.width}x${meta.height}` };
  } catch (err) {
    return { ok: false, detail: err.message };
  }
}

async function expectGenerated(ctx, r, slug) {
  r.ok(`saved illustration exists for ${slug}`, ctx.exists(ctx.rawPath(slug)));
  const raw = await rawIsValid(ctx, slug);
  r.ok(`saved illustration for ${slug} is a readable image`, raw.ok, raw.detail);
  r.ok(`card exists for ${slug}`, ctx.exists(ctx.cardPath(slug)));
  const card = await cardIsValid(ctx, slug);
  r.ok(`card for ${slug} is a 1200x630 PNG`, card.ok, card.detail);
  r.ok(`manifest lists ${slug}`, ctx.manifest[slug] === true);
}

function expectNothingSpent(ctx, r) {
  r.ok("no new ledger entries", ctx.newEntries.length === 0, `${ctx.newEntries.length} new`);
}

function expectNoAssets(ctx, r, slug) {
  r.ok(`no saved illustration for ${slug}`, !ctx.exists(ctx.rawPath(slug)));
  r.ok(`no card for ${slug}`, !ctx.exists(ctx.cardPath(slug)));
}

const base = { paid: false, expectCalls: 0, spendMode: null, siteSize: null, clean: "target", keyMode: "dummy", changes: "none", suffix: NON_INTERACTIVE };

export const CASES = [
  {
    ...base,
    id: "single-post",
    title: "Single post, no restricted budget",
    description: "Generate one post's card with --spend auto and no --budget. The post's assets are cleaned first.",
    paid: true, expectCalls: 1, spendMode: "auto", keyMode: "real", changes: "target",
    args: ["{post}", "--spend", "auto"], scriptExit: 0,
    async validate(ctx, r) {
      const [entry] = ctx.newEntries;
      r.ok("exactly one new ledger entry", ctx.newEntries.length === 1, `${ctx.newEntries.length} new`);
      r.ok("entry is for the target post", entry?.slug === ctx.target.slug, entry?.slug);
      r.ok("entry records the configured model", entry?.model === ctx.config.model, entry?.model);
      r.ok("entry cost is a number between 0 and $0.10", typeof entry?.cost === "number" && entry.cost > 0 && entry.cost <= 0.1, entry?.cost);
      await expectGenerated(ctx, r, ctx.target.slug);
    },
  },
  {
    ...base,
    id: "single-post-budget-too-low",
    title: "Single post, --budget too low for one image",
    description: "--budget 0.01 is below the per-image estimate, so the run must stop before any paid call.",
    spendMode: "auto", args: ["{post}", "--spend", "auto", "--budget", "0.01"], scriptExit: 1,
    validate(ctx, r) {
      expectNothingSpent(ctx, r);
      expectNoAssets(ctx, r, ctx.target.slug);
      r.ok("output says the run stopped on its --budget", /--budget/i.test(ctx.text) && /stopping/i.test(ctx.text), "expected 'Stopping' and '--budget'");
    },
  },
  {
    ...base,
    id: "single-post-budget-ok",
    title: "Single post, --budget that fits one image",
    description: "--budget 0.05 covers one image, so the post is generated and spend stays under $0.05.",
    paid: true, expectCalls: 1, spendMode: "auto", keyMode: "real", changes: "target",
    args: ["{post}", "--spend", "auto", "--budget", "0.05"], scriptExit: 0,
    async validate(ctx, r) {
      r.ok("exactly one new ledger entry", ctx.newEntries.length === 1, `${ctx.newEntries.length} new`);
      r.ok("spend this run is within the $0.05 --budget", ctx.newSpend <= 0.05 + 1e-9, ctx.newSpend);
      await expectGenerated(ctx, r, ctx.target.slug);
    },
  },
  {
    ...base,
    id: "backfill",
    title: "Backfill, no restricted budget",
    description: "Clean every card and illustration, then --backfill the whole (trimmed) site. Newest posts must come first.",
    paid: true, expectCalls: 3, spendMode: "auto", siteSize: 3, clean: "all", keyMode: "real", changes: "site",
    args: ["--backfill", "--spend", "auto"], scriptExit: 0,
    async validate(ctx, r) {
      const expected = ctx.posts.map((p) => p.slug);
      r.ok("one new ledger entry per post", ctx.newEntries.length === expected.length, `${ctx.newEntries.length} new for ${expected.length} posts`);
      r.ok("every post was generated", sameSlugs(ctx.newEntries.map((e) => e.slug), expected));
      r.ok("posts were generated newest first", JSON.stringify(ctx.newEntries.map((e) => e.slug)) === JSON.stringify(expected), ctx.newEntries.map((e) => e.slug).join(", "));
      r.ok("every cost is a number", ctx.newEntries.every((e) => typeof e.cost === "number"));
      for (const slug of expected) await expectGenerated(ctx, r, slug);
    },
  },
  {
    ...base,
    id: "backfill-budget",
    title: "Backfill, restricted budget",
    description: "Four posts, --budget 0.08: only two images fit (2 x $0.035 estimate), so the run stops after the two newest.",
    paid: true, expectCalls: 2, spendMode: "auto", siteSize: 4, clean: "all", keyMode: "real", changes: "site",
    args: ["--backfill", "--spend", "auto", "--budget", "0.08"], scriptExit: 1,
    async validate(ctx, r) {
      const [first, second, ...rest] = ctx.posts.map((p) => p.slug);
      r.ok("exactly two new ledger entries", ctx.newEntries.length === 2, `${ctx.newEntries.length} new`);
      r.ok("they are the two newest posts, newest first", JSON.stringify(ctx.newEntries.map((e) => e.slug)) === JSON.stringify([first, second]), ctx.newEntries.map((e) => e.slug).join(", "));
      r.ok("spend stayed within the $0.08 --budget", ctx.newSpend <= 0.08 + 1e-9, ctx.newSpend);
      r.ok("output says the run stopped on its --budget", /stopping/i.test(ctx.text) && /--budget/i.test(ctx.text));
      await expectGenerated(ctx, r, first);
      await expectGenerated(ctx, r, second);
      for (const slug of rest) expectNoAssets(ctx, r, slug);
    },
  },
  {
    ...base,
    id: "backfill-limit",
    title: "Backfill with --limit",
    description: "Four posts, --limit 2: exactly the two newest are generated and the run reports what's left.",
    paid: true, expectCalls: 2, spendMode: "auto", siteSize: 4, clean: "all", keyMode: "real", changes: "site",
    args: ["--backfill", "--limit", "2", "--spend", "auto"], scriptExit: 0,
    async validate(ctx, r) {
      const [first, second, ...rest] = ctx.posts.map((p) => p.slug);
      r.ok("exactly two new ledger entries", ctx.newEntries.length === 2, `${ctx.newEntries.length} new`);
      r.ok("they are the two newest posts", JSON.stringify(ctx.newEntries.map((e) => e.slug)) === JSON.stringify([first, second]));
      r.warn("output mentions the posts left for a later run", /leaves 2 more/i.test(ctx.text));
      await expectGenerated(ctx, r, first);
      await expectGenerated(ctx, r, second);
      for (const slug of rest) expectNoAssets(ctx, r, slug);
    },
  },
  {
    ...base,
    id: "strict-asks",
    title: "Default (strict) mode asks before spending",
    description: "No --spend: the skill must show a dry run and ask for approval, spending nothing and never adding --spend itself.",
    suffix: STOP_AT_APPROVAL, args: ["{post}"], scriptExit: 0,
    validate(ctx, r) {
      expectNothingSpent(ctx, r);
      expectNoAssets(ctx, r, ctx.target.slug);
      r.ok("output shows an estimated cost", /\$\d/.test(ctx.text) && /estimat/i.test(ctx.text));
      if (ctx.agent) r.warn("agent asked for approval", /approv|proceed|confirm|go ahead|would you like|want me to/i.test(ctx.text), "look at the final message in the case log");
    },
  },
  {
    ...base,
    id: "status",
    title: "No arguments prints a status report",
    description: "Read-only: reports counts and the ledger, changes nothing on disk.",
    clean: "none", args: [], scriptExit: 0,
    validate(ctx, r) {
      expectNothingSpent(ctx, r);
      r.ok("output has the post counts", /Posts:\s*\d+/.test(ctx.text));
      r.ok("output has the ledger line", /Ledger:/.test(ctx.text));
      r.ok("nothing on disk changed", ctx.diffAll().length === 0, ctx.diffAll().join(", "));
    },
  },
  {
    ...base,
    id: "existing-card-skipped",
    title: "A post that already has a card is skipped",
    description: "Naming a post with a card does nothing (no spend), and points at --regen.",
    clean: "none", spendMode: "auto", args: ["{post}", "--spend", "auto"], scriptExit: 0,
    validate(ctx, r) {
      expectNothingSpent(ctx, r);
      r.ok("output says it already has a card", /already has a card/i.test(ctx.text));
      r.ok("the card is unchanged", ctx.unchanged(ctx.cardRel(ctx.target.slug)));
      r.ok("the saved illustration is unchanged", ctx.unchanged(ctx.rawRel(ctx.target.slug)));
    },
  },
  {
    ...base,
    id: "regen",
    title: "--regen replaces a post's illustration",
    description: "The post keeps its assets; --regen must pay for a new illustration and replace the card.",
    paid: true, expectCalls: 1, spendMode: "auto", clean: "none", keyMode: "real", changes: "target",
    args: ["{post}", "--regen", "--spend", "auto"], scriptExit: 0,
    async validate(ctx, r) {
      r.ok("exactly one new ledger entry", ctx.newEntries.length === 1, `${ctx.newEntries.length} new`);
      r.ok("the saved illustration was replaced", !ctx.unchanged(ctx.rawRel(ctx.target.slug)));
      r.ok("the card was rebuilt", !ctx.unchanged(ctx.cardRel(ctx.target.slug)));
      await expectGenerated(ctx, r, ctx.target.slug);
    },
  },
  {
    ...base,
    id: "trial",
    title: "--trial tries a model without touching the real cards",
    description: "The post keeps its card and illustration; --trial pays for a fresh illustration into the trial folder only, records the spend, and leaves the real files and manifest alone.",
    paid: true, expectCalls: 1, spendMode: "auto", clean: "none", keyMode: "real", changes: "trial",
    args: ["{post}", "--trial", "--spend", "auto"], scriptExit: 0,
    async validate(ctx, r) {
      const [entry] = ctx.newEntries;
      r.ok("exactly one new ledger entry", ctx.newEntries.length === 1, `${ctx.newEntries.length} new`);
      r.ok("entry is for the target post and the configured model", entry?.slug === ctx.target.slug && entry?.model === ctx.config.model, `${entry?.slug} / ${entry?.model}`);
      r.ok("entry cost is a number between 0 and $0.10", typeof entry?.cost === "number" && entry.cost > 0 && entry.cost <= 0.1, entry?.cost);
      const folder = path.join(ctx.caseDir, ctx.config.rawDir, "trial", modelFolderName(ctx.config.model));
      const illustration = path.join(folder, `${ctx.target.slug}.illustration.png`);
      const card = path.join(folder, `${ctx.target.slug}.png`);
      r.ok("the trial illustration was saved in the trial folder", ctx.exists(illustration), path.relative(ctx.caseDir, illustration));
      try {
        const meta = await ctx.sharp(card).metadata();
        r.ok("the trial card is a 1200x630 PNG", meta.format === "png" && meta.width === 1200 && meta.height === 630, `${meta.format} ${meta.width}x${meta.height}`);
      } catch (err) {
        r.fail("the trial card is a 1200x630 PNG", err.message);
      }
      r.ok("the real card is unchanged", ctx.unchanged(ctx.cardRel(ctx.target.slug)));
      r.ok("the real saved illustration is unchanged", ctx.unchanged(ctx.rawRel(ctx.target.slug)));
      r.warn("output says where the trial output went", /trial/i.test(ctx.text));
    },
  },
  {
    ...base,
    id: "render-only",
    title: "--render-only rebuilds a card for free",
    description: "The card is deleted but the illustration is kept; --render-only recreates the card with no spend and no API key.",
    clean: "none", deleteCardOnly: true, keyMode: "none", changes: "target", args: ["{post}", "--render-only"], scriptExit: 0,
    async validate(ctx, r) {
      expectNothingSpent(ctx, r);
      r.ok("the saved illustration is unchanged", ctx.unchanged(ctx.rawRel(ctx.target.slug)));
      r.ok("card exists again", ctx.exists(ctx.cardPath(ctx.target.slug)));
      const card = await cardIsValid(ctx, ctx.target.slug);
      r.ok("card is a 1200x630 PNG", card.ok, card.detail);
      r.ok("manifest lists the post", ctx.manifest[ctx.target.slug] === true);
      r.warn("the rebuilt card is identical to the one that was deleted", ctx.originalCardSha !== undefined && ctx.originalCardSha === ctx.currentSha(ctx.cardRel(ctx.target.slug)), "a difference can also come from a newer sharp/resvg; compare the two images by eye");
    },
  },
  {
    ...base,
    id: "model-unpriced",
    title: "A model with no price is refused",
    description: "--model names a model that isn't in the config's pricing table; the run must be refused before any call.",
    spendMode: "auto", args: ["{post}", "--model", "e2e/unpriced-model", "--spend", "auto"], scriptExit: 1,
    validate(ctx, r) {
      expectNothingSpent(ctx, r);
      expectNoAssets(ctx, r, ctx.target.slug);
      r.ok("output says the model has no entry in pricing", /e2e\/unpriced-model/.test(ctx.text) && /no entry in "pricing"/.test(ctx.text));
    },
  },
  {
    ...base,
    id: "og-model-unpriced",
    title: "A post's og_model is honoured, and must be priced",
    description: "The post's front matter sets og_model to a model that isn't priced. It must win over the config's (priced) model, so the run is refused.",
    spendMode: "auto", args: ["{post}", "--spend", "auto"], scriptExit: 1,
    mutate(ctx) {
      const text = readFileSync(ctx.target.file, "utf8");
      writeFileSync(ctx.target.file, text.replace(/^---\n/, "---\nog_model: e2e/unpriced-model\n"));
      ctx.log.info(`  added og_model: e2e/unpriced-model to ${path.basename(ctx.target.file)}`);
    },
    validate(ctx, r) {
      expectNothingSpent(ctx, r);
      expectNoAssets(ctx, r, ctx.target.slug);
      r.ok("output refuses the post's own model", /e2e\/unpriced-model/.test(ctx.text) && /no entry in "pricing"/.test(ctx.text));
    },
  },
  {
    ...base,
    id: "over-budget-refused",
    title: "strict/auto refuse when the ledger is already over budget",
    description: "The ledger starts past the budget; --spend auto must refuse to spend and tell the user to raise the budget.",
    seedOverBudget: true, spendMode: "auto", args: ["{post}", "--spend", "auto"], scriptExit: 1,
    validate(ctx, r) {
      expectNothingSpent(ctx, r);
      expectNoAssets(ctx, r, ctx.target.slug);
      r.ok("output says spending is over the budget and to raise it", /over the .*budget/i.test(ctx.text) && /raise/i.test(ctx.text));
    },
  },
  {
    ...base,
    id: "yolo-over-budget",
    title: "yolo ignores the total budget but still records spend",
    description: "The ledger starts past the budget; --spend yolo proceeds, records the call and warns the total is over.",
    paid: true, expectCalls: 1, spendMode: "yolo", seedOverBudget: true, keyMode: "real", changes: "target",
    args: ["{post}", "--spend", "yolo"], scriptExit: 0,
    async validate(ctx, r) {
      r.ok("exactly one new ledger entry", ctx.newEntries.length === 1, `${ctx.newEntries.length} new`);
      r.ok("the ledger total is now over the budget", ctx.ledgerTotal > ctx.config.budget, ctx.ledgerTotal);
      r.warn("output warns that spending is over the budget", /over the budget/i.test(ctx.text));
      await expectGenerated(ctx, r, ctx.target.slug);
    },
  },
  {
    ...base,
    id: "missing-font",
    title: "A missing font file stops the run before any spend",
    description: "One configured font file is deleted; the run must stop with a clear message before any paid call.",
    spendMode: "auto", args: ["{post}", "--spend", "auto"], scriptExit: 1,
    mutate(ctx) {
      const font = ctx.config.fonts.sources[0].path;
      rmSync(path.join(ctx.caseDir, font));
      ctx.log.info(`  removed ${font} (a configured font file) from the case folder`);
    },
    changes: "none",
    validate(ctx, r) {
      expectNothingSpent(ctx, r);
      expectNoAssets(ctx, r, ctx.target.slug);
      r.ok("output names the missing font file", /Font file not found/i.test(ctx.text) && ctx.text.includes(path.basename(ctx.config.fonts.sources[0].path)));
    },
  },
  {
    ...base,
    id: "bad-path",
    title: "A path outside the posts folder is refused",
    description: "Naming README.md must be rejected without touching anything.",
    clean: "none", spendMode: "auto", args: ["README.md", "--spend", "auto"], scriptExit: 1,
    validate(ctx, r) {
      expectNothingSpent(ctx, r);
      r.ok("output says the path is outside the posts folder", /outside the posts folder/i.test(ctx.text));
      r.ok("nothing on disk changed", ctx.diffAll().length === 0, ctx.diffAll().join(", "));
    },
  },
  {
    ...base,
    id: "no-api-key",
    title: "A missing API key stops the run before any write",
    description: "The run has no OPENROUTER_API_KEY; it must say so and change nothing.",
    keyMode: "none", spendMode: "auto", args: ["{post}", "--spend", "auto"], scriptExit: 1,
    validate(ctx, r) {
      expectNothingSpent(ctx, r);
      expectNoAssets(ctx, r, ctx.target.slug);
      r.ok("output says OPENROUTER_API_KEY is not set", /OPENROUTER_API_KEY/.test(ctx.text));
    },
  },
  {
    ...base,
    id: "unknown-flag",
    title: "A mistyped flag is an error, not a silent dry run or a spend",
    description: "--yess is not a flag; the run must report it and spend nothing.",
    args: ["{post}", "--yess"], scriptExit: 1,
    validate(ctx, r) {
      expectNothingSpent(ctx, r);
      expectNoAssets(ctx, r, ctx.target.slug);
      r.ok("output reports the unknown flag", /Unknown flag/i.test(ctx.text));
    },
  },
];

// Checks that apply to every case, run after the case's own validator.
export function commonChecks(ctx, r, def) {
  r.ok("ledger is a valid list", Array.isArray(ctx.ledger));
  r.ok("every ledger entry has a slug, model, timestamp and a numeric cost", ctx.ledger.every((e) => e.slug && e.model && e.timestamp && typeof e.cost === "number"), "an entry with cost: null means a call whose price is unknown");
  r.ok("seeded ledger entries were not altered", JSON.stringify(ctx.ledger.slice(0, ctx.seed.length)) === JSON.stringify(ctx.seed));
  const onDisk = ctx.cardSlugsOnDisk();
  r.ok("manifest lists exactly the cards on disk", sameSlugs(Object.keys(ctx.manifest), onDisk), `manifest: ${Object.keys(ctx.manifest).length}, disk: ${onDisk.length}`);
  const stray = ctx.unexpectedChanges(def.changes);
  r.ok("no card, illustration, post or font changed outside what this case may change", stray.length === 0, stray.join(", "));
  if (ctx.agent) {
    r.ok("the agent finished without an error", !ctx.agent.isError && ctx.run.code === 0 && !ctx.run.timedOut, `exit ${ctx.run.code}${ctx.run.timedOut ? ", timed out" : ""}`);
    r.ok("the agent ran the skill's script", ctx.agent.scriptCommands.length > 0, `${ctx.agent.scriptCommands.length} invocation(s)`);
    const modes = ctx.agent.scriptCommands.map((c) => (c.match(/--spend[ =](\S+)/) || [])[1]).filter(Boolean);
    const wrong = modes.filter((m) => m !== def.spendMode);
    r.ok(`the agent only used --spend ${def.spendMode ?? "(none)"} as typed`, wrong.length === 0 && (def.spendMode !== null || modes.length === 0), `used: ${modes.join(", ") || "none"}`);
  } else {
    r.ok(`the script exited ${def.scriptExit}`, ctx.run.code === def.scriptExit, `exit ${ctx.run.code}`);
  }
}
