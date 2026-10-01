import { test } from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { parseArgs } from "./lib/args.mjs";
import { canAfford, affordableCalls, describeLimit, selectJobs, buildStatus } from "./lib/plan.mjs";

// --- args ---------------------------------------------------------------

test("no target is a status run", () => {
  const a = parseArgs([]);
  assert.equal(a.kind, "status");
  assert.equal(a.config, "og-cards.config.json");
});

test("post paths and --backfill are the two kinds of target", () => {
  const p = parseArgs(["a.md", "b.md", "--spend", "auto", "--budget", "2.50"]);
  assert.deepEqual([p.kind, p.paths, p.spend, p.budget], ["run", ["a.md", "b.md"], "auto", 2.5]);
  const b = parseArgs(["--backfill", "--limit", "10", "--since=2024-01-01", "--before", "2025-01-01"]);
  assert.deepEqual([b.backfill, b.limit, b.since, b.before], [true, 10, "2024-01-01", "2025-01-01"]);
});

test("paths and --backfill together are refused", () => {
  assert.throws(() => parseArgs(["a.md", "--backfill"]), /not both/);
});

test("unknown flags are errors, not silent dry runs", () => {
  assert.throws(() => parseArgs(["a.md", "--yess"]), /Unknown flag --yess/);
  assert.throws(() => parseArgs(["a.md", "--render_only"]), /Unknown flag/);
});

test("removed flags say what replaced them", () => {
  assert.throws(() => parseArgs(["--yes"]), /--spend/);
  assert.throws(() => parseArgs(["--only", "a"]), /post paths/);
});

test("a flag's value can't be another flag", () => {
  assert.throws(() => parseArgs(["a.md", "--spend", "--backfill"]), /--spend requires a value/);
  assert.throws(() => parseArgs(["--backfill", "--limit"]), /--limit requires a value/);
});

test("--spend takes strict, auto or yolo only", () => {
  assert.throws(() => parseArgs(["a.md", "--spend", "5"]), /strict, auto, yolo/);
  assert.throws(() => parseArgs(["a.md", "--spend", "YOLO"]), /strict, auto, yolo/);
});

test("--budget must be a positive dollar amount", () => {
  for (const bad of ["0", "-1", "$2", "abc", "1e3", "2."]) {
    assert.throws(() => parseArgs(["a.md", "--budget", bad]), /--budget must be a positive number/, bad);
  }
  assert.equal(parseArgs(["a.md", "--budget", "2"]).budget, 2);
});

test("--limit, --since and --before are validated and backfill-only", () => {
  assert.throws(() => parseArgs(["--backfill", "--limit", "0"]), /positive whole number/);
  assert.throws(() => parseArgs(["--backfill", "--limit", "2.5"]), /positive whole number/);
  assert.throws(() => parseArgs(["--backfill", "--since", "2024-13-01"]), /date like/);
  assert.throws(() => parseArgs(["--backfill", "--before", "2024-02-30"]), /date like/);
  assert.throws(() => parseArgs(["a.md", "--limit", "3"]), /only works with --backfill/);
});

test("spending flags without a target are refused rather than run as status", () => {
  assert.throws(() => parseArgs(["--spend", "yolo"]), /needs a target/);
  assert.throws(() => parseArgs(["--render-only"]), /needs a target/);
});

test("--regen only works with named paths", () => {
  assert.equal(parseArgs(["a.md", "--regen"]).regen, true);
  assert.throws(() => parseArgs(["--backfill", "--regen"]), /named post paths/);
});

// --- limits -------------------------------------------------------------

const base = { estimate: 0.035, spentTotal: 1, spentThisRun: 0, mode: "strict", totalBudget: 5, runBudget: null };

test("strict and auto stop at the total budget", () => {
  for (const mode of ["strict", "auto"]) {
    assert.equal(canAfford({ ...base, mode }).ok, true);
    const v = canAfford({ ...base, mode, spentTotal: 4.98 });
    assert.deepEqual([v.ok, v.reason], [false, "total"]);
  }
});

