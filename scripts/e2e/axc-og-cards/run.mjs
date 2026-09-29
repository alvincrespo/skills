#!/usr/bin/env node
// End-to-end harness for the axc-og-cards skill. See README.md.
//
//   node run.mjs                       show the plan and its cost; run nothing
//   node run.mjs --run [--cases ...]   clone, set up, run and validate
//
// Every step is logged to <workdir>/report/run.log, and the results are
// written to <workdir>/report/REPORT.md.

import { cpSync, existsSync, mkdirSync, readFileSync, readdirSync, rmSync, writeFileSync, copyFileSync } from "node:fs";
import { createRequire } from "node:module";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { CASES, commonChecks } from "./cases.mjs";
import { createLogger, runProcess, snapshot, makeChecks, redact, money, commandLine } from "./lib.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(HERE, "../../..");
const SKILL_DIR = path.join(REPO_ROOT, "axc-og-cards");
const SKILL_NAME = "axc-og-cards";

const require = createRequire(path.join(SKILL_DIR, "package.json"));

// A small purpose-built Bridgetown blog, so the tests don't depend on anyone's
// personal site. Point --repo at any other site (a URL or a local path).
const DEFAULT_REPO = "https://github.com/alvincrespo/axc-og-fixture.git";

const USAGE = `Usage: node run.mjs [options]

  (no --run)             print the plan and the cost, run nothing
  --run                  do it: clone, set up each case, run it, validate, write the report
  --list                 list the cases and exit
  --cases a,b | free | paid | all    which cases (default: all)
  --driver agent|script  agent = a headless 'claude -p' session in the case folder that
                         runs the skill (default); script = call the skill's script directly,
                         to tell a script bug from an agent/SKILL.md problem
  --repo URL|PATH        site to clone (default ${DEFAULT_REPO})
  --ref BRANCH           branch or tag to clone
  --workdir DIR          where everything goes (default: a new folder under the system temp dir)
  --model MODEL          model for the agent driver
  --site-size N          posts kept for the backfill cases (default per case)
  --full-site            backfill every eligible post of the site instead of a trimmed copy
                         (the cost gate assumes up to 48 images; be sure)
  --max-spend USD        refuse to start if the planned OpenRouter spend exceeds this (default 1.00)
  --agent-max-usd USD    spend cap for each agent session (default 2)
  --timeout-min N        per-case timeout (default 12)
  --fresh-install        don't copy node_modules; the agent must run npm install itself
  --keep-legacy          keep the website's old scripts/og-cards.mjs in the case folders
  --cleanup              delete the case folders afterwards (the report is always kept)
`;

function parseArgs(argv) {
  const o = { run: false, list: false, cases: "all", driver: "agent", repo: DEFAULT_REPO, ref: null,
    workdir: null, model: null, siteSize: null, fullSite: false, maxSpend: 1.0, agentMaxUsd: 2, timeoutMin: 12,
    freshInstall: false, keepLegacy: false, cleanup: false };
  const take = (i, flag) => {
    const v = argv[i + 1];
    if (v === undefined || v.startsWith("--")) throw new Error(`${flag} requires a value`);
    return v;
  };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    switch (a) {
      case "--run": o.run = true; break;
      case "--list": o.list = true; break;
      case "--full-site": o.fullSite = true; break;
      case "--fresh-install": o.freshInstall = true; break;
      case "--keep-legacy": o.keepLegacy = true; break;
      case "--cleanup": o.cleanup = true; break;
      case "--cases": o.cases = take(i++, a); break;
      case "--driver": o.driver = take(i++, a); break;
      case "--repo": o.repo = take(i++, a); break;
      case "--ref": o.ref = take(i++, a); break;
      case "--workdir": o.workdir = path.resolve(take(i++, a)); break;
      case "--model": o.model = take(i++, a); break;
      case "--site-size": o.siteSize = Number(take(i++, a)); break;
      case "--max-spend": o.maxSpend = Number(take(i++, a)); break;
      case "--agent-max-usd": o.agentMaxUsd = Number(take(i++, a)); break;
      case "--timeout-min": o.timeoutMin = Number(take(i++, a)); break;
      case "-h": case "--help": console.log(USAGE); process.exit(0); break;
      default: throw new Error(`Unknown option ${a}\n\n${USAGE}`);
    }
  }
  if (!["agent", "script"].includes(o.driver)) throw new Error("--driver must be agent or script");
  for (const [k, v] of [["--max-spend", o.maxSpend], ["--agent-max-usd", o.agentMaxUsd], ["--timeout-min", o.timeoutMin]]) {
    if (!Number.isFinite(v) || v <= 0) throw new Error(`${k} must be a positive number`);
  }
  if (o.siteSize !== null && (!Number.isInteger(o.siteSize) || o.siteSize < 1)) throw new Error("--site-size must be a positive whole number");
  return o;
}

