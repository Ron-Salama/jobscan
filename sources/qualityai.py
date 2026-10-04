# -*- coding: utf-8 -*-
"""QualityAI (careers.quality-ai.com) - SAP SuccessFactors career site scraper.
"""


def src_qualityai():
    """QualityAI (careers.quality-ai.com) — SAP SuccessFactors career site.
    Returns Israel tech/software roles as list of dicts. Never raises."""
    import re, time, requests
    from bs4 import BeautifulSoup
    from urllib.parse import urljoin

    HOST = "https://careers.quality-ai.com"
    LIST = HOST + "/search?q=&locationsearch=Israel&startrow={}"
    HEADERS = {
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/124.0.0.0 Safari/537.36"),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml",
    }
    CAP = 120
    MAX_PAGES = 6           # startrow 0..125 (SF pages of 25) — safety bound
    TECH_TERMS = [
        "python", "java", "javascript", "typescript", "c\\+\\+", "c#", r"\.net",
        "node", "react", "angular", "vue", "sql", "nosql", "mongodb", "postgres",
        "mysql", "oracle", "redis", "aws", "azure", "gcp", "docker", "kubernetes",
        "k8s", "linux", "bash", "shell", "git", "jenkins", "ci/cd", "selenium",
        "cypress", "playwright", "appium", "pytest", "junit", "testng", "rest",
        "api", "graphql", "kafka", "spark", "hadoop", "terraform", "ansible",
        "embedded", "rf", "fpga", "verilog", "vhdl", "matlab", "labview", "qa",
        "automation", "devops", "php", "ruby", "golang", "rust", "scala",
        "kotlin", "swift", "android", "ios", "jira", "agile", "scrum",
        "machine learning", "deep learning", "tensorflow", "pytorch", "opencv",
        "microservices", "spring", "django", "flask", "html", "css", "perl",
        "powershell", "cybersecurity", "networking", "tcp/ip", "sap",
    ]
    _tech_rx = [(t, re.compile(r"(?<![a-z0-9])" + t + r"(?![a-z0-9])", re.I))
                for t in TECH_TERMS]
    _tech_label = {
        "c\\+\\+": "c++", "c#": "c#", r"\.net": ".net", "k8s": "kubernetes",
    }
    MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
              "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11,
              "dec": 12}

    def _get(url):
        for attempt in range(2):
            try:
                r = requests.get(url, headers=HEADERS, timeout=25)
                if r.status_code == 200 and r.content:
                    return r.content
            except Exception:
                pass
            time.sleep(1.0)
        return None

    def _clean(s):
        if not s:
            return ""
        return re.sub(r"\s+", " ", s.replace("\xa0", " ").replace("�", " ")).strip()

    def _parse_date(s):
        # "26 Aug 2026" / "2 Sept 2026" -> sortable int yyyymmdd, else 0
        m = re.search(r"(\d{1,2})\s+([A-Za-z]{3,4})\.?\s+(\d{4})", s or "")
        if not m:
            return 0
        d, mon, y = int(m.group(1)), m.group(2)[:4].lower(), int(m.group(3))
        mm = MONTHS.get(mon, MONTHS.get(mon[:3], 0))
        return y * 10000 + mm * 100 + d if mm else 0

    def _level(text):
        t = (text or "").lower()
        if re.search(r"\b(intern|internship|student|סטודנט)\b", t):
            return "student"
        if re.search(r"\b(senior|sr\.?|lead|principal|staff|expert|manager|"
                     r"head of|director|architect)\b", t):
            return "senior"
        if re.search(r"\b(junior|jr\.?|entry[- ]level|graduate|associate)\b", t):
            return "junior"
        return ""

    def _years(text):
        t = (text or "").lower()
        # ranges: "3-5 years", "3 to 5 years"
        m = re.search(r"(\d{1,2})\s*(?:-|–|to)\s*(\d{1,2})\s*(?:\+)?\s*years?", t)
        if m:
            lo, hi = int(m.group(1)), int(m.group(2))
            if lo <= hi <= 40:
                return lo, hi
        # "3+ years", "at least 3 years", "minimum 3 years", "over 3 years"
        m = re.search(r"(?:at least|minimum(?: of)?|over|more than|"
                      r"experience of)\s*(\d{1,2})\s*(?:\+)?\s*years?", t)
        if m and int(m.group(1)) <= 40:
            return int(m.group(1)), None
        m = re.search(r"(\d{1,2})\s*\+\s*years?", t)
        if m and int(m.group(1)) <= 40:
            return int(m.group(1)), None
        m = re.search(r"(\d{1,2})\s*years?(?:\s+of)?\s+(?:of\s+)?experience", t)
        if m and int(m.group(1)) <= 40:
            return int(m.group(1)), None
        return None, None

    def _tech(text):
        t = (text or "").lower()
        out = []
        for term, rx in _tech_rx:
            if rx.search(t):
                out.append(_tech_label.get(term, term))
        # de-dup preserving order
        seen, res = set(), []
        for x in out:
            if x not in seen:
                seen.add(x)
                res.append(x)
        return res

    results = {}
    try:
        for page in range(MAX_PAGES):
            html = _get(LIST.format(page * 25))
            if not html:
                break
            soup = BeautifulSoup(html, "lxml")
            rows = soup.select("tr.data-row")
            if not rows:
                break
            new_on_page = 0
            for row in rows:
                a = row.select_one("a.jobTitle-link")
                if not a or not a.get("href"):
                    continue
                href = a["href"]
                mid = re.search(r"/(\d+)/?$", href)
                sid = mid.group(1) if mid else href.rstrip("/").rsplit("/", 1)[-1]
                if sid in results:
                    continue
                raw_title = _clean(a.get_text())
                # strip leading req-id prefix e.g. "20613 - " / "23819- "
                title = re.sub(r"^\d{3,6}\s*-\s*", "", raw_title).strip() or raw_title
                dept = row.select_one("span.jobDepartment")
                city = _clean(dept.get_text()) if dept else ""
                if not city:
                    city = "Petah Tikva"
                dnode = row.select_one("td.colDate span.jobDate")
                if not dnode:
                    dnode = row.select_one("span.jobDate")
                date_str = _clean(dnode.get_text()) if dnode else ""
                results[sid] = {
                    "source": "qualityai",
                    "sid": sid,
                    "title": title,
                    "company": "QualityAI",
                    "city": city,
                    "url": urljoin(HOST, href),
                    "level": _level(title),
                    "years_min": None,
                    "years_max": None,
                    "tech": _tech(title),
                    "desc": "",
                    "active": True,
                    "_date": _parse_date(date_str),
                }
                new_on_page += 1
            if new_on_page == 0:
                break
            if len(results) >= 300:
                break
            time.sleep(0.6)
    except Exception:
        pass

    # newest first, then cap
    try:
        items = sorted(results.values(), key=lambda d: d["_date"], reverse=True)
    except Exception:
        items = list(results.values())
    items = items[:CAP]

    # enrich each with detail page (desc / years / tech), resilient
    for job in items:
        try:
            html = _get(job["url"])
            if html:
                dsoup = BeautifulSoup(html, "lxml")
                node = (dsoup.select_one(".jobdescription")
                        or dsoup.select_one("div.job")
                        or dsoup.select_one("[itemprop=description]"))
                if node:
                    desc = _clean(node.get_text(" "))
                    job["desc"] = desc[:5000]
                    job["level"] = job["level"] or _level(job["title"] + " " + desc)
                    ymin, ymax = _years(desc)
                    job["years_min"], job["years_max"] = ymin, ymax
                    job["tech"] = job["tech"] + [t for t in _tech(desc)
                                                 if t not in job["tech"]]
            time.sleep(0.4)
        except Exception:
            continue

    # drop private helper key
    for job in items:
        job.pop("_date", None)
    return items
