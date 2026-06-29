#!/usr/bin/env python3
"""
update-blog-index.py -- Keep blog/index.html (the post listing) and sitemap.xml in
sync with the actual blog/<slug>/index.html pages on disk.

Idempotent + non-destructive: it reads the title/description/date/tag straight out
of each post's own <head> (the single source of truth the post already carries),
and ONLY inserts cards/urls for slugs not already listed. Existing hand-curated
cards and sitemap entries are left untouched.

    python3 scripts/update-blog-index.py            # apply
    python3 scripts/update-blog-index.py --check     # report what would change

Run after generating new pages (backfill or publish-time forward-wire).
"""
import argparse
import html as _html
import re
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BLOG = REPO / "blog"
INDEX = BLOG / "index.html"
SITEMAP = REPO / "sitemap.xml"
SITE = "https://astraedus.dev"

# Non-article dirs in /blog that must never be listed as posts.
SKIP = {"index.html"}


def _meta(html, name=None, prop=None):
    if name:
        m = re.search(rf'<meta name="{re.escape(name)}" content="([^"]*)"', html)
    else:
        m = re.search(rf'<meta property="{re.escape(prop)}" content="([^"]*)"', html)
    return _html.unescape(m.group(1)) if m else ""


def read_post(slug):
    f = BLOG / slug / "index.html"
    if not f.exists():
        return None
    html = f.read_text(encoding="utf-8")
    title_m = re.search(r"<h1>(.*?)</h1>", html, re.S)
    title = _html.unescape(re.sub(r"<[^>]+>", "", title_m.group(1)).strip()) if title_m else ""
    desc = _meta(html, name="description")
    date_iso = _meta(html, prop="article:published_time")[:10]
    tag_m = re.search(r'<span class="article-tag">([^<]*)</span>', html)
    tag = _html.unescape(tag_m.group(1)) if tag_m else "Engineering"
    return {"slug": slug, "title": title, "description": desc, "date_iso": date_iso, "tag": tag}


def all_posts():
    posts = []
    for p in sorted(BLOG.iterdir()):
        if not p.is_dir() or p.name in SKIP:
            continue
        d = read_post(p.name)
        if d and d["title"]:
            posts.append(d)
    # newest first
    posts.sort(key=lambda d: d["date_iso"] or "0000-00-00", reverse=True)
    return posts


def _human_date(iso):
    try:
        return datetime.strptime(iso, "%Y-%m-%d").strftime("%B %-d, %Y")
    except Exception:
        return iso


def _esc(s):
    return _html.escape(s or "", quote=False)


def card_html(p):
    return (
        f'    <a href="/blog/{p["slug"]}/" class="post-card">\n'
        f'      <div class="post-meta">\n'
        f'        <span class="post-date">{_human_date(p["date_iso"])}</span>\n'
        f'        <span class="post-tag">{_esc(p["tag"])}</span>\n'
        f'      </div>\n'
        f'      <h2>{_esc(p["title"])}</h2>\n'
        f'      <p class="post-excerpt">{_esc(p["description"])}</p>\n'
        f'      <span class="post-read">Read</span>\n'
        f'    </a>\n'
    )


def _listed_slugs_in_order(html):
    """Return [(slug, span_start, span_end)] for each existing post-card, in document order."""
    out = []
    for m in re.finditer(r'(    <a href="/blog/([^/"]+)/" class="post-card">.*?</a>\n)', html, re.S):
        out.append((m.group(2), m.start(1), m.end(1)))
    return out


def update_index(check=False):
    html = INDEX.read_text(encoding="utf-8")
    existing = _listed_slugs_in_order(html)
    listed = {s for s, _, _ in existing}
    posts = all_posts()  # newest-first
    missing = [p for p in posts if p["slug"] not in listed]
    if not missing:
        return []
    if check:
        return [p["slug"] for p in missing]

    # PURELY ADDITIVE: never rewrite an existing card (their excerpts are
    # hand-curated and diverge from page meta-descriptions). Insert each missing
    # card before the first existing card that is OLDER than it, so the listing
    # stays newest-first. Date of an existing card is read from its own page.
    date_of = {p["slug"]: (p["date_iso"] or "0000-00-00") for p in posts}
    # Fallback: any listed slug whose page we couldn't read.
    for s in listed:
        date_of.setdefault(s, "0000-00-00")

    # Work on a mutable copy; insert one card at a time, recomputing positions.
    for p in sorted(missing, key=lambda x: x["date_iso"] or "0000-00-00"):  # oldest first
        existing = _listed_slugs_in_order(html)
        insert_at = None
        for slug, start, end in existing:
            if date_of.get(slug, "0000-00-00") < (p["date_iso"] or "0000-00-00"):
                insert_at = start  # first older card -> insert before it
                break
        card = card_html(p) + "\n"
        if insert_at is None:
            # All existing cards are newer (or equal) -> append at end of list.
            last_end = existing[-1][2] if existing else html.index('<div class="container">') + len('<div class="container">')
            html = html[:last_end] + "\n" + card + html[last_end:]
        else:
            html = html[:insert_at] + card + html[insert_at:]
    INDEX.write_text(html, encoding="utf-8")
    return [p["slug"] for p in missing]


SITEMAP_ENTRY = """  <url>
    <loc>{site}/blog/{slug}/</loc>
    <lastmod>{date}</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.7</priority>
  </url>
"""


def update_sitemap(check=False):
    xml = SITEMAP.read_text(encoding="utf-8")
    present = set(re.findall(r"<loc>https://astraedus\.dev/blog/([^/<]+)/</loc>", xml))
    posts = all_posts()
    missing = [p for p in posts if p["slug"] not in present]
    if not missing:
        return []
    if check:
        return [p["slug"] for p in missing]
    block = "".join(
        SITEMAP_ENTRY.format(site=SITE, slug=p["slug"], date=p["date_iso"] or datetime.utcnow().strftime("%Y-%m-%d"))
        for p in missing
    )
    xml = xml.replace("</urlset>", block + "</urlset>")
    SITEMAP.write_text(xml, encoding="utf-8")
    return [p["slug"] for p in missing]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="report only")
    args = ap.parse_args()
    idx = update_index(check=args.check)
    sm = update_sitemap(check=args.check)
    verb = "would add" if args.check else "added"
    print(f"blog/index.html: {verb} {len(idx)} card(s)")
    for s in idx:
        print(f"  + {s}")
    print(f"sitemap.xml: {verb} {len(sm)} url(s)")
    for s in sm:
        print(f"  + {s}")


if __name__ == "__main__":
    main()