function selectCases(spec) {
  if (spec === "all") return CASES;
  if (spec === "free") return CASES.filter((c) => !c.paid);
  if (spec === "paid") return CASES.filter((c) => c.paid);
  const ids = spec.split(",").map((s) => s.trim()).filter(Boolean);
  const unknown = ids.filter((id) => !CASES.some((c) => c.id === id));
  if (unknown.length > 0) throw new Error(`Unknown case(s): ${unknown.join(", ")}. Try --list.`);
  return ids.map((id) => CASES.find((c) => c.id === id));
}

const EST = 0.035; // matches the config template's estimatedCostPerImage
function plannedCalls(def, opts) {
  if (opts.fullSite && def.siteSize) return def.id === "backfill" ? 48 : def.expectCalls;
  if (opts.siteSize && def.id === "backfill") return opts.siteSize;
  return def.expectCalls;
}

function printPlan(cases, opts) {
  const rows = cases.map((c) => ({ c, calls: plannedCalls(c, opts) }));
  const total = rows.reduce((n, r) => n + r.calls * EST, 0);
  console.log(`\nPlan (${opts.driver} driver): ${cases.length} case(s)\n`);
  for (const { c, calls } of rows) {
    console.log(`  ${c.paid ? "PAID" : "free"}  ${c.id.padEnd(28)} ${calls ? `up to ~${money(calls * EST)} (${calls} image${calls > 1 ? "s" : ""})` : "$0"}`);
    console.log(`        ${c.title}`);
    console.log(`        /axc-og-cards ${c.args.join(" ")}`);
  }
  console.log(`\n  Planned OpenRouter spend: about ${money(total)} (limit for this run: ${money(opts.maxSpend)})`);
  console.log(`  Paid cases need OPENROUTER_API_KEY in the environment; free cases get a dummy key so they can't spend.`);
  console.log(`  Nothing has been run. Add --run to execute.\n`);
  return total;
}

const loadJson = (file, fallback) => (existsSync(file) ? JSON.parse(readFileSync(file, "utf8")) : fallback);
const sortNewest = (posts) => [...posts].sort((a, b) => (b.date?.getTime() ?? -Infinity) - (a.date?.getTime() ?? -Infinity) || a.slug.localeCompare(b.slug));

// --- the agent's stream-json output ------------------------------------------

function textOf(content) {
  if (typeof content === "string") return content;
  if (Array.isArray(content)) return content.map((c) => (typeof c === "string" ? c : c?.text ?? "")).join("\n");
  return "";
}

function parseStream(raw) {
  const s = { scriptCommands: [], finalText: "", isError: false, costUsd: null, turns: null, toolResults: [], transcript: [] };
  for (const line of raw.split("\n")) {
    if (!line.trim()) continue;
    let ev;
    try { ev = JSON.parse(line); } catch { continue; }
    if (ev.type === "assistant") {
      for (const item of ev.message?.content ?? []) {
        if (item.type === "text") s.transcript.push(`**Agent:**\n\n${item.text}\n`);
        if (item.type === "tool_use") {
          const cmd = item.input?.command ?? JSON.stringify(item.input);
          s.transcript.push(`**Tool use — ${item.name}:**\n\n\`\`\`\n${cmd}\n\`\`\`\n`);
          if (item.name === "Bash" && /og-cards\.mjs/.test(cmd)) s.scriptCommands.push(cmd);
        }
      }
    } else if (ev.type === "user") {
      for (const item of Array.isArray(ev.message?.content) ? ev.message.content : []) {
        if (item.type === "tool_result") {
          const t = textOf(item.content);
          s.toolResults.push(t);
          s.transcript.push(`**Tool result:**\n\n\`\`\`\n${t}\n\`\`\`\n`);
        }
      }
    } else if (ev.type === "result") {
      s.finalText = ev.result ?? "";
      s.isError = Boolean(ev.is_error);
      s.costUsd = ev.total_cost_usd ?? null;
      s.turns = ev.num_turns ?? null;
    }
  }
  return s;
}

