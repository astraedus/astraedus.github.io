#!/usr/bin/env python3
"""
backfill-canonicals.py -- One-shot: generate every astraedus.dev/blog/<slug> page
that a published Dev.to article declares as its canonical_url but does not exist.

Audits the Dev.to API (source of truth) against local /blog dirs, then renders the
missing pages with scripts/build-blog-page.py (self-canonical), so Google's
canonical follow resolves 200 instead of 404.

Idempotent: skips slugs whose dir already exists.

    python3 scripts/backfill-canonicals.py            # generate
    python3 scripts/backfill-canonicals.py --audit    # report only, write nothing
"""
import argparse
import importlib.util
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
DEVTO_KEY_FILE = os.path.expanduser("~/.secrets/devto-api-key")

_SPEC = importlib.util.spec_from_file_location("build_blog_page", str(REPO / "scripts" / "build-blog-page.py"))
bbp = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(bbp)


def _get(url, with_key=False):
    headers = {"User-Agent": UA, "Accept": "application/json"}
    if with_key:
        headers["api-key"] = Path(DEVTO_KEY_FILE).read_text().strip()
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def list_published():
    out, page = [], 1
    while True:
        batch = _get(f"https://dev.to/api/articles/me/published?per_page=100&page={page}", with_key=True)
        if not batch:
            break
        out.extend(batch)
        if len(batch) < 100:
            break
        page += 1
        time.sleep(0.3)
    return out


def audit(published):
    blog = REPO / "blog"
    existing = {p.name for p in blog.iterdir() if p.is_dir()}
    gaps, ok = [], []
    for a in published:
        cu = a.get("canonical_url") or ""
        m = re.match(r"^https://astraedus\.dev/blog/([^/?#]+)/?$", cu)
        if not m:
            continue
        slug = m.group(1)
        (ok if slug in existing else gaps).append((a["id"], slug, a["title"]))
    return gaps, ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit", action="store_true", help="report only, write nothing")
    args = ap.parse_args()

    published = list_published()
    gaps, ok = audit(published)
    print(f"Published on Dev.to: {len(published)}")
    print(f"Declare astraedus.dev/blog canonical: {len(gaps) + len(ok)}  (resolve: {len(ok)}, 404 gaps: {len(gaps)})")
    for _id, slug, title in gaps:
        print(f"  GAP  [{_id}] {slug}")

    if args.audit:
        return

    written = []
    for _id, slug, title in gaps:
        art = _get(f"https://dev.to/api/articles/{_id}")
        meta = {
            "title": art["title"],
            "slug": slug,
            "description": (art.get("description") or "").strip(),
            "tags": art.get("tag_list", []),
            "published_at": art.get("published_at"),
            "reading_time_minutes": art.get("reading_time_minutes"),
        }
        out = bbp.write_page(meta, art["body_markdown"], REPO)
        written.append(str(out.relative_to(REPO)))
        print(f"  +    {out.relative_to(REPO)}")
        time.sleep(0.25)

    print(f"\nWrote {len(written)} pages. Next: node scripts/enhance-blog-seo.js")


if __name__ == "__main__":
    main()
