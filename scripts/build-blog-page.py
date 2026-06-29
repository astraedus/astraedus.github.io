#!/usr/bin/env python3
"""
build-blog-page.py -- Render a self-canonical astraedus.dev/blog/<slug>/index.html
from article markdown, matching the site's existing blog template.

This is the SINGLE renderer used by both:
  - the canonical backfill (scripts/backfill-canonicals.py)
  - the forward-wire at publish time (~/bin/cross-post.py)

so a page generated today is byte-identical in structure to one generated at
publish time, and scripts/enhance-blog-seo.js can layer anchors/TOC/crumbs on
either uniformly.

The generated page is the CANONICAL home of the content:
  <link rel="canonical" href="https://astraedus.dev/blog/<slug>/">

Usage (library):
    from build_blog_page import render_page, write_page
    html = render_page(meta, body_markdown)

Usage (CLI, single page from a JSON descriptor):
    python3 build-blog-page.py --json article.json --out /path/blog/<slug>/index.html

`meta` keys: title, slug, description, tags (list), published_at (ISO),
reading_time_minutes (int|None), lede (str|None -> derived from first paragraph).
"""
import argparse
import html as _html
import json
import re
import sys
from datetime import datetime
from pathlib import Path

try:
    import markdown as _md
except ImportError:  # pragma: no cover
    sys.stderr.write("ERROR: python 'markdown' package required (pip install markdown)\n")
    raise

SITE = "https://astraedus.dev"
AUTHOR = "Diven Rastdus"

# ---------------------------------------------------------------------------
# Markdown -> body HTML
# ---------------------------------------------------------------------------

def _strip_frontmatter(text: str) -> str:
    """Drop a leading --- ... --- YAML block if present (Dev.to bodies usually omit it)."""
    s = text.lstrip()
    if s.startswith("---"):
        end = s.find("\n---", 3)
        if end != -1:
            nl = s.find("\n", end + 4)
            return s[nl + 1:] if nl != -1 else ""
    return text


def _split_lede(md_body: str):
    """Return (lede_text, remaining_markdown).

    The site template renders the first paragraph as the .article-lede and the
    rest as .article-body. If a description is supplied we prefer it for the
    lede, but we still drop the first body paragraph only when it *is* that
    intro paragraph. Conservative: we only pull the lede out of the body when no
    explicit lede is given (handled by caller); here we just expose the first
    paragraph so the caller can decide.
    """
    md_body = md_body.strip()
    # First block separated by a blank line, that is plain prose (not a heading,
    # list, code fence, table, or quote).
    parts = re.split(r"\n\s*\n", md_body, maxsplit=1)
    first = parts[0].strip()
    rest = parts[1] if len(parts) > 1 else ""
    if first and not re.match(r"^(#|```|\||>|[-*+]\s|\d+\.\s)", first):
        return first, rest
    return "", md_body


def _md_to_html(md_text: str) -> str:
    md = _md.Markdown(
        extensions=["fenced_code", "tables", "sane_lists", "attr_list", "nl2br"],
        output_format="html5",
    )
    out = md.convert(md_text)
    # nl2br turns single newlines into <br>; we only want it inside paragraphs,
    # not splattered everywhere. markdown's nl2br is paragraph-scoped already, so
    # this is fine. Clean up <br> immediately before closing block tags.
    out = re.sub(r"<br\s*/?>\s*</(p|li|h[1-6])>", r"</\1>", out)
    return out


def _inline_md(text: str) -> str:
    """Render a short inline string (lede / description) -- strip wrapping <p>."""
    h = _md_to_html(text).strip()
    h = re.sub(r"^<p>(.*)</p>$", r"\1", h, flags=re.DOTALL)
    return h


def _harden_images(body_html: str) -> str:
    """Make any <img> responsive (template has no img rule)."""
    return re.sub(
        r"<img ",
        '<img loading="lazy" style="max-width:100%;height:auto;border-radius:10px;border:1px solid var(--border);margin:8px 0;" ',
        body_html,
    )


# ---------------------------------------------------------------------------
# Page assembly
# ---------------------------------------------------------------------------

def _fmt_date_human(iso: str) -> str:
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%b %-d, %Y")
    except Exception:
        return iso[:10]


def _fmt_date_iso(iso: str) -> str:
    if not iso:
        return ""
    return iso[:10]


