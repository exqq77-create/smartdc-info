#!/usr/bin/env python3
"""Pre-publish check for one new journal post.

usage:
  python3 -I check_post.py <repo_dir> <slug> [--min-chars N] [--source-chars N]
                           [--others <repo_dir> ...] [--json]

Checks (FAIL = must fix before publish, WARN = review by hand):
  1. backlink paragraph: exactly one <p class="backlink">, href = this site's own
     domain only, keyword text matches the fixed mapping; no other managed domain
     anywhere in the file.
  2. body length: body_chars >= min-chars (default 1500) and, when --source-chars is
     given, >= 90% of the source body length (cap 2500) so the post is not a cut-down
     version of its source.
  3. duplicates: exact body hash against every post in this repo and in --others;
     title trigram similarity >= 0.6 (FAIL) / >= 0.45 (WARN); description
     similarity >= 0.7 (FAIL); 3+ of 5 h2 headings identical to one existing post
     (FAIL); first-paragraph similarity >= 0.6 (WARN).
  4. leftovers & banned phrases: production notes (#...#, ★장소추가, 이미지날리기,
     TODO, <인용구>), images in body (<img/<figure>), guarantee/superlative wording.
  5. structure: 5 h2 sections with id s1..s5, toc present, title == og:title,
     canonical points at this site + slug.
Exit code 1 when any FAIL. Prints a human report, or JSON with --json.
"""
import sys, re, json, html, hashlib, argparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from post_index import index_post, body_of, strip_tags  # noqa: E402

DOMAINS = {
    "shidaehospitalinfo": ("https://shidaehospitalinfo.co.kr/", ["안양정형외과"]),
    "myseasonclinic-ulsaninfo": ("https://myseasonclinic-ulsaninfo.co.kr/", ["울산피부과"]),
    "daegu365mc-info": ("https://daegu365mc-info.co.kr/", ["대구다이어트병원"]),
    "sarangi-info": ("https://sarangi-info.co.kr/", ["난임병원"]),
    "mediwoman-info": ("https://mediwoman-info.co.kr/", ["부산유방외과", "부산임신중절"]),
    "smartdc-info": ("https://smartdc-info.co.kr/", ["구미치과", "구미임플란트"]),
    "keundental-info": ("https://keundental-info.co.kr/", ["양천구치과", "강서구치과"]),
    "mppm-info": ("https://mppm-info.co.kr/", ["대구월성동피부과", "대구온다리프팅", "대구세르프"]),
    "newclinic-info": ("https://newclinic-info.co.kr/", ["경성대피부과", "수영구피부과", "남천동피부과", "부산대상포진"]),
    "innodoc-info": ("https://innodoc-info.co.kr/", ["해운대피부과", "부산쥬브젠", "부산세르프", "부산볼뉴머"]),
    "kosleep-info": ("https://kosleep-info.co.kr/", ["수면장애", "수면다원검사", "불면증", "기면증", "수면클리닉"]),
    "shinsegaelasik-info": ("https://shinsegaelasik-info.co.kr/", ["광주안과", "광주스마일라식", "광주라식", "광주라섹", "광주백내장"]),
}
BANNED = ["100%", "완치", "보장", "최고의", "유일한", "부작용 없", "부작용이 없", "확실히 효과", "무조건",
          "1위", "최저가", "가장 저렴", "절대", "영구적", "완벽", "검증된 효과", "입소문", "후기에서"]
LEFTOVER = [r"#[^#\n]{2,40}#", r"★장소추가", r"이미지날리기", r"\bTODO\b", r"<인용구>", r"<소제목>", r"\*원장작성", r"원장작성"]

def trigrams(s):
    s = re.sub(r"\s+", "", s)
    return {s[i:i+3] for i in range(max(0, len(s) - 2))}

def jacc(a, b):
    A, B = trigrams(a), trigrams(b)
    return len(A & B) / len(A | B) if A and B else 0.0

