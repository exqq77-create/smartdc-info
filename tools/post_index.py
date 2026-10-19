#!/usr/bin/env python3
"""Index every published journal post of a site clone (main branch working tree).

usage: python3 -I post_index.py <repo_dir> [out.json]
Prints/saves: slug, title, description, h2 headings, body_chars, body_sha16.
Body = text inside <article class="section article">, excluding nav/footer,
ctas, category line, backlink paragraph, related and prevnext blocks.
"""
import sys, re, json, hashlib, html
from pathlib import Path

def strip_tags(s):
    s = re.sub(r"<script.*?</script>|<style.*?</style>", "", s, flags=re.S)
    s = re.sub(r"<[^>]+>", " ", s)
    return html.unescape(s)

def body_of(doc):
    m = re.search(r'<article class="section article">(.*?)</article>', doc, re.S)
    if not m:
        return None
    a = m.group(1)
    a = re.sub(r'<div class="ctas">.*?</div>', "", a, flags=re.S)
    a = re.sub(r'<p>카테고리 .*?</p>', "", a, flags=re.S)
    a = re.sub(r'<p class="backlink".*?</p>', "", a, flags=re.S)
    a = re.sub(r'<section class="related">.*?</section>', "", a, flags=re.S)
    a = re.sub(r'<nav class="prevnext".*?</nav>', "", a, flags=re.S)
    a = re.sub(r'<nav class="toc".*?</nav>', "", a, flags=re.S)
    return a

def index_post(path):
    doc = path.read_text(encoding="utf-8", errors="replace")
    title = re.search(r"<title>(.*?)</title>", doc, re.S)
    title = html.unescape(title.group(1)).split("|")[0].strip() if title else ""
    desc = re.search(r'<meta name="description" content="(.*?)"', doc)
    desc = html.unescape(desc.group(1)) if desc else ""
    date = re.search(r'article:published_time" content="([^"]+)"', doc)
    body = body_of(doc)
    h2s = [html.unescape(re.sub(r"<[^>]+>", "", h)).strip() for h in re.findall(r'<h2 id="s\d">(.*?)</h2>', body or "", re.S)]
    text = re.sub(r"\s+", "", strip_tags(body or ""))
    return {
        "slug": path.parent.name,
        "title": title,
        "description": desc,
        "date": date.group(1) if date else "",
        "h2": h2s,
        "body_chars": len(text),
        "body_sha16": hashlib.sha256(text.encode()).hexdigest()[:16],
        "has_article": body is not None,
    }

def main():
    repo = Path(sys.argv[1])
    posts = [index_post(p) for p in sorted((repo / "journal").glob("*/index.html"))]
    out = {"site": repo.name, "count": len(posts), "posts": posts}
    if len(sys.argv) > 2:
        Path(sys.argv[2]).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    else:
        print(json.dumps(out, ensure_ascii=False, indent=1))

if __name__ == "__main__":
    main()
