#!/usr/bin/env python3
"""건강정보 글 1편을 사이트에 추가하고 목록/페이지네이션/RSS/사이트맵/치료 페이지/이전·다음을 갱신한다.
사용: python3 -I publish_post.py <repo> <spec.json> [--selftest]
spec.json: {"prefix","title","summary","sections":[{"h","p":[...]}x5],"checklist":[3개]}
"""
import re, sys, os, json, glob, html
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))
WD = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


def rd(p):
    return open(p, encoding='utf8').read()


def wr(p, t):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, 'w', encoding='utf8').write(t)


ITEM_RE = re.compile(r'<li class="post-item">.*?</li>', re.S)


def pager_html(base, cur, last, indent_tail='    '):
    """base: '/blog/' 또는 '/blog/topic/x/'"""
    def href(n):
        return base if n == 1 else f'{base}page/{n}/'
    show = {1, last, cur - 1, cur, cur + 1}
    if cur <= 2:
        show |= set(range(1, min(last, max(3, cur + 2)) + 1))
    show = sorted(n for n in show if 1 <= n <= last)
    parts = []
    prev = None
    for n in show:
        if prev is not None and n - prev > 1:
            parts.append('<span>…</span>')
        if n == cur:
            parts.append(f'<span aria-current="page">{n}</span>')
        else:
            parts.append(f'<a href="{href(n)}">{n}</a>')
        prev = n
    lines = []
    if cur > 1:
        lines.append(f'      <a href="{href(cur-1)}">← 이전</a>')
    lines.append('      ' + ''.join(parts))
    if cur < last:
        lines.append(f'      <a href="{href(cur+1)}">다음 →</a>')
    return '<nav class="pager" aria-label="페이지 이동">\n' + '\n'.join(lines) + '\n' + indent_tail + '</nav>'


def set_pager(t, base, cur, last):
    m = re.search(r'<nav class="pager"[^>]*>.*?</nav>', t, re.S)
    if not m:
        return t
    return t[:m.start()] + pager_html(base, cur, last) + t[m.end():]


def split_list(t):
    """ul.post-list 안의 (앞, 항목들, 구분자, 뒤)"""
    m = re.search(r'(<ul class="post-list">)(.*?)(</ul>)', t, re.S)
    inner = m.group(2)
    items = ITEM_RE.findall(inner)
    first = inner.index(items[0]) if items else len(inner)
    lead = inner[:first]
    trail = inner[inner.rindex(items[-1]) + len(items[-1]):] if items else ''
    sep = '\n      \n      '
    if len(items) >= 2:
        a = inner.index(items[0]) + len(items[0])
        b = inner.index(items[1], a)
        sep = inner[a:b]
    return m, lead, items, sep, trail


def put_list(t, items, lead, sep, trail):
    m = re.search(r'(<ul class="post-list">)(.*?)(</ul>)', t, re.S)
    return t[:m.start(2)] + lead + sep.join(items) + trail + t[m.end(2):]


def page_files(root, base_dir):
    """base_dir: 'blog' 또는 'blog/topic/x'. 반환: [(n, path)]"""
    out = [(1, os.path.join(root, base_dir, 'index.html'))]
    pdir = os.path.join(root, base_dir, 'page')
    if os.path.isdir(pdir):
        ns = sorted(int(d) for d in os.listdir(pdir) if d.isdigit())
        out += [(n, os.path.join(pdir, str(n), 'index.html')) for n in ns]
    return out


def make_new_page(prev_text, base, old_n, new_n, root_url_path):
    t = prev_text
    if old_n == 1:
        # index -> page 2 (topic)
        t = t.replace(f'{base}"', f'{base}page/{new_n}/"')
        t = re.sub(r'(건강정보)( \|)', rf'\1 {new_n}페이지\2', t, count=0)
    else:
        t = t.replace(f'/page/{old_n}/', f'/page/{new_n}/').replace(f'{old_n}페이지', f'{new_n}페이지')
    return t


