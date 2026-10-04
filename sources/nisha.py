# -*- coding: utf-8 -*-
"""Nisha (nisha.co.il) - high-tech recruiting board (staffing agency).

HTML scraper: newest listing pages; the card carries the full JD, a detail page is
fetched only when a card is thin.
"""


def src_nisha():
    """Nisha (nisha.co.il) high-tech recruiting board - newest listing pages.
    Nisha is a staffing agency: company + city are masked site-wide, so those
    come back "". Each listing card already carries the full JD + requirements,
    so we parse cards directly and only hit a detail page when a card is thin.
    """
    import re, time, html as _html
    import requests
    from bs4 import BeautifulSoup

    BASE = "https://www.nisha.co.il"
    LISTINGS = ["/job_cat/high-tech/", "/job-high-tech-software/"]
    MAX_PAGES = 4          # newest N pages per listing (site is newest-first)
    CAP = 120              # hard cap on returned jobs
    UA = {
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
        "Accept-Language": "he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept": "text/html,application/xhtml+xml",
    }

    TECH = [
        "python", "java", "javascript", "typescript", "c++", "c#", ".net", "node",
        "node.js", "react", "angular", "vue", "next.js", "go", "golang", "rust",
        "ruby", "php", "swift", "kotlin", "scala", "perl", "bash", "sql", "nosql",
        "mongodb", "postgres", "postgresql", "mysql", "oracle", "redis", "kafka",
        "rabbitmq", "docker", "kubernetes", "k8s", "aws", "azure", "gcp",
        "terraform", "ansible", "jenkins", "gitlab", "git", "linux", "unix",
        "windows", "embedded", "firmware", "rtos", "freertos", "fpga", "verilog",
        "systemverilog", "vhdl", "matlab", "simulink", "opencv", "tensorflow",
        "pytorch", "keras", "llm", "genai", "nlp", "spark", "hadoop", "airflow",
        "elasticsearch", "graphql", "rest", "grpc", "microservices", "ci/cd",
        "devops", "selenium", "cypress", "playwright", "appium", "pytest",
        "jira", "priority", "sap", "salesforce", "dynamics", "dsp", "pcie",
        "vivado", "xilinx", "altera", "arm", "stm32", "cuda", "opengl", "vulkan",
        "spring", "django", "flask", "fastapi", "express", ".net core", "asp.net",
        "wpf", "qt", "webrtc", "prometheus", "grafana", "snowflake",
        "databricks", "etl", "power bi", "tableau", "assembly",
    ]
    SENIOR_EN = ["senior", "sr.", "sr ", "lead", "principal", "staff", "architect",
                 "team lead", "teamlead", "head of", "vp ", "director", "chief",
                 "expert", "manager"]
    SENIOR_HE = ["בכיר", "מנהל", "ראש צוות", "ארכיטקט", "מוביל"]
    JUNIOR_EN = ["junior", "jr.", "jr ", "entry", "entry-level", "entry level", "associate"]
    JUNIOR_HE = ["ג'וניור", "זוטר", "ללא ניסיון", "מתחיל"]
    # strong student markers only (weak words appear in normal JDs)
    STUDENT_TITLE_EN = ["student", "intern", "internship", "co-op"]
    STUDENT_TITLE_HE = ["סטודנט", "מתמחה", "משרת סטודנט", "התמחות"]
    STUDENT_BODY = ["סטודנט", "משרת סטודנט", "internship", "student position"]

    sess = requests.Session()
    sess.headers.update(UA)

    def fetch(path):
        url = path if path.startswith("http") else (BASE + path)
        try:
            r = sess.get(url, timeout=30)
            if r.status_code != 200:
                return None
            r.encoding = "utf-8"
            return r.text
        except Exception:
            return None

    def clean(txt):
        return re.sub(r"\s+", " ", _html.unescape(txt or "")).strip()

    def guess_level(title, blob, years_min):
        # seniority is only reliable from the TITLE (mirrors the caller's own rule);
        # the JD body always mentions "experience/leadership" and would over-tag senior.
        tl = title.lower()
        if (any(w in tl for w in STUDENT_TITLE_EN) or any(w in title for w in STUDENT_TITLE_HE)
                or any(w in (title + " " + blob).lower() for w in STUDENT_BODY)):
            return "student"
        if any(w in tl for w in SENIOR_EN) or any(w in title for w in SENIOR_HE):
            return "senior"
        if any(w in tl for w in JUNIOR_EN) or any(w in title for w in JUNIOR_HE):
            return "junior"
        # no title signal -> infer from required years if the JD stated them
        if years_min is not None:
            if years_min <= 2:
                return "junior"
            if years_min >= 5:
                return "senior"
        return ""

    def parse_years(blob):
        mins = []
        # english: "3 years", "3+ yrs" ; hebrew: "3 shanot / shanim / shana"
        for m in re.finditer(r"(\d+)\s*\+?\s*(?:years|year|yrs|yr|שנות|שנים|שנה)", blob.lower()):
            try:
                mins.append(int(m.group(1)))
            except Exception:
                pass
        mins = [x for x in mins if 0 < x <= 25]
        return (min(mins) if mins else None)

    def extract_tech(blob):
        bl = blob.lower()
        found = []
        for kw in TECH:
            if kw in bl and kw not in found:
                found.append(kw)
        return found[:15]

    def detail_desc(idnum):
        """Fallback: pull description + requirements from the job detail page."""
        htmltext = fetch("/job/%s/" % idnum)
        if not htmltext:
            return ""
        try:
            ds = BeautifulSoup(htmltext, "lxml")
        except Exception:
            return ""
        parts = []
        for sel in ("div.job-description", "div.more-details", "div.job-content"):
            el = ds.select_one(sel)
            if el:
                parts.append(el.get_text(" ", strip=True))
        return clean(" ".join(parts))[:4000]

    out = []
    seen = set()
    stop = False

    for listing in LISTINGS:
        if stop:
            break
        for page in range(1, MAX_PAGES + 1):
            if stop:
                break
            path = listing if page == 1 else (listing.rstrip("/") + "/page/%d/" % page)
            htmltext = fetch(path)
            if not htmltext:
                break  # first page dead = skip listing; later page dead = end of pages
            try:
                soup = BeautifulSoup(htmltext, "lxml")
            except Exception:
                break
            cards = soup.select("div.item-job")
            if not cards:
                break
            new_on_page = 0
            for c in cards:
                a = c.select_one("h3.job-title a[href]")
                if not a:
                    continue
                m = re.search(r"/job/(\d+)/?", a.get("href", ""))
                if not m:
                    continue
                sid = m.group(1)
                if sid in seen:
                    continue
                seen.add(sid)
                new_on_page += 1
                title = clean(a.get_text(" ", strip=True))
                url = "%s/job/%s/" % (BASE, sid)
                desc_el = c.select_one("div.job-description")
                req_el = c.select_one("div.more-details")
                desc = ""
                if desc_el:
                    desc += desc_el.get_text(" ", strip=True) + " "
                if req_el:
                    desc += req_el.get_text(" ", strip=True)
                desc = clean(desc)
                if len(desc) < 40:  # thin card -> fall back to detail page
                    d2 = detail_desc(sid)
                    if len(d2) > len(desc):
                        desc = d2
                    time.sleep(0.25)
                blob = title + " " + desc
                ymin = parse_years(blob)
                out.append({
                    "source": "nisha",
                    "sid": sid,
                    "title": title,
                    "company": "",              # agency board: employer masked
                    "city": "",                 # nisha never exposes a city
                    "url": url,
                    "level": guess_level(title, desc, ymin),
                    "years_min": ymin,
                    "years_max": None,
                    "tech": extract_tech(blob),
                    "desc": desc[:4000],
                    "active": True,
                })
                if len(out) >= CAP:
                    stop = True
                    break
            time.sleep(0.3)
            if new_on_page == 0:  # nothing new here -> stop paginating this listing
                break

    return out
