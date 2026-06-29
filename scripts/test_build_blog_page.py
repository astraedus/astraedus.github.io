#!/usr/bin/env python3
"""
Unit tests for build-blog-page.py renderer.

Run: python3 scripts/test_build_blog_page.py

Tests the CLASS of failures that produced the SEO bug (a generated page that
wouldn't match the template / wouldn't be self-canonical), plus markdown
fidelity for every feature present across the real backfill corpus
(code fences, tables, lists, blockquotes, images, inline links, JSX-in-fences).
"""
import importlib.util
import json
import re
import sys
import unittest
from pathlib import Path

# Import the hyphenated module by path.
_SPEC = importlib.util.spec_from_file_location(
    "build_blog_page", str(Path(__file__).resolve().parent / "build-blog-page.py")
)
bbp = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(bbp)


META = {
    "title": "My Cron Jobs Were Firing 10 Hours Off Their Own Comments",
    "slug": "cron-jobs-firing-wrong-timezone-cron-tz",
    "description": "Cron schedules in local time. My UTC comment was a lie cron never read.",
    "tags": ["linux", "cron", "devops"],
    "published_at": "2026-06-24T22:11:07Z",
    "reading_time_minutes": 5,
}


class RenderInvariants(unittest.TestCase):
    """Invariants that, if violated, reproduce the dead-canonical bug class."""

    def setUp(self):
        self.html = bbp.render_page(META, "Intro paragraph.\n\n## A heading\n\nBody text here.")

    def test_self_canonical_to_astraedus_with_slug(self):
        # The whole point: the page must claim ITSELF as canonical at the declared slug.
        self.assertIn(
            '<link rel="canonical" href="https://astraedus.dev/blog/cron-jobs-firing-wrong-timezone-cron-tz/">',
            self.html,
        )

    def test_canonical_is_not_devto(self):
        self.assertNotIn('rel="canonical" href="https://dev.to', self.html)

    def test_og_url_matches_canonical(self):
        self.assertIn(
            'property="og:url" content="https://astraedus.dev/blog/cron-jobs-firing-wrong-timezone-cron-tz/"',
            self.html,
        )

    def test_jsonld_url_matches_canonical(self):
        self.assertIn('"url": "https://astraedus.dev/blog/cron-jobs-firing-wrong-timezone-cron-tz/"', self.html)

    def test_title_and_description_present(self):
        self.assertIn("<title>My Cron Jobs Were Firing 10 Hours Off Their Own Comments | Diven Rastdus</title>", self.html)
        self.assertIn('name="description" content="Cron schedules in local time.', self.html)

    def test_template_structure_present(self):
        # Hooks that enhance-blog-seo.js depends on.
        for needle in ['<div class="article-body">', '<header class="article-header">',
                       '<h1>', 'class="article-footer"', '<!DOCTYPE html>']:
            self.assertIn(needle, self.html)

    def test_seo_enhancer_regex_will_match_body(self):
        # enhance-blog-seo.js matches `<div class="article-body">` ... up to separator/footer.
        import re
        m = re.search(
            r'(<div class="article-body">)([\s\S]*?)(<\/div>\s*<div class="separator")',
            self.html,
        )
        self.assertIsNotNone(m, "enhance-blog-seo.js body-bounds regex must match generated page")