def cascade(root, base_dir, base_url, new_item, size=None, self_check=False):
    files = page_files(root, base_dir)
    texts = {n: rd(p) for n, p in files}
    parsed = {n: split_list(texts[n]) for n in texts}
    P = size or len(parsed[1][2])
    # 페이지 크기: 1페이지가 가득 찬 경우만 신뢰(항목수)
    lists = [list(parsed[n][2]) for n, _ in files]
    if self_check:
        return lists, P
    lists[0].insert(0, new_item)
    for i in range(len(lists)):
        if len(lists[i]) > P:
            over = lists[i].pop()
            if i + 1 == len(lists):
                lists.append([])
            lists[i + 1].insert(0, over)
    last = len(lists)
    changed = {}
    for i, items in enumerate(lists):
        n = i + 1
        if n <= len(files):
            path = files[i][1]
            t = texts[n]
            m, lead, _, sep, trail = parsed[n]
        else:
            path = os.path.join(root, base_dir, 'page', str(n), 'index.html')
            t = make_new_page(texts[n - 1], base_url, n - 1, n, None)
            m, lead, _, sep, trail = parsed[len(files)]
        t = put_list(t, items, lead, sep, trail)
        t = set_pager(t, base_url, n, last)
        changed[path] = t
    return changed


def load_posts(root):
    posts = {}
    for d in os.listdir(os.path.join(root, 'journal')):
        f = os.path.join(root, 'journal', d, 'index.html')
        if not os.path.isfile(f):
            continue
        t = rd(f)
        h1 = re.search(r'<h1>(.*?)</h1>', t, re.S).group(1)
        posts[d] = dict(slug=d, title=html.unescape(h1), text=t)
    return posts