def _normalize_tags(tags) -> list:
    """Dev.to returns tag_list as a LIST from /articles/me/published but as a
    comma-separated STRING from /articles/{id}. Accept either."""
    if not tags:
        return []
    if isinstance(tags, str):
        return [t.strip() for t in tags.split(",") if t.strip()]
    return [str(t).strip() for t in tags if str(t).strip()]


def _tag_label(tags) -> str:
    norm = _normalize_tags(tags)
    if not norm:
        return "Engineering"
    t = norm[0]
    return re.sub(r"\b\w", lambda m: m.group().upper(), t.replace("-", " "))


def _esc(s: str) -> str:
    return _html.escape(s or "", quote=True)


def _esc_attr(s: str) -> str:
    return _html.escape(s or "", quote=True)


def _json_str(s: str) -> str:
    """Escape a string for embedding inside a JSON-LD literal."""
    return json.dumps(s or "")[1:-1]


PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title_esc} | {author}</title>
  <meta name="description" content="{desc_attr}">
  <link rel="icon" type="image/svg+xml" href="/favicon.svg">
  <link rel="canonical" href="{canonical}">

  <!-- Open Graph -->
  <meta property="og:title" content="{title_attr}">
  <meta property="og:description" content="{desc_attr}">
  <meta property="og:type" content="article">
  <meta property="og:url" content="{canonical}">
  <meta property="og:site_name" content="{author}">
  <meta property="og:image" content="{site}/og-image.png">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta property="article:published_time" content="{date_iso}">
  <meta property="article:author" content="{author}">

  <!-- Twitter Card -->
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:site" content="@astraedus">
  <meta name="twitter:title" content="{title_attr}">
  <meta name="twitter:description" content="{desc_attr}">
  <meta name="twitter:image" content="{site}/og-image.png">

  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=DM+Sans:ital,wght@0,400;0,500;0,600;0,700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <style>
    :root {{
      --bg: #09090b;
      --surface: #111113;
      --surface-2: #18181b;
      --border: #27272a;
      --border-hover: #3f3f46;
      --text: #fafafa;
      --text-secondary: #a1a1aa;
      --text-dim: #71717a;
      --accent: #f59e0b;
      --accent-dim: rgba(245, 158, 11, 0.12);
      --accent-border: rgba(245, 158, 11, 0.25);
      --serif: 'Instrument Serif', Georgia, serif;
      --sans: 'DM Sans', -apple-system, sans-serif;
      --mono: 'JetBrains Mono', 'SF Mono', monospace;
    }}

    * {{ margin: 0; padding: 0; box-sizing: border-box; }}

    body {{
      font-family: var(--sans);
      background: var(--bg);
      color: var(--text);
      line-height: 1.6;
      -webkit-font-smoothing: antialiased;
      overflow-x: hidden;
    }}

    ::selection {{ background: var(--accent); color: var(--bg); }}
    a {{ color: inherit; }}
    .container {{ max-width: 1100px; margin: 0 auto; padding: 0 28px; }}

    /* Grain */
    body::before {{
      content: '';
      position: fixed;
      top: 0; left: 0; right: 0; bottom: 0;
      background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
      opacity: 0.025;
      pointer-events: none;
      z-index: 9999;
    }}

    /* Nav */
    nav {{ padding: 24px 0; position: relative; z-index: 10; }}
    nav .container {{
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}
    .logo {{
      font-family: var(--mono);
      font-size: 0.85rem;
      font-weight: 500;
      color: var(--text-dim);
      letter-spacing: 0.02em;
      text-decoration: none;
    }}
    .logo strong {{ color: var(--text); font-weight: 500; }}
    .nav-links {{ display: flex; align-items: center; gap: 28px; }}
    .nav-links a {{
      font-size: 0.85rem;
      color: var(--text-secondary);
      text-decoration: none;
      transition: color 0.2s;
    }}
    .nav-links a:hover {{ color: var(--text); }}
    .nav-links a.active {{ color: var(--accent); }}
    .nav-cta {{
      background: var(--text);
      color: var(--bg) !important;
      padding: 8px 20px;
      border-radius: 6px;
      font-weight: 600;
      font-size: 0.82rem;
      text-decoration: none;
      transition: opacity 0.2s;
    }}
    .nav-cta:hover {{ opacity: 0.88; }}

    /* Article layout */
    .article-header {{
      padding: 80px 0 0;
      position: relative;
    }}
    .article-header::before {{
      content: '';
      position: absolute;
      top: -80px; left: 50%;
      transform: translateX(-50%);
      width: 500px; height: 500px;
      background: radial-gradient(circle, rgba(245,158,11,0.04) 0%, transparent 70%);
      pointer-events: none;
    }}
    .article-header .back-link {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-size: 0.82rem;
      color: var(--text-dim);
      text-decoration: none;
      margin-bottom: 40px;
      transition: color 0.2s;
    }}
    .article-header .back-link:hover {{ color: var(--text-secondary); }}
    .article-header .back-link::before {{ content: '\\2190'; }}
    .article-meta {{
      display: flex;
      align-items: center;
      gap: 16px;
      margin-bottom: 20px;
      flex-wrap: wrap;
    }}
    .article-date {{
      font-family: var(--mono);
      font-size: 0.72rem;
      color: var(--text-dim);
      letter-spacing: 0.02em;
    }}
    .article-tag {{
      font-family: var(--mono);
      font-size: 0.65rem;
      font-weight: 500;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      color: var(--accent);
      background: var(--accent-dim);
      border: 1px solid var(--accent-border);
      padding: 3px 10px;
      border-radius: 20px;
    }}
    .article-reading {{
      font-family: var(--mono);
      font-size: 0.72rem;
      color: var(--text-dim);
    }}
    .article-header h1 {{
      font-family: var(--serif);
      font-size: clamp(2rem, 5vw, 3rem);
      font-weight: 400;
      line-height: 1.12;
      letter-spacing: -0.02em;
      margin-bottom: 20px;
      max-width: 720px;
    }}
    .article-lede {{
      font-size: 1.1rem;
      color: var(--text-secondary);
      line-height: 1.7;
      max-width: 640px;
      margin-bottom: 48px;
    }}

    /* Article body */
    .article-body {{
      max-width: 680px;
      padding-bottom: 80px;
    }}
    .article-body p {{
      font-size: 1.02rem;
      line-height: 1.78;
      color: var(--text-secondary);
      margin-bottom: 24px;
    }}
    .article-body img {{
      max-width: 100%;
      height: auto;
      border-radius: 10px;
      border: 1px solid var(--border);
      margin: 8px 0 28px;
    }}
    .article-body h2 {{
      font-family: var(--serif);
      font-size: 1.65rem;
      font-weight: 400;
      color: var(--text);
      margin-top: 56px;
      margin-bottom: 20px;
      letter-spacing: -0.01em;
      line-height: 1.2;
    }}
    .article-body h3 {{
      font-size: 1.05rem;
      font-weight: 600;
      color: var(--text);
      margin-top: 40px;
      margin-bottom: 14px;
    }}
    .article-body strong {{
      color: var(--text);
      font-weight: 600;
    }}
    .article-body em {{
      color: var(--accent);
      font-style: italic;
    }}
    .article-body a {{
      color: var(--accent);
      text-decoration: underline;
      text-underline-offset: 3px;
      text-decoration-color: var(--accent-border);
      transition: text-decoration-color 0.2s;
    }}
    .article-body a:hover {{
      text-decoration-color: var(--accent);
    }}
    .article-body ul, .article-body ol {{
      color: var(--text-secondary);
      font-size: 1.02rem;
      line-height: 1.78;
      margin: 0 0 24px 0;
      padding-left: 22px;
    }}
    .article-body li {{
      margin-bottom: 10px;
    }}
    .article-body li::marker {{
      color: var(--text-dim);
    }}
    .article-body blockquote {{
      border-left: 2px solid var(--accent);
      padding-left: 24px;
      margin: 32px 0;
    }}
    .article-body blockquote p {{
      font-family: var(--serif);
      font-size: 1.15rem;
      font-style: italic;
      color: var(--text);
      line-height: 1.6;
    }}
    .article-body code {{
      font-family: var(--mono);
      font-size: 0.88em;
      background: var(--surface-2);
      border: 1px solid var(--border);
      padding: 2px 7px;
      border-radius: 4px;
      color: var(--accent);
    }}
    .article-body pre {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 24px;
      margin: 28px 0;
      overflow-x: auto;
    }}
    .article-body pre code {{
      background: none;
      border: none;
      padding: 0;
      font-size: 0.85rem;
      line-height: 1.65;
      color: var(--text-secondary);
    }}
    .article-body hr {{
      border: none;
      height: 1px;
      background: var(--border);
      margin: 48px 0;
    }}
    .article-body table {{
      width: 100%;
      border-collapse: collapse;
      margin: 28px 0;
      font-size: 0.95rem;
    }}
    .article-body thead th {{
      text-align: left;
      font-family: var(--mono);
      font-size: 0.72rem;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      color: var(--text-dim);
      padding: 10px 12px;
      border-bottom: 1px solid var(--border);
    }}
    .article-body tbody td {{
      padding: 12px;
      border-bottom: 1px solid var(--border);
      color: var(--text-secondary);
    }}
    .article-body tbody tr:last-child td {{
      border-bottom: none;
    }}

    /* Separator line */
    .separator {{
      width: 40px;
      height: 2px;
      background: var(--accent);
      margin: 48px 0;
      opacity: 0.5;
    }}

    /* Footer CTA */
    .article-footer {{
      border-top: 1px solid var(--border);
      padding: 48px 0;
      max-width: 680px;
    }}
    .article-footer p {{
      font-size: 0.92rem;
      color: var(--text-dim);
      line-height: 1.65;
      margin-bottom: 20px;
    }}
    .article-footer .footer-links {{
      display: flex;
      gap: 16px;
      flex-wrap: wrap;
    }}
    .article-footer .footer-links a {{
      font-size: 0.82rem;
      font-weight: 600;
      color: var(--accent);
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      gap: 4px;
      transition: opacity 0.2s;
    }}
    .article-footer .footer-links a:hover {{ opacity: 0.75; }}
    .article-footer .footer-links a::after {{ content: '\\2197'; font-size: 0.9em; }}

    /* Footer */
    footer {{
      padding: 32px 0;
      border-top: 1px solid var(--border);
    }}
    footer .container {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 0.78rem;
      color: var(--text-dim);
    }}
    footer a {{ color: var(--text-dim); text-decoration: none; }}
    footer a:hover {{ color: var(--text-secondary); }}

    /* Animations */
    @keyframes fadeUp {{
      from {{ opacity: 0; transform: translateY(20px); }}
      to {{ opacity: 1; transform: translateY(0); }}
    }}
    .article-header .back-link,
    .article-meta,
    .article-header h1,
    .article-lede {{
      animation: fadeUp 0.6s ease-out both;
    }}
    .article-meta {{ animation-delay: 0.05s; }}
    .article-header h1 {{ animation-delay: 0.1s; }}
    .article-lede {{ animation-delay: 0.15s; }}
    .article-body {{ animation: fadeUp 0.6s ease-out 0.25s both; }}

    @media (max-width: 768px) {{
      .article-header {{ padding: 48px 0 0; }}
      .article-header h1 {{ font-size: 1.75rem; }}
      .nav-links a:not(.nav-cta) {{ display: none; }}
    }}
  </style>