class MarkdownFidelity(unittest.TestCase):
    def render_body(self, md):
        return bbp.render_page(META, "Lede paragraph.\n\n" + md)

    def test_fenced_code_block(self):
        h = self.render_body("```bash\ntimedatectl\n```")
        self.assertIn("<pre>", h)
        self.assertIn("timedatectl", h)

    def test_jsx_in_fence_is_escaped_not_rendered(self):
        # The expo-superwall / green-tests articles have JSX inside fences.
        h = self.render_body("```tsx\n<SuperwallProvider apiKey={KEY}>\n```")
        self.assertIn("&lt;SuperwallProvider", h)
        self.assertNotIn("<SuperwallProvider", h)  # must NOT become a real tag

    def test_table(self):
        md = "| A | B |\n|---|---|\n| 1 | 2 |"
        h = self.render_body(md)
        self.assertIn("<table>", h)
        self.assertIn("<th>A</th>", h)

    def test_bullet_list(self):
        h = self.render_body("- one\n- two\n- three")
        self.assertIn("<ul>", h)
        self.assertIn("<li>one</li>", h)

    def test_numbered_list(self):
        h = self.render_body("1. first\n2. second")
        self.assertIn("<ol>", h)

    def test_blockquote(self):
        h = self.render_body("> a quoted insight")
        self.assertIn("<blockquote>", h)

    def test_image_is_responsive(self):
        h = self.render_body("![alt text](https://i.imgur.com/KSq8jsJ.png)")
        self.assertIn("<img", h)
        self.assertIn("max-width:100%", h)

    def test_inline_link(self):
        h = self.render_body("See [the docs](https://example.com) for more.")
        self.assertIn('<a href="https://example.com"', h)

    def test_inline_code_and_bold(self):
        h = self.render_body("Set `CRON_TZ` and it is **fixed**.")
        self.assertIn("<code>CRON_TZ</code>", h)
        self.assertIn("<strong>fixed</strong>", h)

    def test_h2_h3_headings(self):
        h = self.render_body("## Top section\n\ntext\n\n### Sub section\n\nmore")
        self.assertIn("<h2>Top section</h2>", h)
        self.assertIn("<h3>Sub section</h3>", h)

    def test_tag_list_accepts_string_and_list(self):
        # REGRESSION: /articles/{id} returns tag_list as a comma-separated STRING,
        # /articles/me/published returns a LIST. tags[0] on a string yields the
        # first CHARACTER ("L"), producing a one-letter tag chip. Both must work.
        self.assertEqual(bbp._tag_label("linux, cron, devops"), "Linux")
        self.assertEqual(bbp._tag_label(["linux", "cron"]), "Linux")
        self.assertEqual(bbp._tag_label("ai-evaluation"), "Ai Evaluation")
        self.assertEqual(bbp._tag_label(""), "Engineering")
        self.assertEqual(bbp._tag_label([]), "Engineering")
        # And end to end, a string tag_list must not render a one-char chip.
        m = dict(META, tags="linux, cron, devops")
        h = bbp.render_page(m, "Lede.\n\n## H\n\nbody")
        self.assertIn('<span class="article-tag">Linux</span>', h)

    def test_lede_pulled_from_first_paragraph(self):
        h = bbp.render_page(META, "This is the opening hook.\n\n## Heading\n\nBody.")
        self.assertIn('<p class="article-lede">This is the opening hook.</p>', h)
        # First paragraph should NOT be duplicated inside the body.
        body = h.split('<div class="article-body">')[1]
        self.assertNotIn("This is the opening hook.", body)


class SlugSafety(unittest.TestCase):
    def test_rejects_traversal_slugs(self):
        import tempfile
        from pathlib import Path
        repo = Path(tempfile.mkdtemp())
        for bad in ["../evil", "a/b", "..", "Foo", "has space", "-leading", ".hidden"]:
            with self.assertRaises(ValueError, msg=f"should reject {bad!r}"):
                bbp.write_page(dict(META, slug=bad), "body", repo)

    def test_accepts_real_slugs(self):
        import tempfile
        from pathlib import Path
        repo = Path(tempfile.mkdtemp())
        for good in [
            "cron-jobs-firing-wrong-timezone-cron-tz",
            "your-ai-agent-evaluation-is-lying-to-you-why-10-test-runs-prove-nothing",
            "3-react-native-bugs-that-crashed-on-device-but-passed-every-test",
            "expo-sdk-56-bugs-crashed-app",
        ]:
            out = bbp.write_page(dict(META, slug=good), "Lede.\n\n## H\n\nbody", repo)
            self.assertTrue(out.exists())


