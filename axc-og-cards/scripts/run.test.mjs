import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, writeFile, mkdir, readFile, readdir } from "node:fs/promises";
import { existsSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { run } from "./lib/run.mjs";

// These drive run() with a fake fetch and dummy font files, so no test touches
// the network or spends anything. The dummy fonts are enough to reach every
// stop condition; a run that gets as far as rendering a card fails at that
// step, and the tests that go that far only check what happened before it
// (the call was made, the ledger recorded it, the manifest was rebuilt).

const here = path.dirname(fileURLToPath(import.meta.url));
const template = JSON.parse(await readFile(path.join(here, "../templates/og-cards.config.json"), "utf8"));

async function makeProject({ ledger = [], budget = 5, posts = ["alpha"], cards = [], frontMatter = {}, pricing = null, modelParams = null } = {}) {
  const dir = await mkdtemp(path.join(tmpdir(), "og-run-"));
  await mkdir(path.join(dir, "posts"));
  await mkdir(path.join(dir, "fonts"));
  await mkdir(path.join(dir, "cards"));
  for (const slug of posts) {
    await writeFile(path.join(dir, "posts", `${slug}.md`), `---\ntitle: ${slug}\ndate: 2024-05-01T10:00:00Z\n${frontMatter[slug] ?? ""}\n---\nBody`);
  }
  for (const slug of cards) await writeFile(path.join(dir, "cards", `${slug}.png`), "card");
  for (const src of template.fonts.sources) await writeFile(path.join(dir, "fonts", path.basename(src.path)), "not a real font");
  await writeFile(path.join(dir, "ledger.json"), JSON.stringify(ledger));
  const config = {
    ...template,
    postsDir: "posts",
    categoriesFile: null,
    cardsDir: "cards",
    rawDir: "raw",
    ledger: "ledger.json",
    budget,
    ...(pricing ? { pricing } : {}),
    ...(modelParams ? { modelParams } : {}),
    manifest: { path: "og_cards.yml", format: "yaml-map" },
    fonts: { ...template.fonts, sources: template.fonts.sources.map((s) => ({ ...s, path: `fonts/${path.basename(s.path)}` })) },
  };
  await writeFile(path.join(dir, "og-cards.config.json"), JSON.stringify(config));
  return dir;
}

const image = (usage) => ({ ok: true, json: async () => ({ data: [{ b64_json: Buffer.from("png").toString("base64") }], ...(usage ? { usage } : {}) }) });

function harness(dir, response = image({ cost: 0.03 }), env = { OPENROUTER_API_KEY: "test-key" }) {
  const calls = [];
  const out = [];
  const err = [];
  const ctx = {
    cwd: dir,
    env,
    out: (l) => out.push(l),
    errOut: (...l) => err.push(l.join(" ")),
    fetchImpl: async (...a) => {
      calls.push(a);
      return typeof response === "function" ? response() : response;
    },
  };
  return { calls, ctx, text: () => out.join("\n"), errText: () => err.join("\n") };
}

const ledgerOf = async (dir) => JSON.parse(await readFile(path.join(dir, "ledger.json"), "utf8"));
const manifestOf = async (dir) => readFile(path.join(dir, "og_cards.yml"), "utf8");

test("no target reports status and writes nothing", async () => {
  const dir = await makeProject();
  const h = harness(dir);
  assert.equal(await run([], h.ctx), 0);
  assert.match(h.text(), /Posts: 1 \(0 with a card, 1 without\)/);
  assert.equal(h.calls.length, 0);
  assert.equal(existsSync(path.join(dir, "raw")), false);
  assert.equal(existsSync(path.join(dir, "og_cards.yml")), false);
});

test("without --spend a run is a dry run: no calls, no ledger change, no folders", async () => {
  const dir = await makeProject();
  const h = harness(dir);
  assert.equal(await run(["posts/alpha.md"], h.ctx), 0);
  assert.match(h.text(), /Planned cards: 1 \(1 need a paid illustration\)/);
  assert.match(h.text(), /Limit: \$5\.00 left of the \$5\.00 total/);
  assert.match(h.text(), /Dry run only/);
  assert.equal(h.calls.length, 0);
  assert.deepEqual(await ledgerOf(dir), []);
  assert.equal(existsSync(path.join(dir, "raw")), false);
});

test("the dry run says how many calls fit before the run would stop", async () => {
  const dir = await makeProject({ ledger: [{ slug: "x", cost: 4.93, timestamp: "t" }], posts: ["a", "b", "c"] });
  const h = harness(dir);
  await run(["--backfill"], h.ctx);
  assert.match(h.text(), /Only 2 of 3 paid illustrations fit/);
});

test("stops before the call that would pass the total budget, and rebuilds the manifest", async () => {
  const dir = await makeProject({ ledger: [{ slug: "x", cost: 4.99, timestamp: "t" }], posts: ["alpha", "beta"], cards: ["beta"] });
  const h = harness(dir);
  assert.equal(await run(["posts/alpha.md", "--spend", "auto"], h.ctx), 1);
  assert.match(h.errText(), /exceeding the \$5\.00 budget/);
  assert.match(h.errText(), /Posts not yet generated: alpha/);
  assert.equal(h.calls.length, 0);
  assert.equal(await manifestOf(dir), "beta: true\n");
});

test("--budget stops the run at its own limit, in every mode including yolo", async () => {
  for (const mode of ["strict", "auto", "yolo"]) {
    const dir = await makeProject();
    const h = harness(dir);
    assert.equal(await run(["posts/alpha.md", "--spend", mode, "--budget", "0.02"], h.ctx), 1, mode);
    assert.match(h.errText(), /--budget for this run/, mode);
    assert.equal(h.calls.length, 0, mode);
  }
});

test("strict and auto refuse to start when the ledger is already over budget", async () => {
  for (const mode of ["strict", "auto"]) {
    const dir = await makeProject({ ledger: [{ slug: "x", cost: 5.5, timestamp: "t" }] });
    const h = harness(dir);
    assert.equal(await run(["posts/alpha.md", "--spend", mode], h.ctx), 1, mode);
    assert.match(h.errText(), /over the \$5\.00 budget.*Raise "budget"/s, mode);
    assert.equal(h.calls.length, 0, mode);
  }
});

test("yolo ignores the total budget and still records the call", async () => {
  const dir = await makeProject({ ledger: [{ slug: "x", cost: 5.5, timestamp: "t" }] });
  const h = harness(dir);
  await run(["posts/alpha.md", "--spend", "yolo"], h.ctx);
  assert.equal(h.calls.length, 1);
  const ledger = await ledgerOf(dir);
  assert.equal(ledger.length, 2);
  assert.deepEqual([ledger[1].slug, ledger[1].cost, ledger[1].model], ["alpha", 0.03, template.model]);
});

test("every paid call is recorded before anything else can fail, and the manifest is rebuilt", async () => {
  const dir = await makeProject({ posts: ["alpha", "beta"], cards: ["beta"] });
  const h = harness(dir);
  // The dummy font makes rendering fail after the call, which is the point.
  assert.equal(await run(["posts/alpha.md", "--spend", "auto"], h.ctx), 1);
  assert.equal(h.calls.length, 1);
  assert.equal((await ledgerOf(dir))[0].cost, 0.03);
  assert.equal(existsSync(path.join(dir, "raw", "alpha.png")), true);
  assert.equal(await manifestOf(dir), "beta: true\n");
});

test("the spend is recorded even if saving the image fails afterwards", async () => {
  const dir = await makeProject();
  await mkdir(path.join(dir, "raw", "alpha.png"), { recursive: true }); // a folder where the file goes, so the write fails
  const h = harness(dir);
  // --regen makes the call even though something already sits at that path.
  assert.equal(await run(["posts/alpha.md", "--regen", "--spend", "auto"], h.ctx), 1);
  assert.equal(h.calls.length, 1);
  assert.deepEqual((await ledgerOf(dir)).map((e) => [e.slug, e.cost]), [["alpha", 0.03]]);
});

test("a missing usage.cost stops the run, keeps the image and records cost: null", async () => {
  const dir = await makeProject({ posts: ["alpha", "beta"] });
  const h = harness(dir, image(null));
  assert.equal(await run(["--backfill", "--spend", "yolo"], h.ctx), 1);
  assert.equal(h.calls.length, 1); // it did not carry on to the next post
  assert.match(h.errText(), /didn't report a numeric usage\.cost/);
  assert.deepEqual((await ledgerOf(dir)).map((e) => e.cost), [null]);
  assert.equal((await readdir(path.join(dir, "raw"))).length, 1);
  assert.equal(existsSync(path.join(dir, "og_cards.yml")), true);
});

test("a ledger entry with no cost blocks later runs entirely", async () => {
  const dir = await makeProject({ ledger: [{ slug: "x", cost: null, timestamp: "t" }] });
  const h = harness(dir);
  assert.equal(await run(["posts/alpha.md", "--spend", "yolo"], h.ctx), 1);
  assert.match(h.errText(), /no numeric cost/);
  assert.equal(h.calls.length, 0);
});

test("an API error stops the run without a ledger entry and rebuilds the manifest", async () => {
  const dir = await makeProject({ cards: ["alpha"], posts: ["alpha", "beta"] });
  const h = harness(dir, { ok: false, status: 500, text: async () => "boom" });
  assert.equal(await run(["posts/beta.md", "--spend", "auto"], h.ctx), 1);
  assert.match(h.errText(), /500 boom/);
  assert.deepEqual(await ledgerOf(dir), []);
  assert.equal(await manifestOf(dir), "alpha: true\n");
});

test("a missing API key stops before any write", async () => {
  const dir = await makeProject();
  const h = harness(dir, image({ cost: 0.03 }), {});
  assert.equal(await run(["posts/alpha.md", "--spend", "auto"], h.ctx), 1);
  assert.match(h.errText(), /OPENROUTER_API_KEY is not set/);
  assert.equal(existsSync(path.join(dir, "raw")), false);
});

test("a missing font file stops before any paid call", async () => {
  const dir = await makeProject();
  await writeFile(path.join(dir, "fonts", "Geist-Bold.ttf"), "x");
  const cfg = JSON.parse(await readFile(path.join(dir, "og-cards.config.json"), "utf8"));
  cfg.fonts.sources[0].path = "fonts/gone.ttf";
  await writeFile(path.join(dir, "og-cards.config.json"), JSON.stringify(cfg));
  const h = harness(dir);
  assert.equal(await run(["posts/alpha.md", "--spend", "auto"], h.ctx), 1);
  assert.match(h.errText(), /Font file not found: fonts\/gone\.ttf/);
  assert.equal(h.calls.length, 0);
  assert.deepEqual(await ledgerOf(dir), []);
});

test("bad arguments and bad paths are reported and never spend", async () => {
  const dir = await makeProject();
  const h = harness(dir);
  assert.equal(await run(["posts/alpha.md", "--yess"], h.ctx), 1);
  assert.match(h.errText(), /Unknown flag --yess/);
  assert.equal(await run(["../elsewhere.md", "--spend", "auto"], h.ctx), 1);
  assert.match(h.errText(), /outside the posts folder/);
  assert.equal(h.calls.length, 0);
});

test("a named post that already has a card is skipped and nothing is spent", async () => {
  const dir = await makeProject({ cards: ["alpha"] });
  const h = harness(dir);
  assert.equal(await run(["posts/alpha.md", "--spend", "auto"], h.ctx), 0);
  assert.match(h.text(), /already has a card \(use --regen/);
  assert.equal(h.calls.length, 0);
});

test("a dry run reports what would make the real run refuse, and exits 1", async () => {
  const noKey = harness(await makeProject(), image({ cost: 0.03 }), {});
  assert.equal(await run(["posts/alpha.md"], noKey.ctx), 1);
  assert.match(noKey.errText(), /OPENROUTER_API_KEY is not set/);
  assert.match(noKey.errText(), /nothing to approve yet/);
  assert.doesNotMatch(noKey.text(), /Dry run only/);

  const over = await makeProject({ ledger: [{ slug: "x", cost: 5.5, timestamp: "t" }] });
  const overH = harness(over);
  assert.equal(await run(["posts/alpha.md"], overH.ctx), 1);
  assert.match(overH.errText(), /over the \$5\.00 budget.*Raise "budget"/s);

  const noFont = await makeProject();
  await writeFile(path.join(noFont, "og-cards.config.json"), JSON.stringify({
    ...JSON.parse(await readFile(path.join(noFont, "og-cards.config.json"), "utf8")),
    fonts: { ...template.fonts, sources: [{ family: "Geist", weight: 700, path: "fonts/gone.ttf" }, ...template.fonts.sources.slice(1).map((s) => ({ ...s, path: `fonts/${path.basename(s.path)}` }))] },
  }));
  const fontH = harness(noFont);
  assert.equal(await run(["posts/alpha.md"], fontH.ctx), 1);
  assert.match(fontH.errText(), /Font file not found: fonts\/gone\.ttf/);
  for (const h of [noKey, overH, fontH]) assert.equal(h.calls.length, 0);
});

test("a dry run that would go ahead still exits 0, and needs no key when nothing is paid for", async () => {
  const ok = harness(await makeProject());
  assert.equal(await run(["posts/alpha.md"], ok.ctx), 0);
  assert.match(ok.text(), /Dry run only/);
  const free = harness(await makeProject({ cards: ["alpha"] }), image({ cost: 0.03 }), {});
  assert.equal(await run(["posts/alpha.md"], free.ctx), 0); // already has a card: nothing to pay for
});

// --- models, pricing, params and trials ----------------------------------------

const PRICES = { [template.model]: 0.035, "vendor/cheap": 0.014, "vendor/pricey": 0.06 };
const bodyOf = (h, i = 0) => JSON.parse(h.calls[i][1].body);

test("a model with no price is refused, in a dry run and a real run, before any call", async () => {
  for (const args of [["posts/alpha.md", "--model", "vendor/unpriced"], ["posts/alpha.md", "--model", "vendor/unpriced", "--spend", "auto"]]) {
    const h = harness(await makeProject());
    assert.equal(await run(args, h.ctx), 1, args.join(" "));
    assert.match(h.errText(), /Model "vendor\/unpriced" has no entry in "pricing"/);
    assert.equal(h.calls.length, 0);
  }
});

test("a post's og_model is used (and priced) ahead of --model and the config's model", async () => {
  const dir = await makeProject({ pricing: PRICES, frontMatter: { alpha: "og_model: vendor/pricey" } });
  const h = harness(dir);
  await run(["posts/alpha.md", "--model", "vendor/cheap", "--spend", "auto"], h.ctx);
  assert.equal(bodyOf(h).model, "vendor/pricey");
  const [entry] = await ledgerOf(dir);
  assert.deepEqual([entry.slug, entry.model], ["alpha", "vendor/pricey"]);
});

test("--model beats the config's model, and is recorded in the ledger", async () => {
  const dir = await makeProject({ pricing: PRICES });
  const h = harness(dir);
  await run(["posts/alpha.md", "--model", "vendor/cheap", "--spend", "auto"], h.ctx);
  assert.equal(bodyOf(h).model, "vendor/cheap");
  assert.equal((await ledgerOf(dir))[0].model, "vendor/cheap");
});

test("the dry run counts what fits using each post's own model price", async () => {
  // alpha uses the $0.035 model and beta the $0.06 one: with a $0.07 run budget
  // only alpha fits ($0.095 together)
  const dir = await makeProject({ pricing: PRICES, posts: ["alpha", "beta"], frontMatter: { beta: "og_model: vendor/pricey" } });
  const h = harness(dir);
  assert.equal(await run(["posts/alpha.md", "posts/beta.md", "--budget", "0.07"], h.ctx), 0);
  assert.match(h.text(), /Only 1 of 2 paid illustrations fit under that limit/);
  assert.match(h.text(), /Estimated cost of this run: \$0\.0950/);
});

test("the dry run lists each model and its estimate", async () => {
  const dir = await makeProject({ pricing: PRICES, posts: ["alpha", "beta"], frontMatter: { beta: "og_model: vendor/cheap" } });
  const h = harness(dir);
  assert.equal(await run(["posts/alpha.md", "posts/beta.md"], h.ctx), 0);
  assert.match(h.text(), /Models: .*flux\.2-pro x1 \(~\$0\.035.*vendor\/cheap x1 \(~\$0\.014/);
  assert.match(h.text(), /Estimated cost of this run: \$0\.0490/);
});

test("modelParams for the model are merged into the request, but can't replace the model or prompt", async () => {
  const dir = await makeProject({ modelParams: { [template.model]: { seed: 7, output_format: "jpeg", model: "evil/model", prompt: "evil" }, "other/model": { seed: 1 } } });
  const h = harness(dir);
  await run(["posts/alpha.md", "--spend", "auto"], h.ctx);
  const body = bodyOf(h);
  assert.equal(body.seed, 7);
  assert.equal(body.output_format, "jpeg"); // overrides the default
  assert.equal(body.aspect_ratio, "1:1"); // default kept
  assert.equal(body.model, template.model);
  assert.match(body.prompt, /^alpha/);
});

test("a trial records the spend but writes only under the trial folder", async () => {
  const dir = await makeProject({ cards: ["alpha"] });
  await mkdir(path.join(dir, "raw"), { recursive: true });
  await writeFile(path.join(dir, "raw", "alpha.png"), "the real illustration");
  const h = harness(dir);
  // the dummy font makes the card render fail after the call, which is fine here
  assert.equal(await run(["posts/alpha.md", "--trial", "--spend", "auto"], h.ctx), 1);
  assert.equal(h.calls.length, 1);
  const [entry] = await ledgerOf(dir);
  assert.deepEqual([entry.slug, entry.model, entry.cost], ["alpha", template.model, 0.03]);
  const trialFolder = path.join(dir, "raw", "trial", template.model.replace(/[^A-Za-z0-9._-]+/g, "_"));
  assert.equal(existsSync(path.join(trialFolder, "alpha.illustration.png")), true);
  assert.equal(await readFile(path.join(dir, "raw", "alpha.png"), "utf8"), "the real illustration");
  assert.equal(await readFile(path.join(dir, "cards", "alpha.png"), "utf8"), "card");
  assert.equal(existsSync(path.join(dir, "og_cards.yml")), false);
});

test("a trial still respects the budget and records nothing it didn't spend", async () => {
  const dir = await makeProject({ cards: ["alpha"] });
  const h = harness(dir);
  assert.equal(await run(["posts/alpha.md", "--trial", "--spend", "auto", "--budget", "0.01"], h.ctx), 1);
  assert.equal(h.calls.length, 0);
  assert.deepEqual(await ledgerOf(dir), []);
});