<!-- Cloudflare Web Analytics --><script defer src="https://static.cloudflareinsights.com/beacon.min.js" data-cf-beacon='{{"token": "8b578cad5b3646a7b9c81ac6acbb76ab"}}'></script><!-- End Cloudflare Web Analytics -->

  <!-- JSON-LD Structured Data -->
  <script type="application/ld+json">
  {{
    "@context": "https://schema.org",
    "@type": "Article",
    "headline": "{headline_json}",
    "description": "{desc_json}",
    "url": "{canonical}",
    "image": "{site}/og-image.png",
    "datePublished": "{date_iso}",
    "author": {{
        "@type": "Person",
        "name": "{author}",
        "url": "{site}"
    }},
    "publisher": {{
        "@type": "Person",
        "name": "{author}",
        "url": "{site}"
    }}
}}
  </script>
</head>
<body>

<nav>
  <div class="container">
    <a href="/" class="logo"><strong>diven</strong>@astraedus ~</a>
    <div class="nav-links">
      <a href="/#projects">Projects</a>
      <a href="/blog" class="active">Blog</a>
      <a href="https://github.com/astraedus" target="_blank" rel="noopener">GitHub</a>
      <a href="mailto:theagentthatcould@gmail.com" class="nav-cta" target="_blank" rel="noopener">Email me</a>
    </div>
  </div>
