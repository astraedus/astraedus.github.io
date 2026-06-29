# astraedus.github.io

Personal portfolio + technical blog at [astraedus.dev](https://astraedus.dev). Pure static HTML/CSS/JS, no build step, deployed via GitHub Pages.

This is the public surface for Diven Rastdus / Astraedus — projects grid, blog posts, links out to socials and the in-progress book. Written for humans (recruiters, peers, prospective clients) — content choices skew toward "I ship production AI systems" and longform technical writing.

## Stack
- Plain HTML + CSS + vanilla JS. No framework, no build, no bundler.
- Custom design system (DM Sans + Instrument Serif + JetBrains Mono, dark theme, amber accent `#f59e0b`).
- GitHub Pages deploy on push to `main` (origin is GitHub Pages/Fastly, proxied through **Cloudflare** — `server: cloudflare`, `cf-ray`).

## Analytics (verified from source 2026-06-28)
**Only ONE analytics tool is actually installed: Cloudflare Web Analytics** (privacy-friendly RUM beacon), site token `8b578cad5b3646a7b9c81ac6acbb76ab` (`static.cloudflareinsights.com/beacon.min.js` on every page).
- **No Google Analytics. No PostHog.** (Repo greps hit "PostHog" 40+ times, but those are all *blog content* — there's a tutorial post about PostHog at `blog/posthog-funnel-events/` whose `posthog.init(...)` is an **example snippet in the article**, not a site tag. Don't be fooled.)
- PostHog project 379606 is the **Origo mobile app**, unrelated to this site — it has zero web pageviews.
- **Reading the numbers:** Cloudflare Web Analytics data is in the CF dashboard (Web Analytics) or via the GraphQL Analytics API (`rumPageloadEventsAdaptiveGroups`, filter by the site token above). The `cf` CLI exposes zone `cf analytics dashboard get <zoneId>` (HTTP-level, needs a **valid** API token — the one in `~/.cf/config.toml` was `tokenValid:false` as of 2026-06-28, rotate via Bitwarden/CF dashboard). Cloudflare account in Bitwarden.

## IndexNow (instant search-engine submission, added 2026-06-29)
We push published URLs to IndexNow (Bing/Yandex/Seznam/etc.) the moment we publish, instead of waiting for a crawl. We own the site, so this is fully autonomous.
- **Key:** `49b5a0c1037670a608fc0a637b1e8a56` (not a secret — it's a public ownership token, hosted in the open).
- **Key file:** `49b5a0c1037670a608fc0a637b1e8a56.txt` at the site root (committed here) → served at `https://astraedus.dev/49b5a0c1037670a608fc0a637b1e8a56.txt`. The file content is the bare key, **no trailing newline** (IndexNow requires byte-exact match). Do NOT delete or edit this file — IndexNow re-validates ownership by fetching it on every submission.
- **Submit URLs:** `~/bin/astra-indexnow.sh <url> [more urls...]` (POSTs to `https://api.indexnow.org/indexnow`; 200/202 = success). It refuses any URL not on `https://astraedus.dev/`. Wired into the `/article` pipeline STEP 6 (every published canonical astraedus.dev URL gets pinged automatically).
- **Rotating the key:** change `KEY` in `astra-indexnow.sh`, rename the `.txt` file to match, commit + push, wait for Pages to deploy, then it re-validates.

## Newsletter signup (`#subscribe`, added 2026-06-29)
The homepage has a `#subscribe` section (between the writing section and the final CTA) — an email input that POSTs `{ email }` to **`https://astraedus.dev/api/subscribe`**, a Cloudflare Worker bound as a same-origin route on this zone. The Worker (repo `~/projects/astraedus-newsletter-worker`) validates server-side and adds the contact to the Resend audience **"Astraedus Newsletter"** (`a32d3681-a39f-42c6-a41e-7bee67402639`). The Resend API key lives ONLY as a Worker secret — never in this static site. Dev.to articles CTA to `astraedus.dev/#subscribe` to compound the audience. To change signup logic, edit/redeploy the Worker repo, not this site. Footer carries the contact email `theagentthatcould@gmail.com`.

## Key Files
- `index.html` — homepage (hero, projects grid, articles, contact).
- `CNAME` — `astraedus.dev` (custom domain).
- `blog/` — one directory per post, each containing `index.html`. Index page at `blog/index.html`.
- `book/` — work-in-progress book (`cover.jpg` + `index.html`).
- `arc-journal/privacy.html` — Arc Journal privacy policy (legally required, not really part of the portfolio narrative).
- `sitemap.xml`, `robots.txt`, `favicon.svg` — standard SEO surface.

## Architecture
Flat static. Every page is a self-contained HTML file with inline CSS variables and JS. Shared design tokens are duplicated across files — change the palette, propagate manually. Links between pages are relative.

## Commands
```bash
# local preview (no build)
python3 -m http.server 8000

# deploy
git push origin main          # GitHub Pages auto-deploys

# check live
curl -I https://astraedus.dev/
```

## Editorial Conventions
- Blog post slug = directory name. Post lives at `blog/<slug>/index.html`.
- New post checklist: add card to `index.html` articles section, add entry to `blog/index.html`, add to `sitemap.xml`, add canonical `<link>` to the post.
- **SEO surfacing (2026-06-09)**: every post has slugified `id` anchors on h2/h3 (`<a class="anchor">` + CSS `::before` "#"), an "On this page" `.post-toc` card, a visible `.crumbs` breadcrumb, and a SECOND additive `BreadcrumbList` JSON-LD block (existing Article block untouched). These power Google jump-to-section sitelinks + breadcrumb trails. After adding a NEW post, run `node scripts/enhance-blog-seo.js` — it's idempotent (skips files carrying the `<!-- seo-enhanced -->` marker), so it only touches the new one.
- Voice: terse, technical, anti-AI-tells. Match the existing posts (e.g. `postgres-rls-or-leak`, `voice-transcription-supabase-gemini-flash`).

## Decisions
Logged in `~/ops/DECISIONS.md` tagged `[astraedus.github.io]` or `[portfolio]`. Major narrative pivots (e.g. promoting Astraedus to centerpiece, then later removing the dedicated deep-dive page) are in git log.

## Lessons
Project-specific lessons inline at the bottom of this file. System-wide: `~/ops/LESSONS.md`. Of note: HN shadow-reject incidents (see `~/ops/LESSONS.md` 2026-04-24 + 2026-05-01) — submitting from `diven_rastdus` account is account-level shadow-banned; new posts cross-posted from this domain need a different submission path.

## Agents & Skills
- `marketing-agent` — voice rules + anti-AI-tells when drafting posts.
- `frontend-qa-agent` — quick visual check after design changes.
- `medium-post` skill — for cross-posting blog content to Medium.

## Secrets
None inline. No build-time env. Cloudflare account in Bitwarden if analytics token ever needs rotation.

---

## Project Lessons

### 2026-06-29: Checking astraedus.dev URLs from a script needs a browser UA
The site is behind Cloudflare, which **403s the default Python `urllib`/`requests` User-Agent**. Any script that probes a live astraedus.dev URL (e.g. the IndexNow "is this page live?" guard in `cross-post.py`) must send a browser-like `User-Agent` header. `curl`'s default UA passes fine, so shell `curl` checks don't need this — only Python clients do.

### 2026-06-29: GSC is already verified + sitemap submitted
astraedus.dev is a **verified Domain property** in Google Search Console (account theagentthatcould@gmail.com) via the DNS TXT `google-site-verification=7batHgI3rJ14n3nM9oFxxlqzhK-WxVHzkOW6BK06kXw` (in the Cloudflare zone). The sitemap `https://astraedus.dev/sitemap.xml` is submitted (Status: Success, 20 pages). As of 6/12/26: 17 pages Indexed, 25 Not indexed. To re-read the TXT token, `dig TXT astraedus.dev +short` (GSC UI hides it once verified). For a domain property, the sitemap field needs the FULL URL, not the bare path.

<!-- Add ## YYYY-MM-DD: Title entries here as lessons accrue. -->

<!-- Auto-generated stub via /project-md bootstrap on 2026-05-05. Sharpen as you learn what's tricky here. -->
