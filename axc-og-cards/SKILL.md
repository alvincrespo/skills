---
name: axc-og-cards
description: Generate a unique 1200×630 Open Graph card for a blog post (or backfill every post missing one). Code renders all the text with the site's own fonts; only the right-hand illustration comes from a paid OpenRouter image model, with spend recorded in a ledger and checked against a budget. Use only when the user explicitly runs /axc-og-cards or directly asks to generate, regenerate or backfill social/OG cards — never inferred from conversation. Every run can spend real money.
argument-hint: "[<post.md>…] | --backfill [--limit N] [--since DATE] [--before DATE] [--spend strict|auto|yolo] [--budget AMOUNT]"
disable-model-invocation: true
---

# axc-og-cards

> **DRAFT: design only (#64).** `scripts/og-cards.mjs` hasn't been
> ported yet. This file describes how the skill will behave, as decided in
> `docs/adr/0003-axc-og-cards-node-and-cost-controls.md`. Don't list the
> skill in the README or `plugin.json` until it's built and verified.

Generate a 1200×630 Open Graph card for each post. The card has:
- the category and date in the top left;
- the title, shrunk to fit at most three lines;
- a byline and site URL in the bottom left;
- a square illustration on the right.

Code renders every piece of text (satori + the site's fonts, rasterized
with resvg/sharp). Only the illustration comes from an image model. So
titles are always spelled correctly, and changing a font or color never
costs money.

Per ADR 0002 and 0003, this skill is `disable-model-invocation: true`:
every run can spend money, so it only runs when a person explicitly asks.

## What the consuming repo owns

The skill owns none of the site's data. The site has:

| File | Purpose |
|---|---|
| `og-cards.config.json` | Paths, brand, fonts, model and pricing, total budget |
| the ledger (e.g. `scripts/og-cards.ledger.json`) | Every paid call: slug, model, cost, timestamp |
| `rawDir` (e.g. `src/images/og/src/`) | Saved illustrations. Commit them so a re-render never pays again; exclude them from the built site |
| `cardsDir` (e.g. `src/images/og/`) | Finished cards, committed and deployed |
| the `og_cards` file (e.g. `src/_data/og_cards.yml`) | The list of which posts have cards, rebuilt from the files on disk on every run |
| font files | Local TTF/OTF/WOFF files the site is licensed to use (**not** WOFF2) |

`OPENROUTER_API_KEY` must be set in the environment. Never print it,
write it anywhere or pass it on the command line.

## First-run setup

Do this when `og-cards.config.json` doesn't exist yet in the current
project.

1. **Install the dependencies** if `${CLAUDE_SKILL_DIR}/node_modules` is
   missing:
   ```bash
   npm install --prefix ${CLAUDE_SKILL_DIR}
   ```
2. **Find the site's settings.** Confirm it's a Bridgetown site
   (`config/initializers.rb`, `bridgetown` in the `Gemfile`). Find the
   posts folder and the categories data file, if there is one. Read the
   site's CSS and head template to find its fonts and colors.
3. **Ask for font files.** Suggest the fonts the site uses, then ask the
   user where the TTF/OTF/WOFF files for each weight the card needs are.
   **Never download fonts or choose a font license for the user.** If the
   site only loads its fonts from a CDN, say that and ask the user to
   supply local files.
4. **Write `og-cards.config.json`**, starting from
   `${CLAUDE_SKILL_DIR}/templates/og-cards.config.json`. Show it to the
   user before saving it.
5. **Wire up the templates** by following `references/bridgetown.md`:
   - the `og:image` fallback chain in the head template;
   - passing `og_cards` to `{% render %}` explicitly;
   - excluding `rawDir` from the build.
6. Run `/axc-og-cards` with no arguments to confirm the setup reads
   cleanly.

## Commands

Translate the user's arguments into a script call. The script always
takes `--config og-cards.config.json` from the project root.

```bash
node ${CLAUDE_SKILL_DIR}/scripts/og-cards.mjs --config og-cards.config.json [targets] [flags]
```

### Targets. A run that spends needs exactly one kind:

| User types | What happens |
|---|---|
| `/axc-og-cards` | **Status only**, costs nothing: posts missing a card, ledger total vs budget, and a suggested next command |
| `/axc-og-cards path/to/post.md [more.md…]` | Cards for these posts |
| `/axc-og-cards --backfill` | Every post missing a card, **newest first** |

The script rejects a post path when:
- it's outside `postsDir`;
- the file has no title in its front matter (a draft).

It skips a post, with a note, when:
- the post already has a card; suggest `--regen`;
- the post sets an `image:` in its front matter; suggest
  `--include-overridden`.

### Modifiers

| Flag | Effect |
|---|---|
| `--regen` | Replace the illustration and card for the named posts |
| `--render-only` | Rebuild cards from the saved illustrations. **Costs nothing**; use after a font, color or byline change |
| `--model <id>` | Use this model for this run |
| `--trial` | Write to a scratch folder instead of `rawDir`/`cardsDir`, to compare models. Spend is still recorded |
| `--include-overridden` | Also generate cards for posts with an `image:` in their front matter |
| `--limit N` | Backfill only: at most N new illustrations |
| `--since DATE` / `--before DATE` | Backfill only: limit by post date (`YYYY-MM-DD`, compared in UTC; `--since` is inclusive, `--before` exclusive) |

### Model precedence
A post's `og_model` front matter wins, then `--model`, then the config's
`model`. Every model used needs a `pricing` entry in the config. The
script refuses a model it has no estimate for rather than guessing.

## Spending: `--spend` and `--budget`

| `--spend` | Asks first | Config `budget` (total) | `--budget` (per run) |
|---|---|---|---|
| `strict` (default) | **Yes** | Enforced | Enforced if passed |
| `auto` | No | Enforced | Enforced if passed |
| `yolo` | No | **Ignored** | Enforced if passed |

- `--budget <amount>` limits this one run. It must be a positive number
  (`2`, `2.50`, no `$`). When both limits apply, the lower one wins.
- The total budget is only ever changed by editing the config. If the
  user wants to spend past it, tell them which setting to change; don't
  offer a flag.
- **Never choose `auto` or `yolo` for the user.** Use them only when the
  user typed them in this request.

### The flow in `strict` (the default)

1. **Dry run:** run the script with the targets and flags but **without**
   `--spend`. It prints the planned cards, how many need a paid
   illustration, the estimated cost, the limit that applies and where it
   comes from (e.g. `Limit: $1.00 (--budget); $3.20 left of $5.00 total`).
   The dry run also makes the checks the real run makes. If something
   would stop it (the ledger is already over budget, `OPENROUTER_API_KEY`
   isn't set, or a font file is missing), it prints what and exits 1. In
   that case **report the problem and stop; don't ask for approval**, since
   the real run would be refused straight away.
2. **Show the plan and ask** (use AskUserQuestion). If the plan exceeds
   the limit, say how many posts will fit before it stops. For a large
   backfill, suggest a `--limit` that fits.
3. **Only after a yes**, rerun the same command with `--spend strict`.

With `auto` or `yolo`, skip steps 1–2: pass the user's `--spend` value
straight through. The script prints the estimate itself before starting.

### What always stops a run, in every mode

These are enforced by the script. Report them to the user; never work
around them.

- **The next call would go over the limit:** the script stops *before*
  that call and lists the posts that didn't get a card.
- **OpenRouter didn't report a `usage.cost`:** the image is saved, and the
  ledger entry is written with `cost: null`. Tell the user to correct that
  entry by hand. Later runs refuse to start until they do.
- **The ledger is over the config budget after a `yolo` run:** `strict`
  and `auto` refuse to spend until `budget` is raised.
- **An API error, a missing font file, or an unknown model.**

On every stop, the script rebuilds the `og_cards` list before exiting. So
cards finished before the stop still appear on the site.

## After generating: check the illustrations for text

Image models often put letters or text in illustrations despite the
style prompt. After a run that generated new illustrations:

1. Read each new file in `rawDir` (just one for a single post; in batches
   of about 10 for a backfill).
2. Flag any with visible letters, words, numbers, logos or faces.
3. List the flagged slugs and offer
   `/axc-og-cards --regen <paths…>`, optionally with a different
   `--model`. That run goes through the same spend flow above.

Don't regenerate without asking, even under `auto` or `yolo`. The user
approved the run they asked for, not follow-up runs.

## Backfilling an existing archive

Backfill is opt-in and resumable:
- a finished card is skipped on the next run;
- a paid illustration is reused, never paid for twice.

So an interrupted or budget-stopped backfill is safe to run again. For a
large archive:

1. Run `/axc-og-cards` for the status report.
2. Run `/axc-og-cards --backfill --limit N`, with N sized to fit the
   budget. Newest posts come first.
3. Check the illustrations for text, then repeat until nothing is left.

## Scope

This skill:
- generates card images;
- rebuilds the `og_cards` list;
- documents the template wiring in `references/bridgetown.md`.

It doesn't:
- deploy anything;
- commit anything;
- change post content;
- support frameworks other than Bridgetown in v1.
