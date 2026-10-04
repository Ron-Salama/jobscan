# -*- coding: utf-8 -*-
"""GotFriends (gotfriends.co.il) - Israeli tech recruiting-agency job boards.

HTML scraper over a curated set of software/devops/automation boards; the JD is on
the listing card.
"""

import html
import re
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from ._common import _is_student_title


def src_gotfriends():
    """GotFriends (gotfriends.co.il) - Israeli tech recruiting-agency job boards.
    Scrapes the newest listing pages of a curated set of software/devops/automation
    subcat boards. Cards carry title, numeric job id, location and full desc+requirements
    inline, so no per-job detail fetch is needed. Company is masked by the agency ("").
    Returns list[dict] with the fixed adapter schema. Never raises."""
    BASE = "https://www.gotfriends.co.il"
    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
    HDRS = {"User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "he-IL,he;q=0.9,en;q=0.8"}
    # (category, subcat) boards, newest-first. The target lanes first (QA/automation, .NET,
    # backend, full-stack, python), then the rest. Every board gets its own PAGES budget
    # (no global cap: the old CAP=120 stopped after ~5 of 14 boards on every run).
    BOARDS = [
        ("qa", "automation-developer"),
        ("software", "net-developer"), ("software", "backend-developer"),
        ("software", "full-stack-developer"), ("software", "python-developer"),
        ("software", "java-developer"), ("software", "frontend-developer"),
        ("software", "nodejs-developer"), ("software", "react-developer"),
        ("software", "go-developer"), ("software", "data-engineer"),
        ("software", "ai-engineer"),
        ("system", "devops-positions"), ("system", "sre"),
    ]
    PAGES = 3          # newest N listing pages per board (page 1 = newest)

    SR = ["senior", "sr.", "sr ", " lead", "lead ", "principal", "staff", "architect",
          "team lead", "teamlead", "team leader", "head of", "manager", "expert", "vp ",
          "director", "בכיר", "ראש צוות",
          "מנהל", "מוביל", "ארכיטקט"]
    # 'graduate' / 'בוגר' (graduate) are junior signals, never student (config.JUNIOR_MARK)
    JR = ["junior", "jr.", "jr ", "entry level", "entry-level", "graduate",
          "ג'וניור", "זוטר", "מתחיל", "בוגר"]

    # tech keyword -> match regex (case-insensitive)
    TECH_RAW = [
        ("Java", r"\bjava\b"), ("Python", r"\bpython\b"), ("C++", r"c\+\+"),
        ("C#", r"c#|c\s?sharp"), (".NET", r"\.net\b|dotnet"), ("Go", r"\bgo(?:lang)?\b"),
        ("Rust", r"\brust\b"), ("Kotlin", r"\bkotlin\b"), ("Scala", r"\bscala\b"),
        ("Ruby", r"\bruby\b"), ("PHP", r"\bphp\b"), ("JavaScript", r"\bjavascript\b"),
        ("TypeScript", r"\btypescript\b"), ("Node.js", r"\bnode(?:\.?js)?\b"),
        ("React", r"\breact\b"), ("Angular", r"\bangular\b"), ("Vue", r"\bvue\b"),
        ("Spring", r"\bspring\b"), ("Django", r"\bdjango\b"), ("Flask", r"\bflask\b"),
        ("FastAPI", r"\bfastapi\b"), ("Kafka", r"\bkafka\b"), ("Spark", r"\bspark\b"),
        ("Flink", r"\bflink\b"), ("Kubernetes", r"\bkubernetes\b|\bk8s\b"),
        ("Docker", r"\bdocker\b"), ("AWS", r"\baws\b"), ("Azure", r"\bazure\b"),
        ("GCP", r"\bgcp\b|google cloud"), ("Linux", r"\blinux\b"), ("SQL", r"\bsql\b"),
        ("NoSQL", r"\bnosql\b"), ("MongoDB", r"\bmongo(?:db)?\b"),
        ("PostgreSQL", r"\bpostgres(?:ql)?\b"), ("MySQL", r"\bmysql\b"),
        ("Redis", r"\bredis\b"), ("GraphQL", r"\bgraphql\b"), ("gRPC", r"\bgrpc\b"),
        ("Microservices", r"\bmicroservices?\b"), ("CI/CD", r"ci/cd|ci-cd"),
        ("Terraform", r"\bterraform\b"), ("Ansible", r"\bansible\b"),
        ("Jenkins", r"\bjenkins\b"), ("Elasticsearch", r"\belastic(?:search)?\b"),
        ("OpenSearch", r"\bopensearch\b"), ("Helm", r"\bhelm\b"),
        ("Selenium", r"\bselenium\b"), ("Cypress", r"\bcypress\b"),
        ("Playwright", r"\bplaywright\b"), ("Appium", r"\bappium\b"),
        ("Prometheus", r"\bprometheus\b"), ("Grafana", r"\bgrafana\b"),
    ]
    TECH = [(name, re.compile(pat, re.I)) for name, pat in TECH_RAW]

    def clean(s):
        return re.sub(r"\s+", " ", html.unescape(s or "")).strip()

    def level_of(title):
        t = (title or "").lower()
        if _is_student_title(title): return "student"
        if any(m in t for m in JR): return "junior"
        if any(m in t for m in SR): return "senior"
        return ""

    def years_of(text):
        t = (text or "").lower()
        ymin = ymax = None
        yword = r"(?:years|year|yrs|שנ)"  # english + Hebrew shin-nun (shanim/shnot)
        for m in re.finditer(r"(\d{1,2})\s*[-–—]\s*(\d{1,2})\s*\+?\s*" + yword, t):
            a, b = int(m.group(1)), int(m.group(2))
            lo, hi = min(a, b), max(a, b)
            ymin = lo if ymin is None else min(ymin, lo)
            ymax = hi if ymax is None else max(ymax, hi)
        for m in re.finditer(r"(?<![\d\-–—])(\d{1,2})\s*\+?\s*" + yword, t):
            v = int(m.group(1))
            if v > 40:
                continue
            ymin = v if ymin is None else min(ymin, v)
        return ymin, ymax

    def tech_of(text):
        return [name for name, rx in TECH if rx.search(text or "")]

    def parse_page(content, cat, subcat, seen, out, page_ids=None):
        soup = BeautifulSoup(content, "lxml")
        cards = soup.select("div.list.panel div.item") or soup.select("div.item")
        pat = re.compile(r"/jobslobby/[a-z0-9\-]+/[a-z0-9\-]+/(\d+)/?")
        added = 0
        for it in cards:
            try:
                a = it.select_one("a[href*='/jobslobby/']")
                if not a:
                    continue
                href = a.get("href", "")
                m = pat.search(href)
                if not m:
                    continue
                sid = m.group(1)
                if page_ids is not None:
                    page_ids.append(sid)
                if sid in seen:
                    continue
                title_el = it.select_one("h2.title") or it.select_one(".title") or a
                title = clean(title_el.get_text(" ", strip=True))
                # some cards carry a numeric placeholder as their title (site-side
                # data glitch) -> fall back to the board's subcat so the caller can
                # still classify the role by title keywords.
                if not title or re.fullmatch(r"[\d\W]+", title):
                    title = subcat.replace("-", " ").title()
                loc_el = it.select_one("span.info-data")
                city = clean(loc_el.get_text(" ", strip=True)) if loc_el else ""
                desc = clean("  ".join(d.get_text(" ", strip=True)
                                       for d in it.select("div.desc")))[:1200]
                blob = title + "  " + desc
                ymin, ymax = years_of(desc)
                seen.add(sid)
                out.append({
                    "source": "gotfriends",
                    "sid": sid,
                    "title": title,
                    "company": "",              # agency masks the employer
                    "city": city,
                    "url": urljoin(BASE, href),
                    "level": level_of(title),
                    "years_min": ymin,
                    "years_max": ymax,
                    "tech": tech_of(blob),
                    "desc": desc,
                    "active": True,
                })
                added += 1
            except Exception:
                continue
        return added

    out, seen = [], set()
    per_board = {}
    try:
        sess = requests.Session()
        sess.headers.update(HDRS)
    except Exception:
        sess = requests
    for cat, subcat in BOARDS:
        n_board = 0
        prev_ids = None
        for page in range(1, PAGES + 1):
            url = "%s/jobslobby/%s/%s/" % (BASE, cat, subcat)
            if page > 1:
                url += "?page=%d" % page
            page_ids = []
            try:
                r = sess.get(url, timeout=30)
                if r.status_code != 200:
                    break
                added = parse_page(r.content, cat, subcat, seen, out, page_ids)
            except Exception:
                break
            n_board += added
            # stop on an empty page or a repeat of the previous one (out-of-range page).
            # A page of only already-seen ids (shared with an earlier board) keeps paging.
            if not page_ids or page_ids == prev_ids:
                break
            prev_ids = page_ids
            time.sleep(0.35)
        per_board[subcat] = n_board
    try:
        print("    gotfriends per-board:", per_board)
    except Exception:
        pass
    return out