def main():
    root = os.path.abspath(sys.argv[1])
    spec = None if '--selftest' in sys.argv else json.load(open(sys.argv[2], encoding='utf8'))
    selftest = '--selftest' in sys.argv

    if selftest:
        bad = 0
        for base_dir, base_url in [('blog', '/blog/')] + [(f'blog/topic/{d}', f'/blog/topic/{d}/') for d in sorted(os.listdir(os.path.join(root, 'blog/topic')))]:
            files = page_files(root, base_dir)
            last = len(files)
            for n, p in files:
                t = rd(p)
                if set_pager(t, base_url, n, last) != t:
                    bad += 1
                    print('PAGER MISMATCH', p)
        print('selftest pager mismatches:', bad)
        return

    prefix = spec['prefix']
    now = datetime.now(KST)
    iso = now.strftime('%Y-%m-%d')
    ko_date = f'{now.year}년 {now.month}월 {now.day}일'
    posts = load_posts(root)
    same = sorted((s for s in posts if re.fullmatch(re.escape(prefix) + r'-\d+', s)), key=lambda s: int(s.rsplit('-', 1)[1]))
    tmpl_slug = same[-1]
    num = int(tmpl_slug.rsplit('-', 1)[1]) + 1
    slug = f'{prefix}-{num:02d}'
    assert slug not in posts
    T = posts[tmpl_slug]['text']
    old_title = posts[tmpl_slug]['title']
    old_sum = re.search(r'<p class="summary">(.*?)</p>', T, re.S).group(1)
    title, summary = spec['title'], spec['summary']
    old_iso = re.search(r'<time datetime="([^"]+)">', T).group(1)
    old_ko = re.search(r'<time datetime="[^"]+">([^<]+)</time>', T).group(1)

    t = T
    t = t.replace(old_title, title).replace(old_sum, summary)
    t = t.replace(f'/journal/{tmpl_slug}/', f'/journal/{slug}/')
    t = re.sub(r'<title>.*?</title>', lambda m: f'<title>{title}</title>', t, count=1, flags=re.S)
    t = re.sub(r'(<meta property="og:title" content=")[^"]*(")', lambda m: m.group(1) + title + m.group(2), t, count=1)
    t = re.sub(r'(<meta name="twitter:title" content=")[^"]*(")', lambda m: m.group(1) + title + m.group(2), t, count=1)
    t = t.replace(old_iso, iso).replace(old_ko, ko_date)
    # toc
    secs = spec['sections']
    toc = ''.join(f'<li><a href="#s{i+1}">{s["h"]}</a></li>' for i, s in enumerate(secs))
    t = re.sub(r'(<nav class="toc"[^>]*><strong>[^<]*</strong><ol>).*?(</ol></nav>)', lambda m: m.group(1) + toc + m.group(2), t, flags=re.S)
    body = '\n'.join(f'<h2 id="s{i+1}">{s["h"]}</h2>\n' + '\n'.join(f'<p>{p}</p>' for p in s['p']) for i, s in enumerate(secs))
    t = re.sub(r'(<div class="body">).*?(</div>\s*<h2>상담 전 확인할 내용</h2>)', lambda m: m.group(1) + body + m.group(2), t, flags=re.S)
    assert body in t, 'body not replaced'
    cl = ''.join(f'<li>{x}</li>' for x in spec['checklist'])
    t = re.sub(r'(<h2>상담 전 확인할 내용</h2>\s*<ul>).*?(</ul>)', lambda m: m.group(1) + cl + m.group(2), t, count=1, flags=re.S)
    if spec.get('risk'):
        t = re.sub(r'(<div class="risk"><h2>위험과 주의사항</h2><p>).*?(</p></div>)', lambda m: m.group(1) + spec['risk'] + m.group(2), t, flags=re.S)
    # prev/next: 사이트 전체에서 next 가 비어 있는 글(= 가장 최신)
    prev_slug = re.search(r'<li class="post-item">\s*<a href="/journal/([^/]+)/"', rd(os.path.join(root, 'blog/index.html'))).group(1)
    assert re.search(r'class="prevnext".*?<span></span>\s*</nav>', posts[prev_slug]['text'], re.S), 'latest post has next'
    assert prev_slug, 'prev not found'
    pt = posts[prev_slug]['title']
    pn = (f'<nav class="prevnext" aria-label="이전·다음 글">\n      <a class="prev" href="/journal/{prev_slug}/"><span>← 이전 글</span>{pt}</a>\n      <span></span>\n    </nav>')
    t = re.sub(r'<nav class="prevnext".*?</nav>', lambda m: pn, t, flags=re.S)
    rel_slugs = [slug] + same[::-1][:2]
    rel = '<ul>' + ''.join(f'<li><a href="/journal/{s}/">{title if s == slug else posts[s]["title"]}</a></li>' for s in rel_slugs) + '</ul>'
    t = re.sub(r'(<section class="related">\s*<h2>[^<]*</h2>\s*)<ul>.*?</ul>', lambda m: m.group(1) + rel, t, flags=re.S)
    out = {}
    out[os.path.join(root, 'journal', slug, 'index.html')] = t
    # 이전 글의 next
    pp = posts[prev_slug]['text']
    nx = f'<a class="next" href="/journal/{slug}/"><span>다음 글 →</span>{title}</a>'
    pp2 = re.sub(r'(class="prevnext".*?)<span></span>(\s*</nav>)', lambda m: m.group(1) + nx + m.group(2), pp, count=1, flags=re.S)
    assert pp2 != pp
    out[os.path.join(root, 'journal', prev_slug, 'index.html')] = pp2

    # 카테고리 이름
    cat = re.search(r'<p>카테고리 <a href="[^"]*">([^<]*)</a></p>', T).group(1)

    # 목록 항목 템플릿 (같은 접두어 최신 글의 항목)
    tp1 = rd(os.path.join(root, f'blog/topic/{prefix}/index.html'))
    items = ITEM_RE.findall(tp1)
    it = next(x for x in items if f'/journal/{tmpl_slug}/' in x)
    it = it.replace(f'/journal/{tmpl_slug}/', f'/journal/{slug}/')
    it = re.sub(r'(<h2><a href="[^"]*">).*?(</a></h2>)', lambda m: m.group(1) + title + m.group(2), it, flags=re.S)
    it = re.sub(r'<time datetime="[^"]*">[^<]*</time>', f'<time datetime="{iso}">{ko_date}</time>', it)
    it = re.sub(r'(<div class="meta">.*?</div>\s*<p>).*?(</p>)', lambda m: m.group(1) + summary + m.group(2), it, count=1, flags=re.S)
    assert slug in it and title in it
    # blog 전체
    out.update(cascade(root, 'blog', '/blog/', it))
    out.update(cascade(root, f'blog/topic/{prefix}', f'/blog/topic/{prefix}/', it))
    # 전체 목록 페이지수 변경 시 blog/index 의 pager 가 다른 페이지에도 반영되도록(마지막 페이지 번호) 모든 blog 페이지 pager 재생성
    bl = sorted(k for k in out if '/blog/' in k and '/topic/' not in k)
    last = len(page_files(root, 'blog')) if not any(True for _ in []) else 0
    allp = {}
    for n, p in page_files(root, 'blog'):
        allp[p] = out.get(p, rd(p))
    for k in out:
        if re.search(r'/blog/page/\d+/index.html$', k) and k not in allp:
            allp[k] = out[k]
    ordered = sorted(allp, key=lambda p: (0 if p.endswith('/blog/index.html') else int(re.search(r'/page/(\d+)/', p).group(1))))
    L = len(ordered)
    for i, p in enumerate(ordered):
        out[p] = set_pager(allp[p], '/blog/', i + 1, L)
    # 토픽 pager 도 마지막 번호 반영
    tl = sorted(k for k in out if f'/blog/topic/{prefix}/' in k)
    tp = {}
    for n, p in page_files(root, f'blog/topic/{prefix}'):
        tp[p] = out.get(p, rd(p))
    for k in tl:
        tp.setdefault(k, out[k])
    tord = sorted(tp, key=lambda p: (0 if p.endswith(f'/{prefix}/index.html') else int(re.search(r'/page/(\d+)/', p).group(1))))
    for i, p in enumerate(tord):
        out[p] = set_pager(tp[p], f'/blog/topic/{prefix}/', i + 1, len(tord))

    # sitemap
    sm = rd(os.path.join(root, 'sitemap.xml'))
    dom = re.search(r'<loc>(https://[^/]+)/', sm).group(1)
    sm = sm.replace('</urlset>', f'<url><loc>{dom}/journal/{slug}/</loc><lastmod>{iso}</lastmod></url>\n</urlset>')
    out[os.path.join(root, 'sitemap.xml')] = sm
    # rss
    rss = rd(os.path.join(root, 'rss.xml'))
    pub = f'{WD[now.weekday()]}, {now.day:02d} {MON[now.month-1]} {now.year} {now:%H:%M:%S} +0900'
    body_inner = body
    item = (f'<item><title>{title}</title><link>{dom}/journal/{slug}/</link><guid isPermaLink="true">{dom}/journal/{slug}/</guid>'
            f'<pubDate>{pub}</pubDate><category>{cat}</category><description><![CDATA[<p>{summary}</p>{body_inner}]]></description></item>\n')
    k = rss.index('<item>')
    rss = rss[:k] + item + rss[k:]
    its = list(re.finditer(r'<item>.*?</item>\n?', rss, re.S))
    if len(its) > 30:
        for m in reversed(its[30:]):
            rss = rss[:m.start()] + rss[m.end():]
    out[os.path.join(root, 'rss.xml')] = rss
    # treatments
    tpath = os.path.join(root, 'treatments', prefix, 'index.html')
    if os.path.isfile(tpath):
        tt = rd(tpath)
        m = re.search(r'(공개 글 전체 목록 \()(\d+)(편\))', tt)
        if m:
            tt = tt[:m.start(2)] + str(int(m.group(2)) + 1) + tt[m.end(2):]
            tt = re.sub(r'(<ul class="all-posts">.*?)(</ul>)', lambda mm: mm.group(1) + f'<li><a href="/journal/{slug}/">{title}</a></li>' + mm.group(2), tt, count=1, flags=re.S)
            out[tpath] = tt
    for p, c in out.items():
        wr(p, c)
    print(json.dumps({'slug': slug, 'prev': prev_slug, 'files': len(out), 'date': iso, 'pub': pub}, ensure_ascii=False))


if __name__ == '__main__':
    main()
