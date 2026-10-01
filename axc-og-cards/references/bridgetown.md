# Wiring the cards into a Bridgetown site

The skill makes the card images and a list of which posts have one. These
steps make the site use them. A working example is
[alvincrespo/axc-og-fixture](https://github.com/alvincrespo/axc-og-fixture):
see its `src/_components/head.liquid`, `src/_layouts/default.liquid` and
`config/initializers.rb`. The examples below assume the default paths
(`cardsDir` `src/images/og`, `rawDir` `src/images/og/src`); change the URLs
if yours differ.

Tested with Bridgetown 2.x and Liquid templates. Other frameworks aren't
covered yet.

## What has to be true

1. Posts live in `src/_posts/`, with `title`, and ideally `category`, `date`
   and `description`, in front matter.
2. A data file lists the posts that have a card (the skill writes it).
3. The head template picks the right image for each page.
4. The layout hands that template everything it needs.
5. The saved illustrations are kept out of the built site.
6. There is a default share image for everything else.

## 1. The `og_cards` data file

The skill rebuilds this file on every run from the card PNGs actually on
disk, so it can't drift. Point `manifest.path` at `src/_data/og_cards.yml`
and keep `"format": "yaml-map"`:

```yaml
getting-started-with-static-site-generators: true
why-i-stopped-using-global-state: true
```

It's a **mapping** (`slug: true`), not a list. Bridgetown 2.x loads each
`_data` file as a resource, and a top-level array falls through a `.rows`
special case that behaves unpredictably with Liquid's `contains` and `for`.
A mapping supports a plain `og_cards[slug]` lookup. (`"format": "json"`
writes the same mapping as JSON.)

## 2. The head template

In `src/_components/head.liquid`, choose the share image in this order:
the post's own `image:` front matter, then its card, then the default.
Only posts get a card; every other page uses the default.

```liquid
{%- assign share_image_path = "/images/og-default.jpg" -%}
{%- if type == "post" -%}
  {%- if image -%}
    {%- assign share_image_path = image -%}
  {%- elsif og_cards[slug] -%}
    {%- assign share_image_path = "/images/og/" | append: slug | append: ".png" -%}
  {%- endif -%}
{%- endif -%}
{%- assign share_image = share_image_path | absolute_url -%}
```

and use it in the tags:

```liquid
<meta property="og:image" content="{{ share_image }}" />
<meta property="og:image:width" content="1200" />
<meta property="og:image:height" content="630" />
<meta name="twitter:card" content="summary_large_image" />
<meta name="twitter:image" content="{{ share_image }}" />
```

`type == "post"` relies on the post layout being named `post`
(`layout: post` in each post). If yours is called something else, change
that comparison.

## 3. Pass the data to the template explicitly

Bridgetown's `{% render %}` only sees the variables you pass it, **not** the
global `site`. So the layout (usually `src/_layouts/default.liquid`) has to
hand over the manifest, the slug and the rest:

```liquid
{% render "head", metadata: site.metadata, title: data.title,
   description: data.description, url: resource.relative_url,
   type: data.layout, date: data.date, slug: resource.slug,
   image: data.image, og_cards: site.data.og_cards %}
```

Without `og_cards: site.data.og_cards`, the lookup in step 2 is always empty
and every post quietly gets the default image.

## 4. Keep the saved illustrations out of the build

The raw illustrations (and any `--trial` output, which lives under them) are
a cache for regeneration, not something to deploy. In
`config/initializers.rb`, relative to `src`:

```ruby
config.exclude = ["images/og/src"]
```

If `rawDir` is somewhere else, exclude that path instead. Commit the
illustrations, so a re-render never pays again; only the finished cards in
`cardsDir` ship.

## 5. A default share image

Add `src/images/og-default.jpg`, 1200×630. It's used for the home page,
other pages, posts without a card and the untitled files the skill skips.

## 6. Slugs must match

The manifest key has to equal the slug Bridgetown computes as
`resource.slug`: the date prefix of `YYYY-MM-DD-title.md` is dropped, and a
front-matter `slug:` wins over the file name. That is
`"slugStrategy": "date-prefixed"`, the default. Use `"filename"` or
`"frontmatter"` only if your site names posts differently.

## Check it

Build and look at the tags:

```bash
bin/bridgetown build
for f in $(find output -name index.html); do printf '%s  ' "$f"; grep -o 'og:image" content="[^"]*"' "$f"; done
ls output/images/og            # the cards, and no src/ folder
```

You should see a post with a card pointing at `/images/og/<slug>.png`, a post
with its own `image:` keeping that image, and the home page using
`og-default.jpg`.

## Other things worth knowing

- **Fonts:** satori reads TTF, OTF and WOFF but **not WOFF2**, which is what
  Google Fonts serves by default. Supply local files you're licensed to use;
  the skill doesn't ship or download any.
- **Imported posts:** the front-matter reader is deliberately tolerant. A
  `description:` that spans lines in a way strict YAML rejects (common in
  posts exported from Hashnode) still works. An imported `coverImage` is
  ignored; set `image:` yourself if you want it used.
- **Titles:** the card's title shrinks to fit about three lines, but a very
  long one can wrap to four. The card uses the post's own `title`, so shorten
  that if it matters.
