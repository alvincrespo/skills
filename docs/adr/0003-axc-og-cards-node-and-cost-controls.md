# ADR 0003: `axc-og-cards` — a Node skill with script-enforced spend controls

## Status
Accepted. Built across parts A–D of #64; the end-to-end harness in
`scripts/e2e/axc-og-cards/` exercises the behavior described here.

## Context
`alvincrespo/website` generates a unique 1200×630 Open Graph card per blog
post with `scripts/og-cards.mjs` (alvincrespo/website#1472). Code renders
all the text (title, category, date, byline) with satori and the site's
fonts, then rasterizes it with resvg and sharp. Only the right-hand
illustration comes from a paid image model on OpenRouter. Spend is
recorded in a ledger and checked against a hard budget.

The script is useful beyond that one site, but it hardcodes the site's
paths, brand, fonts, model and budget. It also runs everything or nothing:
`yarn og --yes` backfills every post missing a card. Moving it into this
repo raises three questions the four existing skills never did:

1. Every other skill here is Python. satori, the layout engine that makes
   the text rendering work, is JavaScript-only.
2. The skill spends real money on each run, not just creating GitHub
   artifacts.
3. The original bundles the Geist font files. Redistributing fonts from a
   skills repo puts the licensing on us, and ties every user to one look.

## Decision

### Runtime: Node, with dependencies local to the skill
`axc-og-cards` stays in Node. Its `package.json` lives inside
`axc-og-cards/`, not at the repo root, and holds only runtime
dependencies: `satori`, `@resvg/resvg-js`, `sharp` and `yaml`. The SKILL.md
installs them with `npm install --prefix ${CLAUDE_SKILL_DIR}` on first
use. `.claude-plugin/plugin.json` is still the only source of the version:
the skill-local `package.json` is `private` and never versioned or
published.

### Invocation: user-only
`disable-model-invocation: true`, extending ADR 0002's reasoning from
irreversible GitHub artifacts to spending money: a person opts in every
time, never by inference. As `.claude/CLAUDE.md` requires, that also
rules out standalone `.skill` packaging.

### Targets: one post by default, backfill on request
- `/axc-og-cards <post.md…>` — the common case: generate cards for these
  posts.
- `/axc-og-cards --backfill [--limit N] [--since DATE] [--before DATE]` —
  every post missing a card, newest first, so a run stopped by the budget
  has still covered the posts most likely to be shared.
- `/axc-og-cards` with no arguments — a status report. Never spends.

Every run that spends has to name a target. A bare `--spend auto` without
a path or `--backfill` is an error, so running the command with no
target can never trigger a backfill.

### Spend: a mode (`--spend`) and a per-run limit (`--budget`)

| `--spend` | Asks first | Total budget (config) | Per-run `--budget` |
|---|---|---|---|
| `strict` (default) | Yes, after the dry-run estimate | Enforced | Enforced if passed |
| `auto` | No; prints the estimate and starts | Enforced | Enforced if passed |
| `yolo` | No | Ignored | Enforced if passed |

- The config's `budget` limits total spend recorded in the ledger. It
  can only be raised by editing the config.
- `--budget <amount>` limits a single run. When both limits apply, the
  lower one wins. A per-run amount the user types is honored even in
  `yolo`.
- The mode is only ever set per run. The config has no mode setting, so
  `yolo` can never become a repo-wide default.
- After a `yolo` run takes the ledger past the total budget, `strict` and
  `auto` runs refuse to spend until the config's `budget` is raised.

**The script enforces all of this, not the SKILL.md.** Asking for approval
is Claude's part (the SKILL.md runs the dry run, shows it, and waits for a
yes in `strict`). Checking the limits, recording spend in the ledger and
the stop conditions below all live in the script. If Claude misreads the
SKILL.md, the approval step can be lost, but the limits still hold.

**True in every mode, `yolo` included:**
- Every paid call is recorded in the ledger (slug, model, cost,
  timestamp) before anything else happens.
- If OpenRouter doesn't report a `usage.cost`, the run stops, and the
  ledger entry is kept with `cost: null` for the user to fix by hand.
  Without a correct ledger total, no later budget check can be trusted.
- Ambiguous input stops the run rather than being guessed at: a model
  missing from the `pricing` table, a missing font file, a post path
  outside `postsDir`, or a `--budget` that isn't a positive number.
- Every exit path, including stopping at the budget, an API error and a
  missing cost, rebuilds the list of which posts have cards (`og_cards`)
  before exiting. The original script exits without rebuilding it, so
  cards finished before an early stop go unused until the next successful
  run.

### Model: configurable at three levels
A post's `og_model` front matter wins, then `--model`, then the config's
`model`. Each model needs an entry in the config's `pricing` table (the
estimated cost per image, used only for the budget check; the ledger
records the actual `usage.cost`). `modelParams` is merged into the request
body for model-specific options. `--trial` writes to a scratch folder
instead of the real card and illustration folders, so models can be
compared without overwriting anything. Spend is still recorded.
OpenRouter is the only provider, using `OPENROUTER_API_KEY`, which is
never logged.

### Fonts: supplied by the site
The skill ships no font files and downloads none. The config maps each
part of the card (`title`, `meta`, `byline`) to a family and weight, and
lists `sources`, each a local TTF/OTF/WOFF path in the consuming repo.
satori can't read WOFF2. If any font the card needs is missing, the script
stops before making a paid call. The site supplies the font files, so it
also handles their licenses.

### Framework: Bridgetown only for v1
The slug rule (`date-prefixed`, `filename`, `frontmatter`) and the format
of the `og_cards` file (`yaml-map`, `json`) are config settings. But
wiring the cards into the site's templates is documented only for
Bridgetown, in `references/bridgetown.md`. Other frameworks get a
reference doc once someone actually needs one.

## Consequences
- This is the first skill that needs Node. The release workflow and
  `.claude/release.json` `checks` gain a Node setup step and
  `node --test axc-og-cards/scripts/`.
- The plugin's `description` and `keywords` have to broaden beyond
  GitHub-project workflows once the skill is listed.
- The consuming repo owns the config, the ledger, the font files, the
  saved illustrations and the finished cards. The skill owns none of them,
  so uninstalling it leaves every card and every recorded dollar in place.
- `alvincrespo/website` becomes the first consumer. Moving it onto the
  skill is checked for $0: re-render every card from the saved
  illustrations with `--render-only --backfill` and compare against the
  committed PNGs.
