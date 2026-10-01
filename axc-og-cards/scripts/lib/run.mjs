import { readFile, writeFile, mkdir } from "node:fs/promises";
import path from "node:path";
import YAML from "yaml";
import { parseArgs } from "./args.mjs";
import { loadConfig } from "./config.mjs";
import { loadPosts } from "./posts.mjs";
import { exists, loadLedger, saveLedger, ledgerTotal } from "./ledger.mjs";
import { syncManifest } from "./manifest.mjs";
import { loadFonts, findFontProblems } from "./fonts.mjs";
import { renderCard } from "./card.mjs";
import { generateIllustration } from "./illustration.mjs";
import { canAfford, fitCalls, describeLimit, selectJobs, buildStatus, resolveModel, trialPaths } from "./plan.mjs";

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

// Runs the command and returns the exit code. Never calls process.exit and
// never throws, so tests can drive it with a fake fetch, environment and
// output.
//
//   no target             status report; never spends, writes nothing
//   post paths|--backfill without --spend: dry run (plan + estimate)
//                         with --spend strict|auto|yolo: does the work
//   --render-only         rebuilds from saved illustrations; costs nothing,
//                         so it runs without --spend
//
// The approval step for strict mode belongs to the caller (SKILL.md runs the
// dry run, asks, then reruns with --spend strict). Everything that limits or
// records spending lives here so it can't depend on the caller behaving.
export async function run(argv, ctx = {}) {
  const { fetchImpl = fetch, env = process.env, cwd = process.cwd(), out = console.log, errOut = console.error } = ctx;

  // Set once posts are loaded, so every exit after that point can rebuild the
  // manifest of which posts have cards. Otherwise cards finished before a stop
  // stay unused by the site until the next successful run.
  let sync = null;

  try {
    return await runCommand();
  } catch (err) {
    errOut(err.message ?? err);
    if (sync) {
      try {
        await sync();
      } catch (syncErr) {
        errOut("Also failed to update the og_cards manifest:", syncErr.message);
      }
    }
    return 1;
  }

  async function stopWith(code) {
    await sync();
    return code;
  }

  async function runCommand() {
    const args = parseArgs(argv);
    const { config, root } = await loadConfig(path.resolve(cwd, args.config));
    const abs = (p) => path.resolve(root, p);
    const relToRoot = (p) => path.relative(root, p);

    const postsDir = abs(config.postsDir);
    const cardsDir = abs(config.cardsDir);
    const rawDir = abs(config.rawDir);
    const ledgerFile = abs(config.ledger);

    const [posts, categories, ledger] = await Promise.all([
      loadPosts(postsDir, config.slugStrategy),
      loadCategories(config.categoriesFile ? abs(config.categoriesFile) : null),
      loadLedger(ledgerFile),
    ]);
    let spentTotal = ledgerTotal(ledger, ledgerFile);

    const hasCard = new Set();
    const hasRaw = new Set();
    for (const post of posts) {
      if (await exists(path.join(cardsDir, `${post.slug}.png`))) hasCard.add(post.slug);
      if (await exists(path.join(rawDir, `${post.slug}.png`))) hasRaw.add(post.slug);
    }

    if (args.kind === "status") {
      for (const line of buildStatus({ posts, hasCard, hasRaw, spentTotal, config })) out(line);
      return 0;
    }

    // A trial leaves the real cards, illustrations and manifest alone.
    sync = args.trial
      ? async () => {}
      : () => syncManifest({ posts, cardsDir, manifestPath: abs(config.manifest.path), format: config.manifest.format });

    // Create the folders just before the first write (never for a status run or
    // a dry run). A ledger write that fails after a paid call would lose the
    // record of that spend, so they all exist before any call is made.
    const prepareFolders = async () => {
      await mkdir(path.dirname(ledgerFile), { recursive: true });
      if (args.trial) {
        for (const job of jobs) await mkdir(trialPaths({ rawDir, model: job.model, slug: job.post.slug }).folder, { recursive: true });
        return;
      }
      await mkdir(cardsDir, { recursive: true });
      await mkdir(rawDir, { recursive: true });
      await mkdir(path.dirname(abs(config.manifest.path)), { recursive: true });
    };

    const { jobs: selected, notes } = selectJobs({ posts, args, postsDir, cwd, hasCard, hasRaw });
    for (const note of notes) out(note);

    // Each job uses its own model (the post's og_model, then --model, then the
    // config's), and each model has its own price. A model with no price gets
    // estimate: null, which stops the run below rather than guessing.
    const jobs = selected.map((job) => {
      const model = resolveModel({ post: job.post, args, config });
      return { ...job, model, estimate: Object.hasOwn(config.pricing, model) ? config.pricing[model] : null };
    });

    if (jobs.length === 0) {
      out("Nothing to do: no cards to generate.");
      if (!args.spend && !args.renderOnly) return 0;
      await prepareFolders();
      await sync();
      return 0;
    }

    const callsNeeded = jobs.filter((j) => j.needsCall);
    // A dry run assumes strict, which is what runs after the caller's approval.
    const mode = args.spend ?? "strict";
    const limits = { mode, totalBudget: config.budget, spentTotal, runBudget: args.budget };

    if (args.renderOnly) {
      out(`Render only: rebuilding ${jobs.length} card(s) from saved illustrations (no API calls, no cost).`);
    } else {
      const fit = fitCalls({ estimates: callsNeeded.map((j) => j.estimate ?? 0), ...limits });
      const perModel = new Map();
      for (const j of callsNeeded) perModel.set(j.model, { count: (perModel.get(j.model)?.count ?? 0) + 1, estimate: j.estimate });
      const price = (e) => (e === null ? "no price in pricing" : `~$${e}/image estimated`);
      if (perModel.size <= 1) {
        const [model, info] = perModel.size === 1 ? [...perModel][0] : [config.model, { estimate: config.pricing[config.model] }];
        out(`Model: ${model} (${price(info.estimate)})`);
      } else {
        out(`Models: ${[...perModel].map(([m, i]) => `${m} x${i.count} (${price(i.estimate)})`).join(", ")}`);
      }
      if (args.trial) out(`Trial: output goes to ${path.relative(root, path.join(rawDir, "trial"))}/<model>/; the real cards, illustrations and manifest are left alone.`);
      out(`Planned cards: ${jobs.length} (${callsNeeded.length} need a paid illustration)`);
      out(`Estimated cost of this run: $${callsNeeded.reduce((n, j) => n + (j.estimate ?? 0), 0).toFixed(4)}`);
      out(`Limit: ${describeLimit(limits)}`);
      if (callsNeeded.length > fit) {
        out(`Only ${fit} of ${callsNeeded.length} paid illustrations fit under that limit; the run will stop after ${fit}.`);
      }
    }

    // Everything that would stop the real run before it makes a call. A dry run
    // reports these too, so an approval is never asked for a run that would be
    // refused straight afterwards.
    const problems = [];
    if (!args.renderOnly && callsNeeded.length > 0) {
      for (const model of new Set(callsNeeded.filter((j) => j.estimate === null).map((j) => j.model))) {
        problems.push(`Model "${model}" has no entry in "pricing" in ${path.basename(args.config)}, so its cost can't be estimated or limited. Add its estimated dollars per image there, or use a different model.`);
      }
      if (mode !== "yolo" && spentTotal > config.budget + 1e-9) {
        problems.push(`Spending is $${spentTotal.toFixed(4)}, over the $${config.budget.toFixed(2)} budget (an earlier --spend yolo run went past it). Raise "budget" in ${path.basename(args.config)} to keep spending.`);
      }
      if (!env.OPENROUTER_API_KEY) problems.push("OPENROUTER_API_KEY is not set; cannot generate new illustrations.");
    }
    problems.push(...(await findFontProblems(config.fonts, root)));

    const dryRun = !args.renderOnly && !args.spend;
    if (problems.length > 0) {
      for (const problem of problems) errOut(`\n${problem}`);
      if (dryRun) errOut("\nDry run: this run would be refused until the above is fixed, so there is nothing to approve yet.");
      return 1;
    }
    if (dryRun) {
      out("\nDry run only. Re-run with --spend strict, auto or yolo to proceed.");
      return 0;
    }

    const fontData = await loadFonts(config.fonts, root);
    await prepareFolders();
    let spentThisRun = 0;

    for (const { post, needsCall, model, estimate } of jobs) {
      const trial = args.trial ? trialPaths({ rawDir, model, slug: post.slug }) : null;
      const rawPath = trial ? trial.illustration : path.join(rawDir, `${post.slug}.png`);
      const cardPath = trial ? trial.card : path.join(cardsDir, `${post.slug}.png`);

      if (needsCall) {
        spentTotal = ledgerTotal(ledger, ledgerFile);
        const verdict = canAfford({ ...limits, estimate, spentTotal, spentThisRun });
        if (!verdict.ok) {
          const remaining = jobs.slice(jobs.findIndex((j) => j.post === post)).filter((j) => j.needsCall).map((j) => j.post.slug);
          errOut(verdict.reason === "run"
            ? `\nStopping: $${spentThisRun.toFixed(4)} spent this run; the next call would risk exceeding the $${args.budget.toFixed(2)} --budget for this run.`
            : `\nStopping: $${spentTotal.toFixed(4)} spent in total; the next call would risk exceeding the $${config.budget.toFixed(2)} budget.`);
          errOut(`Posts not yet generated: ${remaining.join(", ")}`);
          return stopWith(1);
        }

        out(`Generating illustration for "${post.slug}"...`);
        let result;
        try {
          result = await generateIllustration({
            post,
            apiKey: env.OPENROUTER_API_KEY,
            model,
            stylePrompt: config.stylePrompt,
            params: config.modelParams?.[model] ?? {},
            fetchImpl,
          });
        } catch (err) {
          errOut(err.message);
          return stopWith(1);
        }
        // Record the spend before anything else touches the disk: if saving
        // the image fails after a billed call, the ledger must still know.
        ledger.push({ slug: post.slug, model, cost: result.cost, timestamp: new Date().toISOString() });
        await saveLedger(ledgerFile, ledger);
        await writeFile(rawPath, result.buffer);

        if (result.cost === null) {
          errOut(
            `\nOpenRouter didn't report a numeric usage.cost for "${post.slug}". The image was generated (and likely billed) so it's cached at ${relToRoot(rawPath)} and a ledger entry was recorded with cost: null, but the actual spend is unresolved. Fix that entry in ${relToRoot(ledgerFile)} by hand before running again.`
          );
          return stopWith(1);
        }

        spentThisRun += result.cost;
        spentTotal += result.cost;
        out(`  cost: $${result.cost.toFixed(4)} (this run: $${spentThisRun.toFixed(4)}, total: $${spentTotal.toFixed(4)})`);
      } else if (!args.renderOnly) {
        out(`Reusing cached illustration for "${post.slug}" (no API call).`);
      }

      const categoryName = post.category ? categories.get(post.category) ?? post.category : "";
      const cardBuffer = await renderCard({
        post,
        categoryName,
        illustrationPngBuffer: await readFile(rawPath),
        fontData,
        brand: config.brand,
        fonts: config.fonts,
      });
      await writeFile(cardPath, cardBuffer);
      out(`  wrote ${relToRoot(cardPath)}`);
    }

    await sync();
    if (args.trial) out(`\nTrial output is in ${path.relative(root, path.join(rawDir, "trial"))}. Nothing in the real cards, illustrations or manifest was touched.`);

    const finalTotal = ledgerTotal(ledger, ledgerFile);
    out(`\nDone. Ledger total: $${finalTotal.toFixed(4)} of $${config.budget.toFixed(2)}.`);
    if (finalTotal > config.budget + 1e-9) {
      out(`WARNING: spending is over the budget. --spend strict and auto will refuse to spend until "budget" is raised in the config.`);
    }
    return 0;
  }
}
