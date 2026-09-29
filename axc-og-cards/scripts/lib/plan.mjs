import path from "node:path";

const EPS = 1e-9;

// Whether one more paid call fits. `spentTotal` is the ledger total (which
// includes this run's spend so far); `spentThisRun` is only this run's.
//   strict, auto  the config's total budget applies
//   yolo          the total budget is ignored
//   runBudget     the --budget amount, when given, applies in every mode
export function canAfford({ estimate, spentTotal, spentThisRun, mode, totalBudget, runBudget }) {
  if (mode !== "yolo" && spentTotal + estimate > totalBudget + EPS) return { ok: false, reason: "total" };
  if (runBudget != null && spentThisRun + estimate > runBudget + EPS) return { ok: false, reason: "run" };
  return { ok: true };
}

// How many paid calls fit under the limits before the run starts (Infinity if
// nothing limits it).
export function affordableCalls({ estimate, spentTotal, mode, totalBudget, runBudget }) {
  let n = Infinity;
  if (mode !== "yolo") n = Math.min(n, Math.floor((totalBudget - spentTotal) / estimate + EPS));
  if (runBudget != null) n = Math.min(n, Math.floor(runBudget / estimate + EPS));
  return Math.max(0, n);
}

export function describeLimit({ mode, totalBudget, spentTotal, runBudget }) {
  const parts = [];
  if (runBudget != null) parts.push(`$${runBudget.toFixed(2)} for this run (--budget)`);
  if (mode !== "yolo") {
    parts.push(`$${Math.max(0, totalBudget - spentTotal).toFixed(2)} left of the $${totalBudget.toFixed(2)} total`);
  }
  return parts.length > 0 ? parts.join("; ") : "none (--spend yolo ignores the total budget)";
}

function byDateDescending(a, b) {
  if (a.date && b.date) return b.date - a.date || a.slug.localeCompare(b.slug);
  if (a.date) return -1;
  if (b.date) return 1;
  return a.slug.localeCompare(b.slug);
}

// Turns the targets and flags into the list of jobs to run.
//   hasCard, hasRaw  Sets of slugs that already have a finished card / a saved
//                    illustration
// Returns { jobs: [{ post, needsCall }], notes }. Throws if a named path isn't
// a post inside postsDir.
export function selectJobs({ posts, args, postsDir, cwd, hasCard, hasRaw }) {
  const notes = [];
  const jobs = [];

  if (args.paths.length > 0) {
    const seen = new Set();
    for (const given of args.paths) {
      const file = path.resolve(cwd, given);
      const rel = path.relative(postsDir, file);
      if (rel.startsWith("..") || path.isAbsolute(rel)) {
        throw new Error(`${given} is outside the posts folder (${path.relative(cwd, postsDir) || postsDir}).`);
      }
      const post = posts.find((p) => p.file === file);
      if (!post) {
        throw new Error(`${given} isn't a post: the file wasn't found, isn't Markdown, or has no title in its front matter (drafts are skipped).`);
      }
      if (seen.has(post.slug)) continue;
      seen.add(post.slug);

      if (args.renderOnly) {
        if (hasRaw.has(post.slug)) jobs.push({ post, needsCall: false });
        else notes.push(`Skipping "${post.slug}": no saved illustration to render from.`);
      } else if (post.image && !args.includeOverridden) {
        notes.push(`Skipping "${post.slug}": its front matter sets image: ${post.image} (use --include-overridden to generate a card anyway).`);
      } else if (hasCard.has(post.slug) && !args.regen) {
        notes.push(`Skipping "${post.slug}": it already has a card (use --regen to replace it).`);
      } else {
        jobs.push({ post, needsCall: args.regen || !hasRaw.has(post.slug) });
      }
    }
    return { jobs, notes };
  }

  // --backfill: newest first, so a run stopped by a limit has covered the
  // posts most likely to be shared.
  let candidates = [...posts].sort(byDateDescending);
  if (args.since || args.before) {
    const since = args.since ? new Date(`${args.since}T00:00:00Z`) : null;
    const before = args.before ? new Date(`${args.before}T00:00:00Z`) : null;
    const undated = candidates.filter((p) => !p.date).length;
    if (undated > 0) notes.push(`Ignoring ${undated} post(s) with no date, since --since/--before need one.`);
    candidates = candidates.filter((p) => p.date && (!since || p.date >= since) && (!before || p.date < before));
  }

  let skippedOverridden = 0;
  let paid = 0;
  let cutByLimit = 0;
  for (const post of candidates) {
    if (args.renderOnly) {
      if (hasRaw.has(post.slug)) jobs.push({ post, needsCall: false });
      continue;
    }
    if (hasCard.has(post.slug)) continue;
    if (post.image && !args.includeOverridden) {
      skippedOverridden++;
      continue;
    }
    const needsCall = !hasRaw.has(post.slug);
    if (needsCall && args.limit != null && paid >= args.limit) {
      cutByLimit++;
      continue;
    }
    if (needsCall) paid++;
    jobs.push({ post, needsCall });
  }
  if (skippedOverridden > 0) {
    notes.push(`Skipping ${skippedOverridden} post(s) whose front matter sets image: (use --include-overridden to generate cards for them).`);
  }
  if (cutByLimit > 0) notes.push(`--limit ${args.limit} leaves ${cutByLimit} more post(s) for a later run.`);
  return { jobs, notes };
}

// The lines printed when the command is run with no target. Read-only.
export function buildStatus({ posts, hasCard, hasRaw, spentTotal, config }) {
  const withCard = posts.filter((p) => hasCard.has(p.slug));
  const missing = posts.filter((p) => !hasCard.has(p.slug));
  const overridden = missing.filter((p) => p.image);
  const eligible = missing.filter((p) => !p.image);
  const free = eligible.filter((p) => hasRaw.has(p.slug)).length;
  const paid = eligible.length - free;
  const est = config.estimatedCostPerImage;
  const remaining = config.budget - spentTotal;

  const lines = [
    `Posts: ${posts.length} (${withCard.length} with a card, ${missing.length} without)`,
  ];
  if (eligible.length > 0) {
    lines.push(`Missing a card: ${eligible.length} (${free} can render from a saved illustration for free, ${paid} need a paid one)`);
  }
  if (overridden.length > 0) {
    lines.push(`Skipped: ${overridden.length} post(s) set image: in their front matter (--include-overridden to include them)`);
  }
  lines.push(`Ledger: $${spentTotal.toFixed(4)} spent of the $${config.budget.toFixed(2)} budget ($${Math.max(0, remaining).toFixed(4)} left)`);
  if (remaining < -EPS) {
    lines.push(`WARNING: spending is over the budget. --spend strict and auto will refuse to spend until "budget" is raised in the config.`);
  }
  lines.push("");

  if (eligible.length === 0) {
    lines.push("Nothing to do: every post has a card.");
    return lines;
  }
  lines.push(`Backfilling all of them would cost about $${(paid * est).toFixed(2)} (${paid} x $${est}).`);
  lines.push("Next:");
  const fit = affordableCalls({ estimate: est, spentTotal, mode: "strict", totalBudget: config.budget });
  if (paid > 0 && fit < paid) {
    lines.push(fit > 0
      ? `  /axc-og-cards --backfill --limit ${fit}    (all ${paid} would go past the budget)`
      : `  raise "budget" in the config first: there is no room for another paid illustration`);
  } else {
    lines.push("  /axc-og-cards --backfill");
  }
  lines.push("  /axc-og-cards path/to/post.md");
  return lines;
}