def _extract_jsonld_graphs(html):
    """Return every parsed JSON-LD doc emitted by the renderer (un-guarding </ -> <\\/)."""
    graphs = []
    for block in re.findall(
        r'<script type="application/ld\+json">\n(.*?)\n  </script>', html, re.S
    ):
        graphs.append(json.loads(block.replace("<\\/", "</")))
    return graphs


# A listicle/gotcha-shaped article: question-shaped ## headings + a "3 ... bugs" title.
LISTICLE_BODY = (
    "The lede paragraph hooks the reader here.\n\n"
    "## Why did the app crash only on a real device?\n\n"
    "The Hermes engine evaluates differently than the JS test runner, so a parse "
    "the mock accepted threw at runtime.\n\n"
    "## What is the AsyncStorage race that tests miss?\n\n"
    "Tests run storage synchronously. On device two writes race and the second "
    "silently wins, dropping the first draft.\n\n"
    "## How do you catch this class before shipping?\n\n"
    "Run the real bundle on a real device with smoke flows. A green Jest suite is "
    "not device coverage.\n"
)
LISTICLE_META = dict(
    META,
    title="3 React Native Bugs That Crashed On Device But Passed Every Test",
    tags=["react", "reactnative", "javascript"],
)

# A prose essay: declarative headings, narrative title, non-technical tags.
PROSE_BODY = (
    "An opening reflection on the void.\n\n"
    "## The horizon\n\n"
    "Information at the boundary behaves like memory, a record etched into geometry "
    "that no fall can erase.\n\n"
    "## The temperature\n\n"
    "Hawking showed the void glows faintly, a thermodynamic whisper from what looks "
    "like nothing at all.\n"
)
PROSE_META = dict(
    META,
    title="Notes On Black Holes As Entropy Machines",
    tags=["physics", "writing"],
)