// --- one case ----------------------------------------------------------------

async function runCase(def, env) {
  const { opts, logger, baseSite, workdir, reportDir, deps } = env;
  const { loadPosts, sharp, YAML } = deps;
  const caseDir = path.join(workdir, "cases", def.id);
  const outDir = path.join(reportDir, "cases", def.id);
  mkdirSync(outDir, { recursive: true });
  const steps = [];
  const log = { info: (m) => { logger.info(m); steps.push(m); } };
  const result = { driver: opts.driver, id: def.id, title: def.title, description: def.description, paid: def.paid, steps, checks: [], started: new Date().toISOString() };

  logger.step(`=== CASE ${def.id}: ${def.title} ===`);
  logger.info(def.description);

  try {
    // 1. fresh copy of the cloned site
    log.info(`Setup 1/7: copy the cloned site to ${caseDir} (without .git, node_modules or output)`);
    rmSync(caseDir, { recursive: true, force: true });
    const SKIP = new Set([".git", "node_modules", "output", ".bridgetown-cache"]);
    cpSync(baseSite, caseDir, { recursive: true, filter: (p) => !SKIP.has(path.basename(p)) });

    if (!opts.keepLegacy && existsSync(path.join(caseDir, "scripts/og-cards.mjs"))) {
      rmSync(path.join(caseDir, "scripts/og-cards.mjs"));
      log.info("  removed the website's old scripts/og-cards.mjs so the run can only use the skill (--keep-legacy to keep it)");
    }

    const budget = def.configBudget ?? 0.5;
    const cfgPath = path.join(caseDir, "og-cards.config.json");
    const siteConfigPath = path.join(caseDir, "og-cards.config.json");
    let config;
    if (existsSync(siteConfigPath)) {
      config = { ...JSON.parse(readFileSync(siteConfigPath, "utf8")), budget };
      log.info(`  the site has its own og-cards.config.json; using it with the budget set to ${money(budget)}`);
    } else {
      const template = JSON.parse(readFileSync(path.join(SKILL_DIR, "templates/og-cards.config.json"), "utf8"));
      config = {
        ...template,
        brand: { ...template.brand, byline: "Alvin Crespo", url: "alvincrespo.com" },
        budget,
        fonts: { ...template.fonts, sources: template.fonts.sources.map((s) => ({ ...s, path: `scripts/fonts/${path.basename(s.path)}` })) },
      };
      log.info("  the site has no og-cards.config.json; wrote one from the skill's template with fonts in scripts/fonts (the website's layout)");
    }
    const postsDir = path.join(caseDir, config.postsDir);
    const cardsDir = path.join(caseDir, config.cardsDir);
    const rawDir = path.join(caseDir, config.rawDir);
    const ledgerFile = path.join(caseDir, config.ledger);
    const manifestFile = path.join(caseDir, config.manifest.path);

    // 2. the site's size
    log.info("Setup 2/7: choose the posts");
    let posts = sortNewest(await loadPosts(postsDir, config.slugStrategy));
    const eligible = posts.filter((p) => !p.image);
    const size = opts.fullSite ? null : opts.siteSize ?? def.siteSize;
    let site = posts;
    if (def.siteSize || opts.siteSize) {
      site = size ? eligible.slice(0, size) : eligible;
      const keep = new Set(site.map((p) => p.file));
      let removed = 0;
      for (const p of posts) if (!keep.has(p.file)) { rmSync(p.file); removed++; }
      log.info(`  kept the ${site.length} newest post(s) that backfill would cover: ${site.map((p) => p.slug).join(", ")}`);
      log.info(`  removed ${removed} other post file(s) from the case folder (the shared clone is untouched)`);
    } else {
      site = eligible;
      log.info(`  whole site: ${posts.length} posts, ${eligible.length} without an image: override`);
    }
    const target = site[0];
    if (!target) throw new Error("no eligible post found in the clone");
    const targetRel = path.relative(caseDir, target.file);
    log.info(`  target post: ${target.slug} (${targetRel})`);

    const originalCardSha = snapshot(caseDir, [path.join(config.cardsDir, `${target.slug}.png`)]).get(path.join(config.cardsDir, `${target.slug}.png`));

    // 3. clean this skill's assets
    log.info(`Setup 3/7: clean the skill's assets (${def.clean}${def.deleteCardOnly ? ", card only" : ""})`);
    const rm = (p) => { if (existsSync(p)) { rmSync(p); log.info(`  deleted ${path.relative(caseDir, p)}`); } };
    if (def.clean === "all") {
      for (const dir of [cardsDir, rawDir]) for (const f of readdirSync(dir)) if (f.endsWith(".png")) rm(path.join(dir, f));
    } else if (def.clean === "target" || def.deleteCardOnly) {
      rm(path.join(cardsDir, `${target.slug}.png`));
      if (!def.deleteCardOnly) rm(path.join(rawDir, `${target.slug}.png`));
    } else {
      log.info("  nothing deleted");
    }
    const slugsWithCards = posts.map((p) => p.slug).filter((s) => existsSync(path.join(cardsDir, `${s}.png`))).sort();
    writeFileSync(manifestFile, YAML.stringify(Object.fromEntries(slugsWithCards.map((s) => [s, true]))));
    log.info(`  reset ${config.manifest.path} to match the cards on disk (${slugsWithCards.length} card(s))`);

    // 4. ledger and config
    const seed = def.seedOverBudget ? [{ slug: "e2e-seed", model: "e2e-seed", cost: Number((budget + 0.01).toFixed(4)), timestamp: new Date().toISOString() }] : [];
    writeFileSync(ledgerFile, JSON.stringify(seed, null, 2) + "\n");
    writeFileSync(cfgPath, JSON.stringify(config, null, 2) + "\n");
    log.info(`Setup 4/7: wrote a fresh ledger (${seed.length ? `seeded over budget: ${money(seed[0].cost)} against a ${money(budget)} budget` : "empty"}) and og-cards.config.json (budget ${money(budget)}, model ${config.model})`);

    // 5. copy the skill
    const skillDest = path.join(caseDir, ".claude/skills", SKILL_NAME);
    log.info(`Setup 5/7: copy the skill into ${path.relative(caseDir, skillDest)}${opts.freshInstall ? " (without node_modules)" : " (with node_modules)"}`);
    cpSync(SKILL_DIR, skillDest, { recursive: true, filter: (p) => opts.freshInstall ? path.basename(p) !== "node_modules" : true });

    // 6. case-specific breakage
    const ctxBase = { caseDir, log, config };
    if (def.mutate) { log.info("Setup 6/7: apply this case's deliberate breakage"); def.mutate(ctxBase); } else log.info("Setup 6/7: no case-specific changes");

    // 7. snapshot
    const fontDirs = [...new Set(config.fonts.sources.map((s) => path.dirname(s.path)))];
    const watched = [config.cardsDir, config.postsDir, ...fontDirs];
    const before = snapshot(caseDir, watched);
    log.info(`Setup 7/7: snapshot ${before.size} watched file(s) (cards, illustrations, posts and font folders) to detect stray changes`);

    // --- run -----------------------------------------------------------------
    const tokens = def.args.map((a) => (a === "{post}" ? targetRel : a));
    const runEnv = { ...process.env, NO_COLOR: "1" };
    if (def.keyMode === "real") log.info("  API key: the real OPENROUTER_API_KEY (this case can spend)");
    else if (def.keyMode === "dummy") { runEnv.OPENROUTER_API_KEY = "e2e-dummy-key-cannot-spend"; log.info("  API key: a dummy key (this case is free and can't spend)"); }
    else { delete runEnv.OPENROUTER_API_KEY; log.info("  API key: none (deliberately unset)"); }

    let run;
    let agent = null;
    if (opts.driver === "script") {
      const scriptArgs = [path.join(".claude/skills", SKILL_NAME, "scripts/og-cards.mjs"), "--config", "og-cards.config.json", ...tokens];
      result.command = commandLine("node", scriptArgs);
      logger.step(`Running the skill's script directly for ${def.id}`);
      run = await runProcess("node", scriptArgs, { cwd: caseDir, env: runEnv, logger, timeoutMs: opts.timeoutMin * 60_000 });
      writeFileSync(path.join(outDir, "output.txt"), redact(`--- stdout ---\n${run.stdout}\n--- stderr ---\n${run.stderr}\n--- exit ${run.code} ---\n`));
    } else {
      const prompt = `/${SKILL_NAME}${tokens.length ? " " + tokens.join(" ") : ""}\n\n${def.suffix}`;
      writeFileSync(path.join(outDir, "prompt.txt"), prompt);
      const allowed = ["Bash(node:*)", "Bash(npm install:*)", "Bash(ls:*)", "Bash(cat:*)", "Bash(grep:*)", "Read", "Glob", "Grep", "Skill"].join(",");
      const args = ["-p", prompt, "--output-format", "stream-json", "--verbose", "--allowedTools", allowed,
        "--max-budget-usd", String(opts.agentMaxUsd), "--no-session-persistence", "--setting-sources", "project,local", "--strict-mcp-config"];
      if (opts.model) args.push("--model", opts.model);
      result.command = commandLine("claude", args);
      logger.step(`Launching the agent (headless claude) in ${caseDir}. Prompt:\n${prompt}`);
      const streamFile = path.join(outDir, "agent.stream.jsonl");
      const onLine = (line) => {
        try {
          const ev = JSON.parse(line);
          if (ev.type === "assistant") for (const it of ev.message?.content ?? []) {
            if (it.type === "tool_use") logger.info(`  agent -> ${it.name}: ${String(it.input?.command ?? JSON.stringify(it.input)).slice(0, 400)}`);
            if (it.type === "text") logger.info(`  agent says: ${it.text.replace(/\s+/g, " ").slice(0, 300)}`);
          }
          if (ev.type === "result") logger.info(`  agent finished: ${ev.subtype}${ev.is_error ? " (error)" : ""}, cost ${ev.total_cost_usd ?? "?"} USD`);
        } catch { /* not JSON */ }
      };
      run = await runProcess("claude", args, { cwd: caseDir, env: runEnv, logger, streamFile, onStdoutLine: onLine, timeoutMs: opts.timeoutMin * 60_000 });
      const parsed = parseStream(run.stdout);
      agent = parsed;
      writeFileSync(path.join(outDir, "transcript.md"), redact(`# Agent transcript: ${def.id}\n\n## Prompt\n\n\`\`\`\n${prompt}\n\`\`\`\n\n${parsed.transcript.join("\n")}\n\n## Final message\n\n${parsed.finalText}\n`));
      if (run.stderr.trim()) writeFileSync(path.join(outDir, "agent.stderr.txt"), redact(run.stderr));
    }
    log.info(`Run finished in ${(run.durationMs / 1000).toFixed(1)}s with exit code ${run.code}${run.timedOut ? " (TIMED OUT)" : ""}`);

    // --- validate ----------------------------------------------------------
    logger.step(`Validating ${def.id}`);
    const after = snapshot(caseDir, watched);
    const ledger = loadJson(ledgerFile, null);
    const manifest = existsSync(manifestFile) ? YAML.parse(readFileSync(manifestFile, "utf8")) ?? {} : {};
    const cardRel = (s) => path.join(config.cardsDir, `${s}.png`);
    const rawRel = (s) => path.join(config.rawDir, `${s}.png`);
    const newEntries = Array.isArray(ledger) ? ledger.slice(seed.length) : [];
    const changedFiles = () => [...new Set([...before.keys(), ...after.keys()])].filter((f) => before.get(f) !== after.get(f)).sort();
    const output = agent ? [agent.finalText, ...agent.toolResults].join("\n") : `${run.stdout}\n${run.stderr}`;

    const ctx = {
      caseDir, config, log, sharp, posts: site, target, seed, ledger: ledger ?? [], manifest, newEntries, run, agent, text: output,
      newSpend: newEntries.reduce((n, e) => n + (typeof e.cost === "number" ? e.cost : 0), 0),
      ledgerTotal: (ledger ?? []).reduce((n, e) => n + (typeof e.cost === "number" ? e.cost : 0), 0),
      cardPath: (s) => path.join(caseDir, cardRel(s)), rawPath: (s) => path.join(caseDir, rawRel(s)), cardRel, rawRel,
      exists: (p) => existsSync(p),
      originalCardSha,
      currentSha: (rel) => after.get(rel),
      unchanged: (rel) => before.get(rel) === after.get(rel),
      diffAll: changedFiles,
      cardSlugsOnDisk: () => readdirSync(cardsDir).filter((f) => f.endsWith(".png")).map((f) => f.slice(0, -4)),
      unexpectedChanges: (mode) => {
        const slugs = mode === "target" ? [target.slug] : mode === "site" ? site.map((p) => p.slug) : [];
        const allowed = new Set(slugs.flatMap((s) => [cardRel(s), rawRel(s)]));
        return changedFiles().filter((f) => !allowed.has(f));
      },
    };
    const r = makeChecks();
    if (!Array.isArray(ledger)) r.fail("ledger file could not be read");
    else {
      await def.validate(ctx, r);
      commonChecks(ctx, r, def);
    }
    result.checks = r.list;
    for (const c of r.list) logger.check(c);

    result.newEntries = newEntries;
    result.newSpend = ctx.newSpend;
    result.agentCost = agent?.costUsd ?? null;
    result.exitCode = run.code;
    result.durationMs = run.durationMs;
    result.summaryText = (agent ? agent.finalText : output).trim();
    result.commands = agent?.scriptCommands ?? [];

    // artifacts for a human to look at
    const artDir = path.join(outDir, "artifacts");
    for (const rel of new Set([...after.keys()].filter((f) => before.get(f) !== after.get(f) && after.has(f)))) {
      mkdirSync(artDir, { recursive: true });
      const flat = rel.replace(/[\\/]/g, "__");
      copyFileSync(path.join(caseDir, rel), path.join(artDir, flat));
      (result.artifacts ??= []).push(path.join("cases", def.id, "artifacts", flat));
    }
    writeFileSync(path.join(outDir, "ledger.json"), JSON.stringify(ledger, null, 2));
    writeFileSync(path.join(outDir, "checks.json"), JSON.stringify(r.list, null, 2));
  } catch (err) {
    logger.error(`Case ${def.id} could not run: ${err.stack ?? err.message}`);
    result.checks.push({ status: "fail", name: "the case ran to completion", detail: err.message });
  }

  result.status = result.checks.some((c) => c.status === "fail") ? "FAIL" : result.checks.some((c) => c.status === "warn") ? "WARN" : "PASS";
  logger.step(`=== ${def.id}: ${result.status} ===`);
  if (opts.cleanup) rmSync(caseDir, { recursive: true, force: true });
  return result;
}