test("the total budget is not crossed by exactly one estimate", () => {
  assert.equal(canAfford({ ...base, spentTotal: 4.965 }).ok, true);
  assert.equal(canAfford({ ...base, spentTotal: 4.97 }).ok, false);
});

test("yolo ignores the total budget, even when the ledger is over it", () => {
  assert.equal(canAfford({ ...base, mode: "yolo", spentTotal: 9 }).ok, true);
});

test("--budget limits the run in every mode, including yolo", () => {
  for (const mode of ["strict", "auto", "yolo"]) {
    assert.equal(canAfford({ ...base, mode, runBudget: 0.1, spentThisRun: 0.06 }).ok, true);
    const v = canAfford({ ...base, mode, runBudget: 0.1, spentThisRun: 0.07 });
    assert.deepEqual([v.ok, v.reason], [false, "run"]);
  }
});

test("when both limits apply the lower one wins", () => {
  assert.equal(affordableCalls({ ...base, spentTotal: 4.9, runBudget: 1 }), 2); // total: $0.10 left
  assert.equal(affordableCalls({ ...base, spentTotal: 0, runBudget: 0.1 }), 2); // run: $0.10
  assert.equal(affordableCalls({ ...base, mode: "yolo" }), Infinity);
  assert.equal(affordableCalls({ ...base, mode: "yolo", runBudget: 0.07 }), 2);
  assert.equal(affordableCalls({ ...base, spentTotal: 6 }), 0);
});

test("describeLimit names each limit that applies", () => {
  assert.match(describeLimit({ ...base, runBudget: 1 }), /\$1\.00 for this run \(--budget\); \$4\.00 left of the \$5\.00 total/);
  assert.match(describeLimit({ ...base, mode: "yolo" }), /none/);
  assert.doesNotMatch(describeLimit({ ...base, mode: "yolo", runBudget: 3 }), /total/);
});

// --- choosing jobs ------------------------------------------------------

const postsDir = "/site/_posts";
const post = (slug, extra = {}) => ({ slug, file: `${postsDir}/${slug}.md`, title: slug, date: null, image: null, ...extra });
const d = (s) => new Date(`${s}T00:00:00Z`);
const posts = [
  post("old", { date: d("2020-01-01") }),
  post("mid", { date: d("2022-06-01") }),
  post("new", { date: d("2025-03-01") }),
  post("undated"),
  post("custom-image", { date: d("2024-01-01"), image: "/x.png" }),
];
const select = (args, sets = {}) =>
  selectJobs({
    posts,
    args: { paths: [], backfill: false, regen: false, renderOnly: false, includeOverridden: false, limit: null, since: null, before: null, ...args },
    postsDir,
    cwd: "/site",
    hasCard: new Set(sets.card ?? []),
    hasRaw: new Set(sets.raw ?? []),
  });
const slugs = (r) => r.jobs.map((j) => j.post.slug);

test("backfill goes newest first, with undated posts last", () => {
  assert.deepEqual(slugs(select({ backfill: true, includeOverridden: true })), ["new", "custom-image", "mid", "old", "undated"]);
});

test("backfill skips existing cards and image overrides, and says so", () => {
  const r = select({ backfill: true }, { card: ["mid"] });
  assert.deepEqual(slugs(r), ["new", "old", "undated"]);
  assert.match(r.notes.join("\n"), /1 post\(s\) whose front matter sets image/);
});

test("backfill only pays for illustrations that aren't saved", () => {
  const r = select({ backfill: true }, { raw: ["new"] });
  assert.deepEqual(r.jobs.map((j) => [j.post.slug, j.needsCall]), [["new", false], ["mid", true], ["old", true], ["undated", true]]);
});

test("--limit caps paid illustrations but not free re-renders", () => {
  const r = select({ backfill: true, limit: 1 }, { raw: ["old"] });
  assert.deepEqual(slugs(r), ["new", "old"]);
  assert.match(r.notes.join("\n"), /--limit 1 leaves 2 more/);
});

test("--since is inclusive, --before is exclusive, undated posts are dropped", () => {
  const r = select({ backfill: true, since: "2022-06-01", before: "2025-03-01" });
  assert.deepEqual(slugs(r), ["mid"]);
  assert.match(r.notes.join("\n"), /1 post\(s\) with no date/);
});

