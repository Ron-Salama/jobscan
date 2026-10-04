# -*- coding: utf-8 -*-
"""AllJobs (alljobs.co.il) - tech/software listings.

Radware-fronted: it paces slowly, sends full browser headers, and a blocked search is
logged and skipped.
"""

import re
import time
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from ._common import _is_student_title


def src_alljobs():
    """AllJobs (alljobs.co.il) tech/software listings -> list[dict].
    Radware-fronted: slow pace, full browser headers, honest on block."""
    BASE = "https://www.alljobs.co.il"
    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
    HEADERS = {
        "User-Agent": UA,
        "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
                   "image/avif,image/webp,image/apng,*/*;q=0.8"),
        "Accept-Language": "he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
    }
    # a few confirmed tech profession IDs + broad software free-text queries.
    # (label, query, free-text term or None). The free-text parameter is `freetxt=`:
    # AllJobs silently ignores `freetext=` and returns its generic feed (audit BUG 4).
    SEARCHES = [
        ("AI Engineer",   "position=2006", None),
        ("AI Developer",  "position=2004", None),
        ("QA Automation", "position=2011", None),
        ("מפתח",          "freetxt=" + quote(u"מפתח"), u"מפתח"),   # "developer" (Hebrew)
        ("Python",        "freetxt=Python", "Python"),
        ("DevOps",        "freetxt=DevOps", "DevOps"),
        ("Full Stack",    "freetxt=" + quote("Full Stack"), "Full Stack"),
        ("Embedded",      "freetxt=Embedded", "Embedded"),
    ]
    MAX_PAGES = 4          # newest pages PER SEARCH (no global cap -> every search runs)
    TECH_TERMS = [
        "python", "java", "javascript", "typescript", "node", "react", "angular", "vue",
        "c#", ".net", "c++", "go", "golang", "rust", "php", "ruby", "scala",
        "kotlin", "swift", "django", "flask", "fastapi", "spring", "express",
        "sql", "mysql", "postgres", "mongodb", "redis", "kafka", "rabbitmq", "graphql",
        "rest", "aws", "azure", "gcp", "docker", "kubernetes", "k8s", "terraform",
        "jenkins", "ci/cd", "devops", "linux", "embedded", "firmware", "rtos", "fpga",
        "verilog", "llm", "genai", "machine learning", "deep learning", "tensorflow",
        "pytorch", "selenium", "cypress", "appium", "playwright", "git", "microservices",
        "backend", "frontend", "full stack",
    ]
    # word-boundary patterns so "rest" != "interested", "java" != "javascript"
    _TECH_RX = []
    for _t in TECH_TERMS:
        if _t in ("c#", "c++", ".net", "ci/cd", "k8s"):
            _pat = {"c#": r"c#", "c++": r"c\+\+", ".net": r"\.net\b",
                    "ci/cd": r"ci\s*/\s*cd", "k8s": r"\bk8s\b"}[_t]
        else:
            _pat = r"\b" + re.escape(_t) + r"\b"
        _TECH_RX.append((_t, re.compile(_pat, re.I)))
    SENIOR = ["senior", "sr.", "sr ", "lead", "principal", "staff", "architect",
              "team lead", u"בכיר", u"ראש צוות"]
    # student is decided from the TITLE only (_is_student_title): 'intern' used to hit
    # "internal tools" / "international" in JDs, and 'מתמח' / 'הכשרה' in a JD mean
    # "specializing" / "training provided" (junior signals, not student).
    JUNIOR = ["junior", "entry level", "entry-level", "jr.", "jr ",
              u"ללא ניסיון",
              u"זוטר", u"מתחיל"]

    def _txt(el):
        return " ".join(el.get_text(" ", strip=True).split()) if el else ""

    def _years(text):
        t = text.lower()
        m = re.search(r'(\d+)\s*[-–]\s*(\d+)\s*(?:years|year|yrs|שנ)', t)
        if m:
            return int(m.group(1)), int(m.group(2))
        m = re.search(r'(\d+)\s*\+\s*(?:years|year|yrs|שנ)', t)
        if m:
            return int(m.group(1)), None
        m = re.search(r'(?:לפחות|at least|minimum|min\.?)\s*(\d+)', t)
        if m:
            return int(m.group(1)), None
        m = re.search(r'(\d+)\s*(?:years|year|yrs|שנות|שנים)', t)
        if m:
            return int(m.group(1)), None
        return None, None

    def _level(title, desc):
        blob = (title + " " + desc).lower()
        if _is_student_title(title):
            return "student"
        # SENIOR from the TITLE only ('lead' in 'leading', 'architect' in 'architectures'
        # mislabelled JD-wide); the JD still counts for junior
        if any(w in (title or "").lower() for w in SENIOR):
            return "senior"
        if any(w in blob for w in JUNIOR):
            return "junior"
        return ""

    def _tech(blob):
        found = []
        for key, rx in _TECH_RX:
            if rx.search(blob):
                found.append(key)
        return found

    def parse_card(card):
        try:
            sid = None
            a_title = (card.select_one('[class^="job-content-top-title"] a[href*="JobID="]')
                       or card.select_one('a[href*="JobID="]'))
            if a_title:
                m = re.search(r'JobID=(\d+)', a_title.get("href", ""))
                if m:
                    sid = m.group(1)
            if not sid:
                for el in [card] + card.select('[id]'):
                    eid = el.get("id", "") if hasattr(el, "get") else ""
                    m = re.search(r'(?:job-box-container|job-content-top-scvs|job-body-content)(\d+)', eid)
                    if m:
                        sid = m.group(1)
                        break
            if not sid:
                return None
            # title block covers all 4 layouts: base / -highlight / -ltr / -highlight-ltr
            tblock = card.select_one('[class^="job-content-top-title"]')
            h2 = tblock.select_one("h2") if tblock else None
            title = _txt(h2)
            if not title and a_title:
                title = (a_title.get("title") or "").split("|")[-1].strip()
            # company: T14 anchor (all layouts) -> logo alt fallback (masked for many guests)
            comp_a = None
            if tblock:
                comp_a = tblock.select_one(".T14 a") or tblock.select_one(".T14")
            company = _txt(comp_a)
            if not company:
                logo = card.select_one('[class^="job-content-top-img"] img')
                alt = (logo.get("alt") if logo else "") or ""
                # strip "דרושים ב..." / "עבודה ב..." prefixes
                alt = re.sub(r'^(?:דרושים|עבודה)\s*'
                             r'ב(?:חברת\s*)?', '', alt).strip()
                company = alt
            loc = card.select_one('[class^="job-content-top-location"]')
            city = ""
            if loc:
                links = loc.select("a")
                if links:
                    city = ", ".join(_txt(a) for a in links if _txt(a))
                else:
                    city = re.sub(r'^.*?:\s*', '', _txt(loc))
            dv = card.select_one('[class^="job-content-top-desc"]')
            desc = _txt(dv)
            blob = title + " " + desc
            ymin, ymax = _years(desc)
            return {
                "source": "alljobs",
                "sid": sid,
                "title": title,
                "company": company,
                "city": city,
                "url": "%s/Search/UploadSingle.aspx?JobID=%s" % (BASE, sid),
                "level": _level(title, desc),
                "years_min": ymin,
                "years_max": ymax,
                "tech": _tech(blob),
                "desc": desc,
                "active": True,
            }
        except Exception:
            return None

    def _squash(s):
        return re.sub(r"[\s\-_/]+", "", (s or "").lower())

    out, seen_sids = [], set()
    per_search = {}
    sess = requests.Session()
    sess.headers.update(HEADERS)
    try:
        for label, q, term in SEARCHES:
            prev_page_sids = None
            n_search = 0
            for page in range(1, MAX_PAGES + 1):
                url = "%s/SearchResultsGuest.aspx?page=%d&%s" % (BASE, page, q)
                try:
                    r = sess.get(url, timeout=30)
                except Exception:
                    break
                body = r.text or ""
                low = body.lower()
                # Radware / block detection -> back off this search
                if (r.status_code != 200 or "unauthorized request blocked" in low
                        or "radware" in low or "incapsula" in low):
                    try:
                        print("    alljobs %s: HTTP %s / blocked -> skipped" % (label, r.status_code))
                    except Exception:
                        pass
                    break
                try:
                    soup = BeautifulSoup(body, "lxml")
                except Exception:
                    break
                cards = soup.select("div.job-content-top")
                if not cards:
                    break
                page_sids, page_titles, new_here = [], [], 0
                for c in cards:
                    j = parse_card(c)
                    if not j:
                        continue
                    page_sids.append(j["sid"])
                    page_titles.append(j["title"])
                    if j["sid"] in seen_sids:
                        continue
                    seen_sids.add(j["sid"])
                    out.append(j)
                    new_here += 1
                n_search += new_here
                # sanity: a free-text search whose page 1 barely mentions the term is
                # probably the generic feed again (parameter ignored) -> say so.
                if page == 1 and term and page_titles:
                    hits = sum(1 for t in page_titles if _squash(term) in _squash(t))
                    if hits < 0.3 * len(page_titles):
                        try:
                            print("    alljobs WARN %s: only %d/%d page-1 titles contain the "
                                  "term (free-text filter ignored?)" % (label, hits, len(page_titles)))
                        except Exception:
                            pass
                # AllJobs clamps an out-of-range page to the last page: if this page
                # repeats the previous page's ids we've reached the end -> stop.
                if prev_page_sids is not None and page_sids == prev_page_sids:
                    break
                if not page_sids:
                    break
                prev_page_sids = page_sids
                time.sleep(0.4)   # polite pacing between pages
            per_search[label] = n_search
            time.sleep(0.5)       # polite pacing between searches
    except Exception:
        pass
    try:
        print("    alljobs per-search:", per_search)
    except Exception:
        pass
    return out