// --- the report --------------------------------------------------------------

function writeReport({ reportDir, results, meta }) {
  const icon = { PASS: "PASS", WARN: "WARN", FAIL: "FAIL" };
  const totalSpend = results.reduce((n, r) => n + (r.newSpend ?? 0), 0);
  const lines = [
    `# axc-og-cards end-to-end report`, "",
    `Generated ${meta.finished}. Everything below is also in \`run.log\` in this folder, in order.`, "",
    `## Result: ${results.every((r) => r.status !== "FAIL") ? "no failures" : `${results.filter((r) => r.status === "FAIL").length} FAILED`}`, "",
    `| Case | Result | Checks | OpenRouter spend | Agent cost | Time |`, `|---|---|---|---|---|---|`,
    ...results.map((r) => `| \`${r.id}\` | ${icon[r.status]} | ${r.checks.filter((c) => c.status === "pass").length}/${r.checks.length} | ${money(r.newSpend ?? 0)} | ${r.agentCost != null ? `$${Number(r.agentCost).toFixed(2)}` : "-"} | ${r.durationMs ? `${(r.durationMs / 1000).toFixed(0)}s` : "-"} |`),
    "", `Total OpenRouter spend recorded in the ledgers: **${money(totalSpend)}**.`, "",
    `## Environment`, "", ...Object.entries(meta.env).map(([k, v]) => `- **${k}:** ${v}`), "",
  ];
  for (const r of results) {
    lines.push(`## ${r.id}: ${r.title}`, "", `**${icon[r.status]}** ${r.description}`, "", "### Setup", "", ...r.steps.map((s) => `- ${s.trim()}`), "");
    if (r.command) lines.push("### Command", "", "```", r.command, "```", "");
    if (r.commands?.length) lines.push("### What the agent ran", "", ...r.commands.map((c) => "```\n" + c + "\n```"), "");
    if (r.summaryText) lines.push("### Output" + (r.driver === "agent" ? " (the agent's final message)" : " (the script's stdout and stderr)"), "", "```", r.summaryText.slice(0, 3000), "```", "");
    if (r.newEntries) lines.push("### Ledger entries added", "", r.newEntries.length ? r.newEntries.map((e) => `- \`${e.slug}\` — ${e.model} — ${e.cost === null ? "cost unknown" : money(e.cost)}`).join("\n") : "None.", "");
    lines.push("### Validation", "", `| | Check | Detail |`, `|---|---|---|`, ...r.checks.map((c) => `| ${c.status.toUpperCase()} | ${c.name.replace(/\|/g, "\\|")} | ${String(c.detail).replace(/\|/g, "\\|").replace(/\n/g, " ")} |`), "");
    if (r.artifacts?.length) lines.push("### For a human to review", "", "Look at each generated card for stray text, letters or faces in the illustration.", "", ...r.artifacts.map((a) => `- \`${a}\``), "");
    lines.push(`Raw logs: \`cases/${r.id}/\` (${["prompt.txt", "transcript.md", "agent.stream.jsonl", "output.txt", "ledger.json", "checks.json"].join(", ")} as applicable).`, "");
  }
  const text = redact(lines.join("\n"));
  writeFileSync(path.join(reportDir, "REPORT.md"), text);
  writeFileSync(path.join(reportDir, "report.json"), redact(JSON.stringify({ meta, results }, null, 2)));
}

