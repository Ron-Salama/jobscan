# -*- coding: utf-8 -*-
"""LinkedIn guest jobs API (unofficial, rate-limited).

Entry-level boolean searches, newest first, each search with its own card budget;
the JD and LinkedIn's seniority level are read for the newest postings.
"""


def src_linkedin():
    """LinkedIn guest jobs API (UNOFFICIAL, ToS-grey, rate-limited).
    2026-09-24 rewrite: the old version read only page 1 (~10 cards) of 5 narrow keywords,
    never fetched the JD, and tagged 'graduate' titles as student. Now: the owner's own boolean
    searches, entry-level (f_E=2), newest first (sortBy=DD), paginated until empty; JD +
    LinkedIn's 'Seniority level' fetched for the newest MAX_DETAIL postings. 2026-09-25: past 48h
    (was a week), each query with its own card budget and a round-robin share of the JD reads
    (the developer lane used to starve the QA lane). Backs off on 429 and keeps whatever it has.
    Never raises."""
    import re, time, html as _html, requests, urllib.parse
    from bs4 import BeautifulSoup

    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
    HEADERS = {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.linkedin.com/jobs/search",
    }
    SEARCH = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    DETAIL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/%s"
    QUERIES = [
        # a dict = raw params for a COMPANY feed (all levels, no date filter): an employer with
        # few postings that the keyword/entry-level searches miss. First, so MAX_TOTAL never
        # starves it. 83490368 = PwC Israel's tech subsidiary (some of its roles are posted only
        # on LinkedIn; checked 2026-09-24).
        {"f_C": "83490368"},
        # the owner's own search (developer lane)
        '(developer OR "software engineer" OR programmer OR "full stack" OR backend OR frontend)',
        # the QA / automation / C# / embedded / test lane
        '("qa automation" OR "automation engineer" OR "test automation" OR "test engineer" '
        'OR embedded OR firmware OR "c#" OR ".net" OR validation OR "integration engineer")',
    ]
    # 2026-09-25: every query has its OWN card budget. With one shared MAX_TOTAL=600 the developer
    # lane filled it alone on every run (source_stats last=604), so the QA / automation / C# /
    # embedded lane - the profile's core - never ran (~200 unique entry-level roles a week unseen). The
    # window is 48h, not a week: scans run several times a day (worst measured gap ~7h), so two
    # days covers the gaps with margin and keeps each lane far below its budget.
    WINDOW = "r172800"      # f_TPR in seconds: past 48h
    MAX_PAGES = 50          # per keyword query: 10 cards per call -> up to 500 each (dev lane, 48h: ~370)
    FEED_PAGES = 5          # a company feed (all levels, no date filter) is small
    MAX_TOTAL = 1200        # global safety net only, no longer shared between the queries
    MAX_DETAIL = 110        # JD + seniority reads per run, dealt round-robin across the queries
    FEED_DETAIL = 15        # ...of which at most this many for a company feed
    SENIOR = ("senior", "sr.", "sr ", "lead", "principal", "team lead", "manager", "head of",
              "director", "experienced")
    SENIOR_WORDS = r"\b(architects?|experts?|staff|vp|chief)\b"   # word-bound: not 'Architecture'/'Expertise'/'Staffing'
    STUDENT_WORDS = r"\b(student|interns?|internship|trainee|co-?op)\b"   # NOT 'graduate' (= junior, the target level)
    JUNIOR_WORDS = r"\b(junior|jr\.?|entry[- ]level|graduate|new[- ]grad|associate)\b"
    TECHS = [".net", "c#", "c++", "python", "java", "javascript", "typescript", "node", "react",
             "angular", "vue", "go", "golang", "rust", "ruby", "php", "kotlin", "swift", "scala",
             "django", "flask", "fastapi", "spring", "aws", "azure", "gcp", "kubernetes", "docker",
             "sql", "postgres", "mongodb", "graphql", "devops", "backend", "frontend", "full stack",
             "fullstack", "embedded", "firmware", "automation", "qa", "labview", "linux"]
    SENIORITY_MAP = {"entry level": "junior", "internship": "student", "mid-senior level": "senior",
                     "director": "senior", "executive": "senior"}

    def title_level(t):
        t = (t or "").lower()
        if re.search(STUDENT_WORDS, t):
            return "student"
        if any(w in t for w in SENIOR) or re.search(SENIOR_WORDS, t):
            return "senior"
        if re.search(JUNIOR_WORDS, t) or "ג'וניור" in t:
            return "junior"
        # Unknown until the JD / LinkedIn 'Seniority level' is read. LinkedIn's entry-level
        # filter is noisy (101 of 256 judged cards were really Mid-Senior), so an unread card
        # must not be treated as junior (audit bug 11 / judgment call 8 - reversible).
        return ""

    def tech_of(text):
        t = (text or "").lower()
        return [k for k in TECHS if re.search(r"(?<![a-z0-9])" + re.escape(k) + r"(?![a-z0-9])", t)]

    def get(sess, url, params=None):
        for attempt in range(3):
            try:
                r = sess.get(url, params=params, headers=HEADERS, timeout=30)
                if r.status_code == 429:
                    time.sleep(4 * (2 ** attempt))          # 4s, 8s, 16s
                    continue
                return r if r.status_code == 200 else None
            except Exception:
                time.sleep(2 + attempt)
        return "RATE_LIMITED"

    out, seen = [], set()
    lane_of = []                # parallel to out: (query index, rank within that query, newest = 0)
    try:
        sess = requests.Session()
    except Exception:
        return out

    for qi, q in enumerate(QUERIES):
        feed = isinstance(q, dict)
        base = (dict({"location": "Israel", "sortBy": "DD"}, **q) if feed else
                {"keywords": q, "location": "Israel", "f_E": "2", "f_TPR": WINDOW, "sortBy": "DD"})
        got = 0
        for page in range(FEED_PAGES if feed else MAX_PAGES):
            if len(out) >= MAX_TOTAL:
                break
            r = get(sess, SEARCH, dict(base, start=str(page * 10)))
            if r is None or r == "RATE_LIMITED":
                break
            try:
                soup = BeautifulSoup(r.text, "lxml")
                cards = soup.select("div.base-card") or soup.select("li")
            except Exception:
                break
            new_here = 0
            for d in cards:
                urn = d.get("data-entity-urn", "") or ""
                m = re.search(r"jobPosting:(\d+)", urn)
                a = d.select_one("a.base-card__full-link") or d.select_one("a[href*='/jobs/view/']")
                href = (a.get("href", "") if a else "").split("?")[0]
                sid = m.group(1) if m else ""
                if not sid:
                    m2 = re.search(r"/jobs/view/(?:[^/]*?-)?(\d{6,})", href)
                    sid = m2.group(1) if m2 else ""
                if not sid or sid in seen:
                    continue
                seen.add(sid)
                new_here += 1
                te = d.select_one("h3.base-search-card__title")
                ce = d.select_one("h4.base-search-card__subtitle")
                le = d.select_one(".job-search-card__location")
                title = te.get_text(strip=True) if te else ""
                out.append({
                    "source": "linkedin", "sid": sid, "title": title,
                    "company": ce.get_text(strip=True) if ce else "",
                    "city": le.get_text(strip=True) if le else "",
                    "url": "https://www.linkedin.com/jobs/view/" + sid,
                    "level": title_level(title), "years_min": None, "years_max": None,
                    "tech": tech_of(title), "desc": "", "active": True,
                })
                lane_of.append((qi, got)); got += 1
            if not cards or new_here == 0:
                break                                   # end of results for this query
            time.sleep(1.3)

    # JD + LinkedIn's own seniority field, newest first, dealt ROUND-ROBIN across the queries: in
    # plain list order the developer lane used the whole budget and no QA-lane card was ever read.
    order = sorted(range(len(out)), key=lambda i: (lane_of[i][1], lane_of[i][0]))
    details, per_q = 0, {}
    for i in order:
        if details >= MAX_DETAIL:
            break
        qi, row = lane_of[i][0], out[i]
        if isinstance(QUERIES[qi], dict) and per_q.get(qi, 0) >= FEED_DETAIL:
            continue
        r = get(sess, DETAIL % row["sid"])
        if r == "RATE_LIMITED":
            break                                        # keep titles-only for the rest
        details += 1; per_q[qi] = per_q.get(qi, 0) + 1
        if r is None:
            continue
        try:
            soup = BeautifulSoup(r.text, "lxml")
            body = soup.select_one(".show-more-less-html__markup") or soup.select_one(".description__text")
            if body:
                row["desc"] = _html.unescape(re.sub(r"\s+", " ", body.get_text(" "))).strip()[:2500]
                row["tech"] = tech_of(row["title"] + " " + row["desc"])
            for li in soup.select("li.description__job-criteria-item"):
                h = li.select_one("h3")
                v = li.select_one("span")
                if h and v and "seniority" in h.get_text(strip=True).lower():
                    lvl = SENIORITY_MAP.get(v.get_text(strip=True).lower())
                    if lvl and row["level"] != "senior":   # a 'Senior' title always wins
                        row["level"] = lvl
        except Exception:
            pass
        time.sleep(1.2)
    return out