def first_para(doc):
    b = body_of(doc) or ""
    m = re.search(r"<h2[^>]*>.*?</h2>\s*<p>(.*?)</p>", b, re.S)
    return html.unescape(re.sub(r"<[^>]+>", "", m.group(1))) if m else ""

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("repo"); ap.add_argument("slug")
    ap.add_argument("--min-chars", type=int, default=1500)
    ap.add_argument("--source-chars", type=int, default=0)
    ap.add_argument("--others", nargs="*", default=[])
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    repo = Path(a.repo).resolve(); site = repo.name
    path = repo / "journal" / a.slug / "index.html"
    fails, warns = [], []
    if not path.exists():
        print(f"FAIL: {path} not found"); sys.exit(1)
    doc = path.read_text(encoding="utf-8", errors="replace")
    me = index_post(path)

    # 1. backlink
    own, kws = DOMAINS[site]
    bl = re.findall(r'<p class="backlink".*?</p>', doc, re.S)
    if len(bl) != 1:
        fails.append(f"backlink paragraph count = {len(bl)} (must be 1)")
    else:
        hrefs = re.findall(r'href="([^"]+)"', bl[0])
        if not hrefs or any(h != own for h in hrefs):
            fails.append(f"backlink href must be {own}; got {hrefs}")
        texts = re.findall(r'<a [^>]*>(.*?)</a>', bl[0])
        if sorted(texts) != sorted(kws):
            fails.append(f"backlink keyword text must be {kws}; got {texts}")
    for other, (dom, _) in DOMAINS.items():
        if other != site and dom.rstrip("/").split("//")[1] in doc:
            fails.append(f"foreign managed domain present: {dom}")

    # 2. length
    if me["body_chars"] < a.min_chars:
        fails.append(f"body_chars {me['body_chars']} < min {a.min_chars}")
    if a.source_chars:
        need = min(int(a.source_chars * 0.9), 2500)
        if me["body_chars"] < need:
            fails.append(f"body_chars {me['body_chars']} < 90% of source ({a.source_chars}) → need ≥ {need}")

    # 3. duplicates
    corpus = []
    for r in [repo] + [Path(o).resolve() for o in a.others]:
        for p in sorted((r / "journal").glob("*/index.html")):
            if p == path: continue
            ix = index_post(p); ix["site"] = r.name; ix["fp"] = first_para(p.read_text(encoding="utf-8", errors="replace"))
            corpus.append(ix)
    myfp = first_para(doc)
    for ix in corpus:
        tag = f"{ix['site']}/{ix['slug']}"
        if ix["body_sha16"] == me["body_sha16"]:
            fails.append(f"EXACT duplicate body of {tag}")
        ts = jacc(me["title"], ix["title"])
        if ts >= 0.6: fails.append(f"title too similar ({ts:.2f}) to {tag}: {ix['title']}")
        elif ts >= 0.45: warns.append(f"title similar ({ts:.2f}) to {tag}: {ix['title']}")
        ds = jacc(me["description"], ix["description"])
        if ds >= 0.7: fails.append(f"description too similar ({ds:.2f}) to {tag}")
        same_h2 = len(set(me["h2"]) & set(ix["h2"]))
        if same_h2 >= 3: fails.append(f"{same_h2} identical h2 headings with {tag}")
        elif same_h2 == 2: warns.append(f"2 identical h2 headings with {tag}")
        if myfp and ix["fp"]:
            fs = jacc(myfp, ix["fp"])
            if fs >= 0.6: warns.append(f"first paragraph similar ({fs:.2f}) to {tag}")

    # 4. leftovers / banned / images
    body = body_of(doc) or ""
    btxt = strip_tags(body)
    for pat in LEFTOVER:
        if re.search(pat, btxt): fails.append(f"leftover production note matches /{pat}/")
    if re.search(r"<img|<figure", body): fails.append("image tag inside body (text-only rule)")
    for w in BANNED:
        if w in btxt: warns.append(f"banned/risky phrase: '{w}'")

    # 4b. SEO length (네이버 서치어드바이저 권고: <title> 40자, description 80자)
    tt = re.search(r"<title>(.*?)</title>", doc, re.S); tt = html.unescape(tt.group(1)).strip() if tt else ""
    if len(tt) > 40: fails.append(f"<title> {len(tt)}자 > 40 (제목을 40자 이내로, 또는 <title>만 줄이기)")
    if len(me["description"]) > 80: fails.append(f"description {len(me['description'])}자 > 80")
    ogt = re.search(r'og:title" content="(.*?)"', doc); ogt = html.unescape(ogt.group(1)).strip() if ogt else ""
    if len(ogt) > 40: fails.append(f"og:title {len(ogt)}자 > 40")
    ogd = re.search(r'og:description" content="(.*?)"', doc); ogd = html.unescape(ogd.group(1)).strip() if ogd else ""
    if len(ogd) > 80: fails.append(f"og:description {len(ogd)}자 > 80")

    # 5. structure
    ids = re.findall(r'<h2 id="(s\d)"', body)
    if ids != ["s1", "s2", "s3", "s4", "s5"]: fails.append(f"h2 ids = {ids}, expected s1..s5")
    if '<nav class="toc"' not in doc: fails.append("toc nav missing")
    og = re.search(r'property="og:title" content="(.*?)"', doc)
    if not og or html.unescape(og.group(1)).strip() not in (tt, me["title"]): fails.append("og:title != <title>")
    canon = re.search(r'<link rel="canonical" href="([^"]+)"', doc)
    if not canon or canon.group(1) != f"{own}journal/{a.slug}/": fails.append(f"canonical wrong: {canon.group(1) if canon else None}")
    if not me["has_article"]: fails.append("article block missing")

    rep = {"site": site, "slug": a.slug, "title": me["title"], "body_chars": me["body_chars"],
           "compared_posts": len(corpus), "compared_sites": sorted({ix["site"] for ix in corpus} | {site}),
           "fails": fails, "warns": warns, "result": "FAIL" if fails else "PASS"}
    if a.json: print(json.dumps(rep, ensure_ascii=False, indent=1))
    else:
        print(f"[{rep['result']}] {site}/{a.slug} — {me['body_chars']}자, compared {len(corpus)} posts across {len(rep['compared_sites'])} sites")
        for f in fails: print("  FAIL:", f)
        for w in warns: print("  WARN:", w)
    sys.exit(1 if fails else 0)

if __name__ == "__main__":
    main()
