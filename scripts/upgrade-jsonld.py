#!/usr/bin/env python3
"""
upgrade-jsonld.py -- Regenerate the Article/TechArticle (+ FAQPage) JSON-LD on every
existing blog/<slug>/index.html, in place, from data the page already carries.

Why in-place over a full re-render: 11 of the blog posts are hand-written native HTML
with NO markdown/Dev.to source. Re-rendering them through build-blog-page.py would lose
their body. This upgrader instead reads each page's own <head> meta (title, description,
canonical, datePublished, tag) + its rendered <h2> section headings and the first
paragraph under each, then rebuilds the structured data via the SAME assembler the
renderer uses (build_blog_page.build_jsonld_graph) -- so a Dev.to-backed page and a
native page get byte-identical schema shape. Body content is never touched.

It swaps the FIRST `application/ld+json` block (the Article one). The additive
BreadcrumbList block injected by enhance-blog-seo.js is left untouched.

Idempotent: re-running produces the same enriched block.

    python3 scripts/upgrade-jsonld.py            # apply to every page
    python3 scripts/upgrade-jsonld.py --check     # report, write nothing
"""
import argparse
import html as _html
import importlib.util
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BLOG = REPO / "blog"

_SPEC = importlib.util.spec_from_file_location(
    "build_blog_page", str(REPO / "scripts" / "build-blog-page.py")
)
bbp = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(bbp)

# Matches the renderer's first ld+json block (the Article one). Non-greedy so it
# stops at the first </script>; the BreadcrumbList block (added later) is separate.
_ARTICLE_LD_RE = re.compile(
    r'(<script type="application/ld\+json">)\s*(\{.*?\})\s*(</script>)', re.S
)


def _strip_tags(s: str) -> str:
    return _html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


def _meta_content(html, *, name=None, prop=None):
    if name:
        m = re.search(rf'<meta name="{re.escape(name)}" content="([^"]*)"', html)
    else:
        m = re.search(rf'<meta property="{re.escape(prop)}" content="([^"]*)"', html)
    return _html.unescape(m.group(1)) if m else ""


def _extract_body_faq(html):
    """Build [(question, answer)] from rendered <h2> headings + the first <p> after
    each, scoped to .article-body. Mirrors the markdown extractor's gates so the FAQ
    decision matches what the renderer would emit."""
    bm = re.search(
        r'<div class="article-body">(.*?)(?:<div class="separator"|'
        r'<div class="article-footer"|<footer)',
        html, re.S,
    )
    body = bm.group(1) if bm else html
    # Sequence of (kind, text) tokens for h2/p in document order.
    pairs = []
    pending_q = None
    for m in re.finditer(r"<(h2|p)\b[^>]*>(.*?)</\1>", body, re.S):
        kind, inner = m.group(1), m.group(2)
        text = _strip_tags(inner)
        if kind == "h2":
            pending_q = text if text else None
        elif kind == "p" and pending_q:
            answer = bbp._first_answer(text)
            if answer and len(answer) >= 25 and len(pending_q) <= 120:
                pairs.append((pending_q, answer))
            pending_q = None  # only the first paragraph becomes the answer
    return pairs


def upgrade_page(path: Path):
    """Return (new_html, changed_bool, has_faq). Reuses the renderer's schema assembler."""
    html = path.read_text(encoding="utf-8")

    title = _strip_tags(re.search(r"<h1>(.*?)</h1>", html, re.S).group(1)) \
        if re.search(r"<h1>(.*?)</h1>", html, re.S) else ""
    description = _meta_content(html, name="description")
    canon_m = re.search(r'<link rel="canonical" href="([^"]+)"', html)
    canonical = canon_m.group(1) if canon_m else ""
    date_iso = _meta_content(html, prop="article:published_time")[:10]
    tag = _strip_tags(
        (re.search(r'<span class="article-tag">([^<]*)</span>', html) or [None, ""])[1]
        if re.search(r'<span class="article-tag">([^<]*)</span>', html) else ""
    )

    if not (title and canonical):
        return html, False, False  # not a renderable post; skip defensively

    is_tech = bbp._is_tech_article([tag]) if tag else False
    pairs = _extract_body_faq(html)
    faq = pairs if bbp._wants_faq(title, pairs) else None

    doc = bbp.build_jsonld_graph(
        title=title, description=description, canonical=canonical,
        date_iso=date_iso, modified_iso=date_iso, is_tech=is_tech, faq_pairs=faq,
    )
    has_faq = bool(faq)
    new_body = bbp.serialize_jsonld(doc)
    new_block = f"  <script type=\"application/ld+json\">\n{new_body}\n  </script>"

    if not _ARTICLE_LD_RE.search(html):
        # No existing Article block (shouldn't happen on these pages) -> inject before </head>.
        new_html = html.replace("</head>", f"{new_block}\n</head>", 1)
        return new_html, new_html != html, has_faq

    new_html = _ARTICLE_LD_RE.sub(
        lambda m: new_block.lstrip(), html, count=1
    )
    return new_html, new_html != html, has_faq


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="report only, write nothing")
    args = ap.parse_args()

    changed, unchanged, faq_slugs = [], [], []
    for p in sorted(BLOG.iterdir()):
        if not p.is_dir():
            continue
        f = p / "index.html"
        if not f.exists():
            continue
        new_html, did, has_faq = upgrade_page(f)
        if has_faq:
            faq_slugs.append(p.name)
        if did:
            changed.append(p.name)
            if not args.check:
                f.write_text(new_html, encoding="utf-8")
        else:
            unchanged.append(p.name)

    verb = "would update" if args.check else "updated"
    print(f"JSON-LD: {verb} {len(changed)} page(s), {len(unchanged)} unchanged.")
    print(f"Pages emitting FAQPage: {len(faq_slugs)}")
    for s in faq_slugs:
        print(f"  FAQ  {s}")
    for s in changed:
        print(f"  ~    {s}")


if __name__ == "__main__":
    main()