</nav>

<article>
  <div class="container">

    <header class="article-header">
      <a href="/blog" class="back-link">Back to blog</a>
      <div class="article-meta">
        <span class="article-date">{date_human}</span>
        <span class="article-tag">{tag_label}</span>
        <span class="article-reading">{reading} min read</span>
      </div>
      <h1>{title_esc}</h1>
      <p class="article-lede">{lede_html}</p>
    </header>

    <div class="article-body">
{body_html}
    </div>

    <div class="separator"></div>

    <div class="article-footer">
      <p>I build production AI systems, billing-heavy SaaS, and the auth boundaries that keep tenant data from leaking. If you want help with something similar, the links below are the fastest way in.</p>
      <div class="footer-links">
        <a href="mailto:theagentthatcould@gmail.com" target="_blank" rel="noopener">Email me</a>
        <a href="https://github.com/astraedus" target="_blank" rel="noopener">GitHub</a>
        <a href="https://www.amazon.com/dp/B0GTX9N3FZ" target="_blank" rel="noopener">Book</a>
        <a href="/blog">More posts</a>
      </div>
    </div>

  </div>
</article>

<footer>
  <div class="container">
    <span>Diven Rastdus / Astraedus, 2026</span>
    <span>Sydney, Australia</span>
  </div>
