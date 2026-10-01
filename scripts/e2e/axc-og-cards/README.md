# axc-og-cards end-to-end harness

Runs the skill the way a user would, in a throwaway copy of a real site, and
writes a report you can read to decide whether it works. It is not part of the
skill and isn't shipped with it.

By default it clones [alvincrespo/axc-og-fixture](https://github.com/alvincrespo/axc-og-fixture),
a small Bridgetown blog with posts chosen to cover the edge cases (escaped quotes
in a title, a very long title, no category, a `slug:` that differs from the file
name, an `image:` override, a file with no title) and placeholder illustrations, so
the tests don't depend on anyone's personal site.

To test against another site, pass `--repo <url or local path>`, for example a
checkout of your own blog. A site that ships its own `og-cards.config.json` is used
as is (only the budget is overridden); otherwise the harness writes one for a
site whose fonts are in `scripts/fonts/`. The site needs at least four posts
without an `image:` override, and its newest post must already have a card and a
saved illustration.

```bash
# clone the site, print the plan and its cost, run nothing (the clone is deleted)
node scripts/e2e/axc-og-cards/run.mjs

# run the free cases (nothing can spend: they get a dummy API key)
node scripts/e2e/axc-og-cards/run.mjs --run --cases free

# run everything, including the paid cases (about $0.40 of image generation)
OPENROUTER_API_KEY=... node scripts/e2e/axc-og-cards/run.mjs --run
```

Set the key in the environment, never on the command line. Install the skill's
dependencies first: `npm install --prefix axc-og-cards`.

## What one run does

1. **Clones** the site once (`--repo`, default the fixture) into
   `<workdir>/base-site`.
2. For each case, **copies** that clone to `<workdir>/cases/<id>/` so cases
   can't affect each other, and **sets up** the case: picks the posts, cleans the
   skill's assets (cards, saved illustrations, manifest), writes a fresh ledger
   and `og-cards.config.json`, copies the skill to `.claude/skills/axc-og-cards/`,
   makes any deliberate breakage, and snapshots the watched files.
3. **Runs** it with a driver:
   - `agent` (default): a headless `claude -p` session in the case folder that
     runs `/axc-og-cards <args>`. This tests the whole thing: SKILL.md, the
     agent's reading of it, and the script.
   - `script`: calls `og-cards.mjs` directly. Use it to tell a script bug from a
     SKILL.md or agent problem.
4. **Validates** the result (see below) and logs every check.
5. Writes `<workdir>/report/REPORT.md`, `report.json`, `run.log` and per-case
   files.

## Cases

| Case | Paid | What it proves |
|---|---|---|
| `single-post` | yes | One post, no restricted budget: one ledger entry, illustration, 1200x630 card, manifest |
| `single-post-budget-too-low` | | `--budget 0.01`: stops before any paid call |
| `single-post-budget-ok` | yes | `--budget 0.05`: generates, spend stays under it |
| `backfill` | yes | Everything cleaned, then `--backfill` the (trimmed) site, newest first |
| `backfill-budget` | yes | Four posts, `--budget 0.08`: exactly the two newest, then stops |
| `backfill-limit` | yes | Four posts, `--limit 2`: exactly the two newest |
| `strict-asks` | | No `--spend`: shows an estimate and asks, spends nothing, agent adds no `--spend` |
| `status` | | No arguments: read-only report |
| `existing-card-skipped` | | A post with a card is skipped and pointed at `--regen` |
| `regen` | yes | `--regen` pays for a new illustration and replaces the card |
| `render-only` | | Rebuilds a deleted card from the saved illustration for free, identical to the original |
| `over-budget-refused` | | Ledger already over budget: `--spend auto` refuses |
| `yolo-over-budget` | yes | `--spend yolo` proceeds, records the call, warns the total is over |
| `missing-font` | | A missing font file stops the run before any spend |
| `bad-path` | | A path outside the posts folder is refused |
| `no-api-key` | | No key: stops before any write |
| `unknown-flag` | | `--yess` is an error, not a spend |

The backfill cases run on a clone trimmed to the newest 3 or 4 posts (in the
case folder only), so "backfill everything" costs cents. `--site-size N` changes
the size; `--full-site` backfills every eligible post instead. The cost is sized from the
cloned site (its real post count and its own `estimatedCostPerImage`), never from
a default, so even the plan clones first. Cloning is read-only and free. The run
is refused before any case starts if the plan is over `--max-spend`, so raise it if
the site is large. `--list` shows the cases without cloning or costs.

Add a case by adding an object to `cases.mjs`; the fields are documented at the
top of that file.

## What is checked

Each case has its own checks (ledger entries, files present, sizes, messages).
Every case also checks that:

- the ledger is valid, and every entry has a numeric cost (a `null` cost means a
  billed call with an unknown price);
- entries that were seeded weren't altered;
- the manifest lists exactly the cards on disk;
- no card, illustration, post or font changed outside what the case may change;
- (agent driver) the agent finished, ran the skill's script, and only used the
  `--spend` mode the user typed. It must never upgrade to `auto` or `yolo`.
- the OpenRouter key appears in no log or report file.

`WARN` marks things for a human to look at rather than proof of a bug.
**The harness can't judge the illustrations.** Each generated card and
illustration is copied to `report/cases/<id>/artifacts/`; look for stray text,
letters or faces.

## Safety

- Free cases get a dummy key (`no-api-key` gets none), so they can't spend.
- Every case's config has a small total budget (default $0.50), so a bug in the
  skill is bounded.
- The plan is refused if it exceeds `--max-spend` (default $1.00).
- The agent runs with an allow-list of tools (`node`, `npm install`, `ls`, `cat`,
  `grep`, read and search), a spend cap (`--agent-max-usd`), no user settings and
  no MCP servers.
- The website's old `scripts/og-cards.mjs` is removed from the case folders, so a
  run can only use the skill (`--keep-legacy` to keep it).

## Options

Run `node run.mjs --help`. Case folders are kept for review unless `--cleanup`.
