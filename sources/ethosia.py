# -*- coding: utf-8 -*-
"""Ethosia (ethosia.co.il) - Israeli recruiting agency, strong in the North.

HTML scraper: newest WordPress archive pages; title, URL, id and requirements are all on
the listing card.
"""


def src_ethosia():
    """
    Ethosia (ethosia.co.il) - Israeli recruiting agency, strong in the North.
    Scrapes the newest ~4 WordPress archive pages of /content/ (50 jobs/page).
    Every posting is an <article class="job ..."> whose class tokens carry the
    English category slug and a numeric 'area-in-the-country-<id>' (a macro
    region, resolved to a location string via a small map). Title, direct URL,
    post-id and a requirements excerpt all live on the listing, so no per-job
    detail fetch is needed in the normal case; a bounded fallback fetches a job
    detail only when an unknown area-id shows up. Company is masked (agency)->"".
    Returns tech/software roles only; caller applies seniority/location filters.
    """
    import re, time, html
    import requests
    from urllib.parse import unquote, urljoin
    from bs4 import BeautifulSoup

    BASE = "https://ethosia.co.il"
    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
    MAX_PAGES = 4
    CAP = 120

    # area-in-the-country term id -> location string the caller can region.
    # Discovered live; Haifa (105) & North (122) => caller regions as North.
    # 614 = "nationwide / all of Israel" -> no specific city ("").
    AREA = {"80": "Sharon", "83": "Center", "85": "Shfela",
            "105": "Haifa", "122": "North", "614": ""}
    # Hebrew macro-region -> English (fallback when a new area id appears)
    HEB_LOC = {"שרון": "Sharon", "השרון": "Sharon",
               "מרכז": "Center", "שפלה": "Shfela",
               "חיפה": "Haifa", "צפון": "North",
               "דרום": "South", "ירושלים": "Jerusalem",
               "תל אביב": "Tel Aviv", "כל הארץ": ""}

    # category slugs that are tech/software (software + hw/embedded/EE/data/AI/QA/IT/systems)
    TECH_CATS = {
        "ai-engineer", "algorithm-research", "architecture-engineer", "asic-design",
        "c-plus-plus-developer", "chip-architecture", "data-engineering", "data-scientist",
        "devops", "fae", "firmware-engineer", "front-end", "full-stack",
        "hardware-development", "hardware-testing", "help-desk", "infrastructure-specialist",
        "integration-engineering", "it-manager", "it-project-manager",
        "machine-learning-engineer", "network-engineer", "optical-engineer",
        "physical-designer", "rf-design", "rf-ic-design", "robotics-engineer",
        "rt-embedded", "software-architect", "software-developmen", "software-development",
        "system-administration", "system-architect", "system-engineering",
        "technical-support", "test-engineer", "validation-engineer",
        "verification-design", "vlsi-backend-design",
    }
    TECH_TITLE = re.compile(
        r"develop|software|full[\s-]?stack|back[\s-]?end|front[\s-]?end|devops|embedded|"
        r"firmware|algorithm|\bdata\b|machine learning|\bml\b|\bai\b|\bllm\b|genai|python|"
        r"\bjava\b|c\+\+|c#|\.net|javascript|typescript|react|angular|node|\bqa\b|automation|"
        r"sdet|verification|validation|vlsi|asic|\brf\b|fpga|hardware|network|sysadmin|"
        r"infrastructur|robotic|integration|programmer|\bsystem\b|"
        r"מפתח|תוכנה|אוטומציה",
        re.I)
    TECH_KW = ["python", "java", "javascript", "typescript", "c++", "c#", ".net", "react",
               "angular", "vue", "node", "go", "golang", "rust", "kubernetes", "docker",
               "aws", "azure", "gcp", "sql", "linux", "embedded", "firmware", "rtos",
               "devops", "llm", "genai", "pytorch", "tensorflow", "verilog", "systemverilog",
               "fpga", "asic", "vlsi", "rf", "spark", "kafka", "microservices"]

    SEN = re.compile(r"\b(senior|sr\.?|lead|principal|staff|architect|head|vp|director|"
                     r"chief|expert|manager)\b", re.I)
    JUN = re.compile(r"\b(junior|jr\.?|entry[\s-]?level|graduate)\b", re.I)
    STU = re.compile(r"\b(student|intern|internship)\b|סטודנט|"
                     r"מתמח", re.I)

    def clean(t):
        if not t:
            return ""
        t = html.unescape(t)
        if "%" in t:
            try:
                t = unquote(t)
            except Exception:
                pass
        return re.sub(r"\s+", " ", t).strip().lstrip("#").strip()

    def level_of(title):
        if STU.search(title):
            return "student"
        if SEN.search(title):
            return "senior"
        if JUN.search(title):
            return "junior"
        return ""

    def years_of(desc):
        m = re.findall(r"(\d{1,2})\s*\+?\s*(?:years|yrs?|"
                       r"שנים|שנה)", (desc or "").lower())
        return min(int(x) for x in m) if m else None

    def techs(cat, blob):
        out = []
        if cat:
            out.append(cat.replace("-", " "))
        low = blob.lower()
        for kw in TECH_KW:
            if kw in low and kw not in out:
                out.append(kw)
        return out[:12]

    s = requests.Session()
    s.headers.update({"User-Agent": UA,
                      "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                      "Accept-Language": "en-US,en;q=0.9,he;q=0.8"})

    def detail_location(href):
        """Bounded fallback: read the Hebrew Location cell from a job's meta table."""
        try:
            d = s.get(href, timeout=30)
            d.encoding = "utf-8"
            ds = BeautifulSoup(d.text, "lxml")
            for tbl in ds.find_all("table"):
                for tr in tbl.find_all("tr"):
                    cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
                    if cells and cells[0] == "Location" and len(cells) > 1:
                        v = cells[1].strip()
                        return HEB_LOC.get(v, v)
        except Exception:
            pass
        return ""

    out = []
    area_cache = dict(AREA)
    fallback_budget = 6
    seen_urls = set()

    for pg in range(1, MAX_PAGES + 1):
        if len(out) >= CAP:
            break
        try:
            r = s.get("%s/content/page/%d/" % (BASE, pg), timeout=30)
            if r.status_code != 200:
                break
            r.encoding = "utf-8"
            soup = BeautifulSoup(r.text, "lxml")
        except Exception:
            break

        arts = soup.select("article.job")
        if not arts:
            break

        for art in arts:
            if len(out) >= CAP:
                break
            try:
                cls = art.get("class") or []
                a = art.select_one("h2.entry-title a") or art.select_one("a[rel='bookmark']")
                if not a or not a.get("href"):
                    continue
                url = urljoin(BASE, a.get("href"))
                if url in seen_urls:
                    continue
                seen_urls.add(url)

                title = clean(a.get_text())
                if not title:
                    continue

                cat = next((c[len("job-categories-"):] for c in cls
                            if c.startswith("job-categories-")), "")

                # tech/software gate (category slug OR title keyword)
                if cat not in TECH_CATS and not TECH_TITLE.search(title):
                    continue

                # sid: WordPress post id, else slug
                sid = ""
                pid = art.get("id") or ""
                m = re.match(r"post-(\d+)", pid)
                if m:
                    sid = m.group(1)
                if not sid:
                    m = re.search(r"/content/([^/?#]+)/?$", url)
                    sid = unquote(m.group(1)) if m else url

                # location from area-in-the-country id (bounded detail fallback if new)
                aid = next((c.split("-")[-1] for c in cls
                            if re.match(r"area-in-the-country-\d+$", c)), None)
                if aid in area_cache:
                    city = area_cache[aid]
                elif aid and fallback_budget > 0:
                    fallback_budget -= 1
                    city = detail_location(url)
                    area_cache[aid] = city
                    time.sleep(0.3)
                else:
                    city = ""

                exc = art.select_one("div.ast-excerpt-container")
                desc = clean(exc.get_text(" ", strip=True)) if exc else ""

                out.append({
                    "source": "ethosia",
                    "sid": str(sid),
                    "title": title,
                    "company": "",
                    "city": city,
                    "url": url,
                    "level": level_of(title),
                    "years_min": years_of(desc),
                    "years_max": None,
                    "tech": techs(cat, title + " " + desc),
                    "desc": desc,
                    "active": True,
                })
            except Exception:
                continue

        time.sleep(0.35)

    return out