</footer>

</body>
</html>
"""


def render_page(meta: dict, body_markdown: str) -> str:
    slug = meta["slug"].strip("/")
    canonical = f"{SITE}/blog/{slug}/"
    title = meta["title"].strip()
    description = (meta.get("description") or "").strip()

    body_md = _strip_frontmatter(body_markdown)

    # Lede: prefer the first prose paragraph from the body, fall back to description.
    first_para, rest_md = _split_lede(body_md)
    if first_para:
        lede_source = first_para
        content_md = rest_md
    else:
        lede_source = description
        content_md = body_md
    if not description:
        # Derive a description from the lede (plain text, truncated).
        plain = re.sub(r"\s+", " ", re.sub(r"[*_`#>\[\]()]", "", lede_source)).strip()
        description = (plain[:157] + "...") if len(plain) > 160 else plain

    lede_html = _inline_md(lede_source) if lede_source else ""
    body_html = _harden_images(_md_to_html(content_md))
    body_html = "\n".join("      " + ln if ln.strip() else ln for ln in body_html.splitlines())

    reading = meta.get("reading_time_minutes")
    if not reading:
        words = len(re.findall(r"\w+", body_md))
        reading = max(1, round(words / 200))

    return PAGE_TEMPLATE.format(
        site=SITE,
        author=AUTHOR,
        title_esc=_esc(title),
        title_attr=_esc_attr(title),
        desc_attr=_esc_attr(description),
        headline_json=_json_str(title),
        desc_json=_json_str(description),
        canonical=canonical,
        date_iso=_fmt_date_iso(meta.get("published_at", "")),
        date_human=_fmt_date_human(meta.get("published_at", "")),
        tag_label=_esc(_tag_label(meta.get("tags"))),
        reading=reading,
        lede_html=lede_html,
        body_html=body_html,
    )


_SAFE_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def write_page(meta: dict, body_markdown: str, repo_root: Path) -> Path:
    slug = meta["slug"].strip("/")
    # Defense-in-depth: the slug becomes a directory under blog/. Reject anything
    # that could escape it (path traversal) even though the canonical regex
    # upstream already excludes '/'. Blog slugs are lowercase-kebab only.
    if not _SAFE_SLUG.match(slug):
        raise ValueError(f"unsafe blog slug: {slug!r}")
    out = (repo_root / "blog" / slug / "index.html").resolve()
    blog_root = (repo_root / "blog").resolve()
    if blog_root not in out.parents:
        raise ValueError(f"slug {slug!r} resolves outside blog/: {out}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_page(meta, body_markdown), encoding="utf-8")
    return out


def main():
    ap = argparse.ArgumentParser(description="Render one astraedus.dev blog page from markdown.")
    ap.add_argument("--json", required=True, help="JSON descriptor: {title, slug, description, tags, published_at, reading_time_minutes, body_markdown}")
    ap.add_argument("--out", help="Output path (default: <repo>/blog/<slug>/index.html)")
    ap.add_argument("--repo", default=str(Path(__file__).resolve().parent.parent), help="Repo root")
    args = ap.parse_args()

    d = json.loads(Path(args.json).read_text())
    body = d.pop("body_markdown")
    html_out = render_page(d, body)
    if args.out:
        p = Path(args.out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(html_out, encoding="utf-8")
        print(f"wrote {p}")
    else:
        p = write_page(d, body, Path(args.repo))
        print(f"wrote {p}")


if __name__ == "__main__":
    main()