class JsonLdSchema(unittest.TestCase):
    """Invariants over the GEO/answer-engine JSON-LD. These guard the class of bug
    where the structured data is malformed, missing a Rich-Results-required field,
    un-escaped (breaks the parse / breaks out of the <script>), or emits spammy
    FAQ markup on prose."""

    def graphs(self, meta, body):
        return _extract_jsonld_graphs(bbp.render_page(meta, body))

    def article_node(self, meta, body):
        nodes = self.graphs(meta, body)[0]["@graph"]
        arts = [n for n in nodes if n["@type"] in ("Article", "TechArticle")]
        self.assertEqual(len(arts), 1, "exactly one Article/TechArticle node")
        return arts[0]

    def test_jsonld_parses(self):
        # Every emitted ld+json block must be valid JSON (the whole point).
        for g in self.graphs(LISTICLE_META, LISTICLE_BODY):
            self.assertIn("@context", g)

    def test_article_has_required_rich_result_fields(self):
        art = self.article_node(META, "Lede.\n\n## H\n\nBody text that is here.")
        for key in ("headline", "description", "url", "image",
                    "datePublished", "dateModified", "author", "publisher",
                    "mainEntityOfPage"):
            self.assertIn(key, art, f"Article JSON-LD missing required field: {key}")
        self.assertEqual(art["author"]["@type"], "Person")
        self.assertEqual(art["author"]["name"], "Diven Rastdus")

    def test_publisher_is_raedus_labs_organization(self):
        art = self.article_node(META, "Lede.\n\n## H\n\nBody text here now.")
        self.assertEqual(art["publisher"]["@type"], "Organization")
        self.assertEqual(art["publisher"]["name"], "Raedus Labs")
        self.assertIn("logo", art["publisher"])

    def test_date_modified_defaults_to_published(self):
        art = self.article_node(META, "Lede.\n\n## H\n\nBody text here now.")
        self.assertEqual(art["dateModified"], art["datePublished"])
        self.assertEqual(art["dateModified"], "2026-06-24")

    def test_tech_tags_yield_techarticle(self):
        # META carries linux/cron/devops -> TechArticle.
        art = self.article_node(META, "Lede.\n\n## H\n\nBody text here now.")
        self.assertEqual(art["@type"], "TechArticle")

    def test_non_tech_tags_yield_plain_article(self):
        art = self.article_node(PROSE_META, PROSE_BODY)
        self.assertEqual(art["@type"], "Article")

    def test_faqpage_emitted_for_listicle_gotcha_shape(self):
        nodes = self.graphs(LISTICLE_META, LISTICLE_BODY)[0]["@graph"]
        faqs = [n for n in nodes if n["@type"] == "FAQPage"]
        self.assertEqual(len(faqs), 1, "listicle/Q&A article must emit one FAQPage")
        qs = faqs[0]["mainEntity"]
        self.assertGreaterEqual(len(qs), 2)
        for q in qs:
            self.assertEqual(q["@type"], "Question")
            self.assertTrue(q["name"])
            self.assertEqual(q["acceptedAnswer"]["@type"], "Answer")
            self.assertTrue(q["acceptedAnswer"]["text"])
            # Answers are plain text -- no markdown noise that AI engines would lift verbatim.
            self.assertNotIn("```", q["acceptedAnswer"]["text"])
            self.assertNotRegex(q["acceptedAnswer"]["text"], r"\[[^\]]+\]\([^)]+\)")

    def test_no_faqpage_on_prose_essay(self):
        nodes = self.graphs(PROSE_META, PROSE_BODY)[0]["@graph"]
        faqs = [n for n in nodes if n["@type"] == "FAQPage"]
        self.assertEqual(faqs, [], "narrative prose must NOT get spammy FAQ markup")

    def test_escaping_quotes_amp_and_script_breakout(self):
        meta = dict(
            META,
            title='Why "RLS OR" Leaks Rows & Breaks <Tenants>',
            description='Quotes "and" & <html> and </script> here.',
            tags=["postgres", "security", "sql"],
        )
        body = (
            "Lede.\n\n"
            "## Why does \"OR\" in an RLS policy leak rows?\n\n"
            "A policy USING (a OR b) evaluates as a union & matches rows it should "
            "not, and a </script> in prose must not break the JSON here.\n\n"
            "## Should you ever use OR in RLS?\n\n"
            "No. Split into separate PERMISSIVE policies, each with one predicate.\n"
        )
        html = bbp.render_page(meta, body)
        # Parses despite the hostile characters.
        graphs = _extract_jsonld_graphs(html)
        art = [n for n in graphs[0]["@graph"] if n["@type"] in ("Article", "TechArticle")][0]
        self.assertEqual(art["headline"], 'Why "RLS OR" Leaks Rows & Breaks <Tenants>')
        # A raw </script> inside the ld+json block would terminate the script early.
        block = re.search(
            r'<script type="application/ld\+json">\n(.*?)\n  </script>', html, re.S
        ).group(1)
        self.assertNotIn("</script>", block, "ld+json must not contain a raw closing script tag")

    def test_faq_answer_handles_section_with_only_code(self):
        # A section whose body is only a code fence yields no usable prose answer,
        # so it must be skipped rather than emitting an empty Answer.
        body = (
            "Lede.\n\n"
            "## How do you set the timezone?\n\n"
            "```bash\nexport TZ=UTC\n```\n\n"
            "## Why does cron ignore the comment?\n\n"
            "Cron never reads the comment line; it schedules in the daemon's local "
            "time regardless of what the comment claims.\n"
        )
        nodes = self.graphs(LISTICLE_META, body)[0]["@graph"]
        faqs = [n for n in nodes if n["@type"] == "FAQPage"]
        if faqs:
            for q in faqs[0]["mainEntity"]:
                self.assertTrue(q["acceptedAnswer"]["text"].strip(),
                                "no empty FAQ answers")


if __name__ == "__main__":
    unittest.main(verbosity=2)
