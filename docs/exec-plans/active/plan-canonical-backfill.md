# Plan: Backfill dead Dev.to canonicals on astraedus.dev

## Problem (verified 2026-06-29 against live URLs + Dev.to API)
Dev.to articles set `canonical_url` to `https://astraedus.dev/blog/<slug>`. Source-of-truth
audit (Dev.to API `/articles/me/published` + local `/blog` dirs):
- 77 articles published on Dev.to.
- 23 declare a canonical at `astraedus.dev/blog/<slug>`.
- **Only 3 of those slugs have a matching `/blog/<slug>` dir → 20 canonicals 404.**
- Confirmed live: `curl https://astraedus.dev/blog/cron-jobs-firing-wrong-timezone-cron-tz` → 404.

Root cause: pages were either never created, or created under a SHORTER hand-slug
(e.g. dir `agent-eval-lying` while the Dev.to canonical declares the long
`your-ai-agent-evaluation-is-lying-...`). Google follows the declared canonical → dead page →
no canonical authority consolidates on our domain.

Secondary issue (noted, not in scope to rewrite): the 3 dirs that DO resolve canonical *back to
Dev.to* in their `<link rel=canonical>`. New backfilled pages will be **self-canonical** (correct).

## Fix
1. Generate the 20 missing `/blog/<canonical-slug>/index.html` pages from each article's
   Dev.to `body_markdown`, reusing the exact existing template (`agent-eval-lying` is the model):
   same head/nav/footer, CSS vars, JSON-LD Article block, but **self-canonical** to
   `https://astraedus.dev/blog/<slug>/`.
2. Run `scripts/enhance-blog-seo.js` (idempotent) to add the anchor/TOC/crumb SEO layer
   uniformly — same as the documented "new post" workflow.
3. Add each new page to `blog/index.html` listing + `sitemap.xml`.
4. Forward-wire: extend `~/bin/cross-post.py` so publishing to Dev.to with an
   `astraedus.dev/blog/<slug>` canonical auto-generates the page first (fail loud if the
   canonical would be dead). Document in `~/.claude/skills/article/SKILL.md`.
5. Verify: re-curl the previously-404 slugs → expect 200. Regenerate sitemap, ping IndexNow.

## Tooling
- `scripts/build-blog-page.py` — markdown→page generator (new, committed to repo so the
  forward-wire and future re-runs use the same renderer).
- Python `markdown` 3.5.2 (`fenced_code`, `tables`, `sane_lists`, `attr_list`).

## Out of scope (file domain)
Do NOT touch substack scripts/skill. Only: `~/projects/astraedus.github.io/`,
`~/.claude/skills/article/SKILL.md`, `~/bin/cross-post.py`.
