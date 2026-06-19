#!/usr/bin/env node
/**
 * One-off, idempotent SEO enhancer for astraedus.dev hand-written blog posts.
 * For each blog/<slug>/index.html:
 *   - adds slugified id anchors + hover "#" permalink to every .article-body h2/h3
 *   - injects an "On this page" TOC (top-level h2s, only if >= 3)
 *   - injects a visible breadcrumb trail (Home / Blog)
 *   - injects a BreadcrumbList JSON-LD block (additive; existing Article schema untouched)
 *   - injects scoped CSS using the site's existing CSS vars
 * Guarded by a marker comment so re-runs are no-ops.
 */
const fs = require("fs");
const path = require("path");

const REPO_ROOT = path.basename(__dirname) === "scripts" ? path.dirname(__dirname) : (__dirname.includes("astraedus.github.io") ? __dirname : "/home/astraedus/projects/astraedus.github.io");
const BLOG = path.join(REPO_ROOT, "blog");
const MARKER = "<!-- seo-enhanced -->";

function decodeEntities(s) {
  return String(s).replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&#39;/g, "'");
}
function slugify(t) {
  return decodeEntities(String(t)).toLowerCase().replace(/<[^>]+>/g, "").replace(/&[a-z]+;/g, " ")
    .replace(/[^a-z0-9\s-]/g, "").trim().replace(/\s+/g, "-").replace(/-+/g, "-");
}

const CSS = `  <style>
    .crumbs{font-family:var(--mono);font-size:.72rem;letter-spacing:.08em;text-transform:uppercase;color:var(--text-dim);margin-bottom:1.5rem}
    .crumbs a{color:var(--text-secondary);text-decoration:none}
    .crumbs a:hover{color:var(--accent)}
    .crumbs .sep{color:var(--border-hover);margin:0 .5rem}
    .post-toc{border:1px solid var(--border);border-radius:.6rem;background:var(--surface);padding:1rem 1.25rem;margin:0 0 2.5rem}
    .post-toc .toc-label{font-family:var(--mono);font-size:.66rem;letter-spacing:.12em;text-transform:uppercase;color:var(--text-dim);margin:0 0 .6rem}
    .post-toc ul{list-style:none;margin:0;padding:0}
    .post-toc li{margin:0 0 .35rem}
    .post-toc li:last-child{margin:0}
    .post-toc a{font-size:.9rem;color:var(--text-secondary);text-decoration:none;border-bottom:1px solid transparent;transition:color .15s,border-color .15s}
    .post-toc a:hover{color:var(--accent);border-bottom-color:var(--accent-border)}
    .article-body h2,.article-body h3{position:relative;scroll-margin-top:5rem}
    .article-body h2 .anchor,.article-body h3 .anchor{position:absolute;left:-1.1rem;color:var(--text-dim);opacity:0;text-decoration:none;border:none;transition:opacity .15s,color .15s}
    .article-body h2 .anchor::before,.article-body h3 .anchor::before{content:"#"}
    .article-body h2:hover .anchor,.article-body h3:hover .anchor{opacity:1}
    .article-body .anchor:hover{color:var(--accent)}
    @media(max-width:640px){.article-body h2 .anchor,.article-body h3 .anchor{display:none}}
  </style>`;

let done = 0, skipped = 0;
for (const slug of fs.readdirSync(BLOG)) {
  const file = path.join(BLOG, slug, "index.html");
  if (!fs.existsSync(file)) continue; // index.html listing has no subdir
  let html = fs.readFileSync(file, "utf8");
  if (html.includes(MARKER)) { console.log(`  = skip (already done) ${slug}`); skipped++; continue; }

  // --- 1. Heading ids + collect TOC (only within .article-body) ---
  const bodyMatch = html.match(/(<div class="article-body">)([\s\S]*?)(<\/div>\s*<div class="separator"|<\/div>\s*<div class="article-footer"|<\/div>\s*<footer)/);
  const seen = new Map();
  const toc = [];
  function processHeadings(body) {
    return body.replace(/<h([23])>([\s\S]*?)<\/h\1>/g, (full, depth, inner) => {
      const text = decodeEntities(inner.replace(/<[^>]+>/g, "")).trim();
      let id = slugify(text);
      if (!id) return full;
      if (seen.has(id)) { const n = seen.get(id) + 1; seen.set(id, n); id = `${id}-${n}`; } else seen.set(id, 1);
      toc.push({ depth: Number(depth), id, text });
      return `<h${depth} id="${id}"><a class="anchor" href="#${id}" aria-label="Link to this section"></a>${inner}</h${depth}>`;
    });
  }
  if (bodyMatch) {
    const newBody = processHeadings(bodyMatch[2]);
    html = html.replace(bodyMatch[2], newBody);
  } else {
    // Fallback: process all h2/h3 in the doc (none appear outside article-body in these files).
    html = processHeadings(html); // unlikely path; logged below
    console.log(`  ! ${slug}: article-body bounds not matched, processed whole doc`);
  }

  // --- 2. TOC (top-level h2s, >=3) injected right after .article-body opening ---
  const top = toc.filter((t) => t.depth === 2);
  if (top.length >= 3) {
    const lis = top.map((t) => `          <li><a href="#${t.id}">${t.text.replace(/&/g, "&amp;").replace(/</g, "&lt;")}</a></li>`).join("\n");
    const tocHtml = `\n      <nav class="post-toc" aria-label="Table of contents">\n        <p class="toc-label">On this page</p>\n        <ul>\n${lis}\n        </ul>\n      </nav>\n`;
    html = html.replace(/<div class="article-body">/, `<div class="article-body">${tocHtml}`);
  }

  // --- 3. Visible breadcrumb before the article header ---
  const crumbs = `      <nav class="crumbs" aria-label="Breadcrumb"><a href="/">Home</a><span class="sep">/</span><a href="/blog">Blog</a></nav>\n`;
  html = html.replace(/(\s*)<header class="article-header">/, `$1${crumbs}    <header class="article-header">`);

  // --- 4. BreadcrumbList JSON-LD (additive) ---
  const headlineM = html.match(/"headline":\s*"((?:[^"\\]|\\.)*)"/);
  const urlM = html.match(/<link rel="canonical" href="([^"]+)"/) || html.match(/"url":\s*"((?:[^"\\]|\\.)*)"/);
  if (headlineM && urlM) {
    const headline = headlineM[1];
    const url = urlM[1];
    const ld = `  <script type="application/ld+json">
  {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    "itemListElement": [
      { "@type": "ListItem", "position": 1, "name": "Home", "item": "https://astraedus.dev/" },
      { "@type": "ListItem", "position": 2, "name": "Blog", "item": "https://astraedus.dev/blog" },
      { "@type": "ListItem", "position": 3, "name": "${headline}", "item": "${url}" }
    ]
  }
  </script>`;
    html = html.replace(/<\/head>/, `${ld}\n${CSS}\n${MARKER}\n</head>`);
  } else {
    html = html.replace(/<\/head>/, `${CSS}\n${MARKER}\n</head>`);
    console.log(`  ! ${slug}: no headline/url for breadcrumb schema (CSS only)`);
  }

  fs.writeFileSync(file, html);
  console.log(`  + ${slug}  (h2/h3=${toc.length}, toc=${top.length >= 3 ? "yes" : "no"})`);
  done++;
}
console.log(`\nDone. ${done} enhanced, ${skipped} skipped.`);