function scanForSecrets(dir) {
  const key = process.env.OPENROUTER_API_KEY;
  if (!key || key.length < 8) return [];
  const hits = [];
  const walk = (d) => {
    for (const n of readdirSync(d, { withFileTypes: true })) {
      const p = path.join(d, n.name);
      if (n.isDirectory()) walk(p);
      else if (!/\.(png|jpg)$/.test(n.name)) {
        const t = readFileSync(p, "utf8");
        if (t.includes(key)) { hits.push(path.relative(dir, p)); writeFileSync(p, redact(t)); }
      }
    }
  };
  walk(dir);
  return hits;
}

// --- main --------------------------------------------------------------------

async function main() {
  const opts = parseArgs(process.argv.slice(2));
  const cases = selectCases(opts.cases);
  const planned = plannedCalls;
  const totalPlanned = cases.reduce((n, c) => n + planned(c, opts) * EST, 0);

  if (opts.list || !opts.run) {
    printPlan(cases, opts);
    if (opts.run === false) process.exit(0);
  }
  if (totalPlanned > opts.maxSpend + 1e-9) {
    console.error(`Refusing to start: the plan is about ${money(totalPlanned)}, over --max-spend ${money(opts.maxSpend)}. Pick fewer cases or raise --max-spend.`);
    process.exit(2);
  }
  const needsRealKey = cases.some((c) => c.keyMode === "real");
  if (needsRealKey && !process.env.OPENROUTER_API_KEY) {
    console.error("Paid cases are selected but OPENROUTER_API_KEY isn't set. Set it in the environment (never on the command line), or run --cases free.");
    process.exit(2);
  }
  if (!existsSync(path.join(SKILL_DIR, "node_modules"))) {
    console.error(`The skill's dependencies aren't installed. Run: npm install --prefix ${SKILL_DIR}`);
    process.exit(2);
  }

  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  const workdir = opts.workdir ?? path.join(os.tmpdir(), `axc-og-e2e-${stamp}`);
  const reportDir = path.join(workdir, "report");
  mkdirSync(reportDir, { recursive: true });
  const logger = createLogger(path.join(reportDir, "run.log"));
  const started = new Date();

  logger.step(`axc-og-cards end-to-end run started`);
  logger.info(`work folder: ${workdir}`);
  logger.info(`driver: ${opts.driver}; cases: ${cases.map((c) => c.id).join(", ")}`);
  logger.info(`planned OpenRouter spend: about ${money(totalPlanned)} (limit ${money(opts.maxSpend)})`);
  logger.info(`options: ${JSON.stringify({ ...opts, workdir: undefined })}`);

  const env = {};
  const sh = async (cmd, args, cwd) => (await runProcess(cmd, args, { cwd, env: process.env, logger })).stdout.trim();

  // Clone once; every case then gets its own copy.
  logger.step("Cloning the site");
  const baseSite = path.join(workdir, "base-site");
  rmSync(baseSite, { recursive: true, force: true });
  const cloneArgs = ["clone", "--depth", "1", ...(opts.ref ? ["--branch", opts.ref] : []), opts.repo, baseSite];
  const clone = await runProcess("git", cloneArgs, { cwd: workdir, env: process.env, logger });
  if (clone.code !== 0) {
    logger.error(`git clone failed (exit ${clone.code}): ${clone.stderr.trim()}`);
    process.exit(1);
  }
  const siteSha = await sh("git", ["rev-parse", "HEAD"], baseSite);
  const skillSha = await sh("git", ["rev-parse", "--short", "HEAD"], REPO_ROOT);
  const skillDirty = await sh("git", ["status", "--porcelain", "--", "axc-og-cards"], REPO_ROOT);
  const claudeVersion = opts.driver === "agent" ? await sh("claude", ["--version"], workdir) : "not used (script driver)";
  logger.info(`site commit: ${siteSha}`);
  logger.info(`skill commit: ${skillSha}${skillDirty ? " (with uncommitted changes in axc-og-cards/)" : ""}`);

  const deps = {
    loadPosts: (await import(pathToFileURL(path.join(SKILL_DIR, "scripts/lib/posts.mjs")).href)).loadPosts,
    sharp: require("sharp"),
    YAML: require("yaml"),
  };

  const results = [];
  for (const def of cases) results.push(await runCase(def, { opts, logger, baseSite, workdir, reportDir, deps }));

  const leaked = scanForSecrets(reportDir);
  const finished = new Date().toISOString();
  const meta = {
    started: started.toISOString(), finished,
    env: {
      "Driver": opts.driver, "Site": `${opts.repo} @ ${siteSha.slice(0, 10)}`,
      "Skill": `${skillSha}${skillDirty ? " + uncommitted changes" : ""}`, "Node": process.version, "Claude Code": claudeVersion,
      "Agent model": opts.model ?? "default", "OS": `${os.type()} ${os.release()}`, "Work folder": workdir,
      "API key handling": leaked.length ? `LEAKED into ${leaked.join(", ")} (redacted afterwards)` : "the OpenRouter key appears in no log or report file",
    },
  };
  writeReport({ reportDir, results, meta });

  const failed = results.filter((r) => r.status === "FAIL");
  logger.step(`Done. ${results.length - failed.length}/${results.length} case(s) without failures. Report: ${path.join(reportDir, "REPORT.md")}`);
  if (leaked.length) logger.error(`The API key was found in: ${leaked.join(", ")}. It has been redacted, but that is a bug to look into.`);
  process.exit(failed.length > 0 || leaked.length > 0 ? 1 : 0);
}

main().catch((err) => { console.error(err.message ?? err); process.exit(2); });