test("--render-only rebuilds every card that has a saved illustration", () => {
  const r = select({ backfill: true, renderOnly: true }, { card: ["new", "old"], raw: ["new", "old", "custom-image"] });
  assert.deepEqual(slugs(r), ["new", "custom-image", "old"]);
  assert.ok(r.jobs.every((j) => !j.needsCall));
});

test("a named path becomes a job; a repeated path counts once", () => {
  const r = select({ paths: ["_posts/mid.md", "/site/_posts/mid.md"] });
  assert.deepEqual(r.jobs.map((j) => [j.post.slug, j.needsCall]), [["mid", true]]);
});

test("a named post with a card is skipped unless --regen", () => {
  const r = select({ paths: ["_posts/mid.md"] }, { card: ["mid"], raw: ["mid"] });
  assert.deepEqual(r.jobs, []);
  assert.match(r.notes[0], /already has a card.*--regen/);
  const again = select({ paths: ["_posts/mid.md"], regen: true }, { card: ["mid"], raw: ["mid"] });
  assert.deepEqual(again.jobs.map((j) => [j.post.slug, j.needsCall]), [["mid", true]]);
});

test("a named post with an image override is skipped unless --include-overridden", () => {
  const r = select({ paths: ["_posts/custom-image.md"] });
  assert.deepEqual(r.jobs, []);
  assert.match(r.notes[0], /--include-overridden/);
  assert.deepEqual(slugs(select({ paths: ["_posts/custom-image.md"], includeOverridden: true })), ["custom-image"]);
});

test("a post whose file name starts with two dots is still inside the folder", () => {
  const dotted = post("..draft", { file: `${postsDir}/..draft.md` });
  const r = selectJobs({
    posts: [dotted],
    args: { paths: ["_posts/..draft.md"], backfill: false, regen: false, renderOnly: false, includeOverridden: false },
    postsDir,
    cwd: "/site",
    hasCard: new Set(),
    hasRaw: new Set(),
  });
  assert.deepEqual(r.jobs.map((j) => j.post.slug), ["..draft"]);
});

test("a named path outside the posts folder, or not a post, is an error", () => {
  assert.throws(() => select({ paths: ["../etc/passwd"] }), /outside the posts folder/);
  assert.throws(() => select({ paths: ["/other/place/x.md"] }), /outside the posts folder/);
  assert.throws(() => select({ paths: ["_posts/draft.md"] }), /isn't a post.*no title/);
});

// --- status -------------------------------------------------------------

test("status reports counts, the ledger and a next command, and warns when over budget", () => {
  const config = { budget: 5, estimatedCostPerImage: 0.035 };
  const lines = buildStatus({ posts, hasCard: new Set(["mid"]), hasRaw: new Set(["new"]), spentTotal: 1.5, config });
  const text = lines.join("\n");
  assert.match(text, /Posts: 5 \(1 with a card, 4 without\)/);
  assert.match(text, /Missing a card: 3 \(1 can render.*2 need a paid one\)/);
  assert.match(text, /\$1\.5000 spent of the \$5\.00 budget/);
  assert.match(text, /\/axc-og-cards --backfill$/m);
  const over = buildStatus({ posts, hasCard: new Set(), hasRaw: new Set(), spentTotal: 5.2, config }).join("\n");
  assert.match(over, /WARNING: spending is over the budget/);
  assert.match(over, /raise "budget"/);
});

test("status suggests a --limit that fits when the backfill wouldn't", () => {
  const config = { budget: 5, estimatedCostPerImage: 0.035 };
  const text = buildStatus({ posts, hasCard: new Set(), hasRaw: new Set(), spentTotal: 4.93, config }).join("\n");
  assert.match(text, /--backfill --limit 2 /);
});

test("status with every card present has nothing to do", () => {
  const config = { budget: 5, estimatedCostPerImage: 0.035 };
  const all = new Set(posts.map((p) => p.slug));
  assert.match(buildStatus({ posts, hasCard: all, hasRaw: all, spentTotal: 0, config }).join("\n"), /Nothing to do/);
});
