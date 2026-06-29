# Plan: GEO / answer-engine optimization layer (JSON-LD + answer-first)

## Goal
Make astraedus.dev blog content citable by AI answer engines (ChatGPT, Perplexity,
Google AI Overviews) and richer in Google via structured data. Build ON the existing
blog infra (build-blog-page.py renderer + enhance-blog-seo.js), don't reinvent.

## Decisions
1. **JSON-LD built as a Python object, json.dumps()'d, injected pre-serialized.**
   The current template hand-interpolates a `{...}` block via `.format()` (requires
   `{{`/`}}` doubling, fragile, can't be conditional). Replace with a real dict ->
   `json.dumps(indent=2)` -> single `{jsonld_block}` placeholder. Escaping is
   correct-by-construction. This is the altitude fix.
2. **Use a `@graph` array** holding the Article node + (optionally) a FAQPage node.
   Canonical schema.org pattern for multiple entities on one page.
3. **Article vs TechArticle**: emit `TechArticle` when tags/title signal a developer
   how-to/technical teardown (most of our corpus); else `Article`. Conservative
   heuristic; both are valid Rich Results types.
4. **FAQPage**: only when the article has a Q&A / listicle / "gotcha" shape. Detect
   from the markdown `##` headings: build Q/A pairs from each `##` heading + the
   first sentence(s) of its section. Only emit if >= 2 usable pairs. Headings that
   aren't question-shaped still work as FAQ "questions" (Google accepts declarative
   FAQ questions), but we gate on shape signals to avoid spammy FAQ on prose essays.
5. **publisher = Raedus Labs** (Organization, the real legal entity, D-U-N-S 753163623),
   author = Diven Rastdus (Person). dateModified defaults to datePublished unless a
   real modified date is supplied.

## Files (touch ONLY)
- `scripts/build-blog-page.py` — JSON-LD builder (the work).
- `scripts/test_build_blog_page.py` — tests for the new schema (invariants over the class).
- `~/.claude/skills/article/SKILL.md` — answer-first convention.
- (regenerate pages via backfill + enhancer; these are outputs not "edits")

## Steps
1. [build] Add `_build_jsonld(meta, content_md, canonical, ...)` -> dict, and a
   FAQ extractor `_extract_faq(content_md)`. Replace the template's hand-rolled
   JSON-LD with a single `{jsonld_block}` placeholder fed `json.dumps(graph, indent=2)`.
2. [build] TechArticle/Article heuristic; dateModified; publisher Organization.
3. [test] Add invariants: valid JSON parses, required Article fields, publisher is
   Raedus Labs Org, FAQPage present for listicle/gotcha shapes + absent for prose,
   escaping of quotes/specials in headline/description/FAQ.
4. [regen] Extend backfill to force-rewrite existing pages (or a tiny regen script),
   regenerate all 34, run enhance-blog-seo.js, update-blog-index.py.
5. [verify] Run full test suite. Commit + push. Fetch 3 live pages, assert JSON-LD
   parses + required keys. IndexNow ping the regenerated URLs.

## Risks
- Regenerating pages drops the enhance-blog-seo.js marker -> must re-run enhancer
  (it's idempotent and re-applies on fresh pages). Confirm anchors/TOC/breadcrumb
  reappear.
- backfill only fills GAPS; existing pages won't re-render unless I force it. Need a
  `--force`/regenerate path that re-pulls body from Dev.to (source of truth).
- FAQ answer sentences must be plain text (strip markdown), escaped, length-capped.
