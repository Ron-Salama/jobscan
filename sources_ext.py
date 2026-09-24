# -*- coding: utf-8 -*-
# Auto-generated adapters (v2 scrapers + v3 + giants). Built by workflow 2026-09-17.

import re as _re_shared

# Shared student test for the free-text board adapters (audit 2026-09-24, BUG 9).
# TITLE ONLY, word-bound: JD/company-blurb text ("המתמחה בפיתוח" = "that specializes in
# development", "internal tools", "international") must never make a role 'student'.
# 'graduate' / 'בוגר' (graduate) mean junior, never student.
_STUDENT_TITLE_RX = _re_shared.compile(r"\b(student|interns?|internship|co-?op|trainee)\b", _re_shared.I)


def _is_student_title(title):
    t = title or ""
    return bool(_STUDENT_TITLE_RX.search(t)) or "סטודנט" in t or t.strip().startswith("מתמח")


# ===== ethosia (works=yes) =====
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


# ===== dialog (works=yes) =====
def src_dialog():
    """Dialog (dialog.co.il) Israeli high-tech job board. Server-rendered HTML.
    Scrapes the newest MAX_PAGES listing pages of EACH software/data/qa/system category
    (per-category budget; no global cap, so the later categories are always requested).
    sid = positionId. company is not published on the board, so it is returned "".
    Never raises; returns whatever it managed to collect."""
    import re, time
    import requests
    from bs4 import BeautifulSoup

    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
    HEADERS = {"User-Agent": UA,
               "Accept": "text/html,application/xhtml+xml",
               "Accept-Language": "he-IL,he;q=0.9,en;q=0.8"}
    BASE = "https://www.dialog.co.il"
    CATS = ("software", "data", "qa", "system")
    MAX_PAGES = 3      # per category (newest first); stops early on an empty/repeated page

    TECH_KW = [
        "python", "java", "javascript", "typescript", "react", "angular", "vue",
        "node", "node.js", "c++", "c#", ".net", "go", "golang", "rust", "kotlin",
        "swift", "php", "ruby", "scala", "sql", "nosql", "mongodb", "postgres",
        "mysql", "redis", "kafka", "spark", "hadoop", "aws", "azure", "gcp",
        "docker", "kubernetes", "k8s", "terraform", "jenkins", "ci/cd", "linux",
        "embedded", "firmware", "rtos", "verilog", "vhdl", "matlab", "django",
        "flask", "fastapi", "spring", "graphql", "rest", "microservices",
        "selenium", "cypress", "playwright", "pytest", "appium", "jmeter",
        "tensorflow", "pytorch", "llm", "genai", "nlp", "airflow", "snowflake",
        "databricks", "elasticsearch", "devops", "ansible", "bash", "powershell",
    ]

    def txt(el):
        return re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip() if el else ""

    def parse_years(s):
        s = (s or "").lower()
        nums = re.findall(r'(\d+)\s*\+?\s*(?:years?|yrs?|שנ)', s)  # שנ = "shan" (year)
        nums = [int(x) for x in nums if int(x) <= 25]
        if not nums:
            return None, None
        rng = re.search(r'(\d+)\s*[-–]\s*(\d+)\s*(?:years?|yrs?|שנ)', s)
        if rng:
            a, b = int(rng.group(1)), int(rng.group(2))
            return min(a, b), max(a, b)
        return min(nums), (max(nums) if len(nums) > 1 else None)

    def level_of(title, blob):
        # student: TITLE only, word-bound (the company blurb "המתמחה בפיתוח" means
        # "that specializes in development" and made 14/18 false 'student' labels)
        if _is_student_title(title):
            return "student"
        # SENIOR from the TITLE only: on the JD/blurb 'lead' hit 'leading', 'architect' hit
        # 'architectures', 'expert' hit 'expertise' (review 2026-09-24); the blurb still
        # counts for junior
        tl = (title or "").lower()
        t = (title + " " + blob).lower()
        if any(w in tl for w in ("senior", "sr.", "lead", "principal", "staff",
                                 "architect", "בכיר",
                                 "team lead", "expert", "מנוסה")):
            return "senior"
        if any(w in t for w in ("junior", "jr.", "entry", "גוניור",
                                "זוטר",
                                "ללא ניסיון")):
            return "junior"
        return ""

    def tech_of(skills_ul, blob):
        found = []
        if skills_ul:
            for li in skills_ul.select("li"):
                s = txt(li)
                if s:
                    found.append(s)
        if not found:
            low = blob.lower()
            for kw in TECH_KW:
                if re.search(r'(?<![a-z0-9])' + re.escape(kw) + r'(?![a-z0-9+#.])', low) \
                   or (kw in ("c++", "c#", ".net", "node.js", "ci/cd", "k8s") and kw in low):
                    found.append(kw)
        seen = set(); uniq = []
        for x in found:
            k = x.lower()
            if k not in seen:
                seen.add(k); uniq.append(x)
        return uniq[:15]

    out = []
    seen_ids = set()
    try:
        sess = requests.Session()
        sess.headers.update(HEADERS)
    except Exception:
        sess = None

    per_cat = {}
    for cat in CATS:
        n_cat = 0
        prev_pids = None
        for page in range(1, MAX_PAGES + 1):
            url = "%s/high-tech/jobs/%s/?page=%d" % (BASE, cat, page)
            try:
                if sess is not None:
                    r = sess.get(url, timeout=30)
                else:
                    r = requests.get(url, headers=HEADERS, timeout=30)
                if r.status_code != 200:
                    continue
                r.encoding = "utf-8"
                soup = BeautifulSoup(r.text, "lxml")
            except Exception:
                continue

            cards = soup.select("div.item_job")
            if not cards:
                break
            n_before = len(out)
            page_pids = []
            for card in cards:
                try:
                    a = card.select_one("h3.title_job a")
                    title = txt(card.select_one("h3.title_job")) or txt(a)
                    href = a.get("href", "") if a else ""

                    pid = ""
                    m = re.search(r'positionId=(\d+)', href)
                    if m:
                        pid = m.group(1)
                    if not pid:
                        btn = card.select_one("[data-positionid]")
                        if btn and btn.get("data-positionid"):
                            pid = re.sub(r"\D", "", btn["data-positionid"])
                    if not pid:
                        sp = card.select_one("span.positionId")
                        if sp:
                            dm = re.search(r'(\d+)', txt(sp))
                            if dm:
                                pid = dm.group(1)
                    if pid:
                        page_pids.append(pid)
                    if not pid or pid in seen_ids:
                        continue
                    seen_ids.add(pid)

                    link = "%s/high-tech/jobs/jobpage?positionId=%s" % (BASE, pid)

                    city = ""
                    loc_icon = card.select_one("span.icon-location")
                    if loc_icon and loc_icon.parent:
                        city = txt(loc_icon.parent)
                    if not city:
                        li_loc = card.select_one("ul.job_info li a")
                        if li_loc:
                            city = txt(li_loc)

                    desc_top = txt(card.select_one("div.right div.top div.desc"))
                    reqs = txt(card.select_one("div.req_list"))
                    reqs = re.sub(r'^מה צריך:\s*', '', reqs)  # strip "ma tsarich:" label
                    on_comp = txt(card.select_one("div.on_comp"))
                    full_desc = " | ".join(x for x in (desc_top, reqs) if x)
                    blob = " ".join(x for x in (title, desc_top, reqs, on_comp) if x)

                    ymin, ymax = parse_years(reqs + " " + desc_top)
                    lvl = level_of(title, blob)
                    if lvl == "junior" and ymin is None:
                        ymax = 2
                    tech = tech_of(card.select_one("ul.skills_list"), blob)

                    out.append({
                        "source": "dialog",
                        "sid": pid,
                        "title": title,
                        "company": "",
                        "city": city,
                        "url": link,
                        "level": lvl,
                        "years_min": ymin,
                        "years_max": ymax,
                        "tech": tech,
                        "desc": full_desc[:1200],
                        "active": True,
                    })
                except Exception:
                    continue
            n_cat += len(out) - n_before
            time.sleep(0.3)
            # past the last page (empty, or a repeat of the previous one) -> next category.
            # A page whose ids were all seen in an earlier category keeps paging.
            if not page_pids or page_pids == prev_pids:
                break
            prev_pids = page_pids
        per_cat[cat] = n_cat
    try:
        print("    dialog per-category:", per_cat)
    except Exception:
        pass
    return out


# ===== nisha (works=yes) =====
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


# ===== gotfriends (works=yes) =====
# -*- coding: utf-8 -*-
import re, time, html, json
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

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
    # (category, subcat) boards, newest-first. Ron's lanes first (QA/automation, .NET,
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


# ===== builtin (works=yes) =====
# -*- coding: utf-8 -*-
import re, time, json
import requests
from bs4 import BeautifulSoup

def src_builtin():
    """Built In (builtin.com) Israel board -> normalized job dicts.
    Newest ~4 listing pages of https://builtin.com/jobs/mena/israel?page=N .
    Everything (sid, title, url, company, city, level, tech, desc) is on the
    server-rendered listing card, so no per-job detail fetch is needed."""
    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
    BASE = "https://builtin.com"
    LIST = BASE + "/jobs/mena/israel?page=%d"
    MAX_PAGES = 4          # newest N pages only (daily run stays fast; caller dedups)
    CAP = 120

    sess = requests.Session()
    sess.headers.update({"User-Agent": UA,
                         "Accept": "text/html,application/xhtml+xml"})

    def _label(card, icon_cls):
        # BuiltIn puts the value text in the grandparent div of the fa-* icon.
        i = card.select_one("i.%s" % icon_cls)
        if not i or not i.parent or not i.parent.parent:
            return ""
        return i.parent.parent.get_text(" ", strip=True)

    def _level(txt):
        t = (txt or "").lower()
        if any(w in t for w in ("intern", "student")):        return "student"
        if any(w in t for w in ("entry", "junior", "associate")): return "junior"
        if "senior" in t or "principal" in t or "staff" in t or "lead" in t: return "senior"
        return ""   # "Mid level" / unknown -> caller decides

    def _city(txt):
        c = (txt or "").strip()
        c = re.sub(r",?\s*(ISR|Israel|IL)\s*$", "", c, flags=re.I).strip(" ,")
        if c.upper() in ("", "IL", "ISR", "ISRAEL"):
            return "Israel" if txt else ""
        return c

    out, seen_sid = [], set()
    for pg in range(1, MAX_PAGES + 1):
        try:
            r = sess.get(LIST % pg, timeout=30)
            if r.status_code != 200:
                break
            soup = BeautifulSoup(r.text, "lxml")
        except Exception:
            break
        cards = soup.select("div.job-bounded-responsive")
        if not cards:                       # ran past the last page
            break
        for c in cards:
            try:
                a = c.select_one("a[href*='/job/']")
                if not a:
                    continue
                href = a.get("href") or ""
                m = re.search(r"/job/[^/]+/(\d+)", href)
                if not m:
                    continue
                sid = m.group(1)
                if sid in seen_sid:
                    continue
                seen_sid.add(sid)
                title = a.get_text(" ", strip=True)
                url = href if href.startswith("http") else BASE + href

                company = ""
                for ca in c.select("a[href*='/company/']"):
                    t = ca.get_text(" ", strip=True)
                    if t:
                        company = t
                        break

                city = _city(_label(c, "fa-location-dot"))
                level = _level(_label(c, "fa-trophy") or title)

                tech, desc = [], ""
                drop = c.select_one("[data-job-id]")
                if drop:
                    tech = [s.get_text(strip=True) for s in drop.select("span.mx-sm")
                            if s.get_text(strip=True)]
                    tech = list(dict.fromkeys(tech))[:25]
                    d = (drop.select_one("div.fs-sm.text-gray-04")
                         or drop.select_one("div.fs-sm"))
                    if d:
                        desc = d.get_text(" ", strip=True)
                if not level:
                    level = _level(title)

                out.append({
                    "source": "builtin", "sid": sid, "title": title,
                    "company": company, "city": city, "url": url,
                    "level": level, "years_min": None, "years_max": None,
                    "tech": tech, "desc": desc, "active": True,
                })
                if len(out) >= CAP:
                    return out
            except Exception:
                continue
        time.sleep(0.3)
    return out


# ===== linkedin (works=yes) =====
def src_linkedin():
    """LinkedIn guest jobs API (UNOFFICIAL, ToS-grey, rate-limited).
    2026-09-24 rewrite: the old version read only page 1 (~10 cards) of 5 narrow keywords,
    never fetched the JD, and tagged 'graduate' titles as student. Now: Ron's own boolean
    searches, entry-level (f_E=2), past week (f_TPR=r604800), newest first (sortBy=DD),
    paginated until empty; JD + LinkedIn's 'Seniority level' fetched for the newest
    MAX_DETAIL postings. Backs off on 429 and keeps whatever it has. Never raises."""
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
        # Ron's own search (developer lane)
        '(developer OR "software engineer" OR programmer OR "full stack" OR backend OR frontend)',
        # his QA / automation / C# / embedded / test lane
        '("qa automation" OR "automation engineer" OR "test automation" OR "test engineer" '
        'OR embedded OR firmware OR "c#" OR ".net" OR validation OR "integration engineer")',
    ]
    MAX_PAGES = 60          # the guest API returns 10 cards per call -> up to 600 per query
    MAX_TOTAL = 600
    MAX_DETAIL = 80         # newest-first, so these are the freshest postings
    SENIOR = ("senior", "sr.", "sr ", "lead", "principal", "team lead", "manager", "head of",
              "director", "experienced")
    SENIOR_WORDS = r"\b(architects?|experts?|staff|vp|chief)\b"   # word-bound: not 'Architecture'/'Expertise'/'Staffing'
    STUDENT_WORDS = r"\b(student|interns?|internship|trainee|co-?op)\b"   # NOT 'graduate' (= junior, Ron's target)
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
    try:
        sess = requests.Session()
    except Exception:
        return out

    for q in QUERIES:
        for page in range(MAX_PAGES):
            if len(out) >= MAX_TOTAL:
                break
            r = get(sess, SEARCH, {"keywords": q, "location": "Israel", "f_E": "2",
                                   "f_TPR": "r604800", "sortBy": "DD", "start": str(page * 10)})
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
            if not cards or new_here == 0:
                break                                   # end of results for this query
            time.sleep(1.3)

    # JD + LinkedIn's own seniority field for the newest postings
    details = 0
    for row in out:
        if details >= MAX_DETAIL:
            break
        r = get(sess, DETAIL % row["sid"])
        if r == "RATE_LIMITED":
            break                                        # keep titles-only for the rest
        details += 1
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


# ===== cps (works=yes) =====
def src_cps():
    """CPS (cps.co.il) - Israeli hi-tech staffing agency.
    Detail bodies are JS-rendered, but job-sitemap.xml lists every /job/{slug}/ URL + <lastmod>,
    and each job page ships the real title in its server-rendered <title>. We take the newest
    ~120 by lastmod and fetch each title. company/city/desc are JS-only -> "".
    Resilient: never raises; returns whatever it got.
    """
    import re, html, time, requests
    from bs4 import BeautifulSoup

    MAX = 120
    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")
    H = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,application/xml"}
    out = []

    # --- 1) sitemap: collect (lastmod, url, slug) ---
    entries = []
    try:
        r = requests.get("https://www.cps.co.il/job-sitemap.xml", headers=H, timeout=30)
        soup = BeautifulSoup(r.text, "lxml-xml")
        for u in soup.find_all("url"):
            loc = u.find("loc")
            if not loc:
                continue
            url = loc.text.strip()
            path = url.rstrip("/")
            if not re.search(r"/job/[^/]+$", path):   # skip the /job/ index page
                continue
            slug = path.rsplit("/", 1)[-1]
            lm = u.find("lastmod")
            entries.append(((lm.text.strip() if lm else ""), url, slug))
    except Exception as e:
        print("  cps sitemap err %s" % e)
        return out

    entries.sort(key=lambda x: x[0], reverse=True)   # newest lastmod first
    entries = entries[:MAX]

    # --- 2) fetch each job page for its server-rendered <title> ---
    for lm, url, slug in entries:
        title = ""
        try:
            jr = requests.get(url, headers=H, timeout=20)
            m = re.search(r"<title[^>]*>(.*?)</title>", jr.text, re.S | re.I)
            if m:
                title = html.unescape(m.group(1)).strip()
                # strip a trailing site-name suffix if the theme ever adds one
                title = re.sub(r"\s*[\|\-–—»]\s*CPS\b.*$", "", title, flags=re.I).strip()
        except Exception as e:
            print("  cps job err %s (%s)" % (e, slug))
            time.sleep(0.2)
            continue
        if not title:
            time.sleep(0.2)
            continue

        tl = title.lower()
        # best-effort seniority from title (EN + HE)
        if any(w in tl for w in ("student", "intern", "סטודנט", "מתמחה")):
            level = "student"
        elif any(w in tl for w in ("senior", "sr.", "sr ", "lead", "principal", "staff",
                                   "בכיר", "מנוסה",
                                   "ראש צוות", "team lead")):
            level = "senior"
        elif any(w in tl for w in ("junior", "jr.", "jr ", "entry",
                                   "ג'וניור", "גוניור",
                                   "מתחיל")):
            level = "junior"
        else:
            level = ""

        # best-effort tech tags from title
        TECH = ["python", "java", "javascript", "typescript", "c++", "c#", ".net", "golang",
                "go ", "rust", "php", "node", "react", "angular", "vue", "fullstack",
                "full stack", "full-stack", "backend", "frontend", "front end", "front-end",
                "devops", "kubernetes", "docker", "aws", "azure", "gcp", "sql", "embedded",
                "firmware", "verilog", "vlsi", "fpga", "ios", "android", "mobile", "qa",
                "automation", "data", "ml", "ai", "llm", "algorithm", "web", "cloud"]
        tech = sorted({t.strip() for t in TECH if t in tl})

        out.append({
            "source": "cps",
            "sid": slug,
            "title": title,
            "company": "",   # masked / JS-only
            "city": "",      # JS-only
            "url": url,
            "level": level,
            "years_min": None,
            "years_max": None,
            "tech": tech,
            "desc": "",      # JS-only
            "active": True,
        })
        time.sleep(0.25)

    return out


# ===== techjob (works=partial) =====
def src_techjob():
    """TechJob (techjob.co.il) open FeathersJS API adapter.

    Israeli tech job board. The public API (api.techjob.co.il/jobs) returns a
    very thin payload: only _id, _modified, title, and a mostly-empty
    siteMetaData object. company / city / description / seniority are NOT
    exposed by the API, and the SPA job page (jobs-lobby?job=<id>) is
    client-rendered so there is nothing to scrape server-side. We therefore
    return thin records, deriving level/tech best-effort from the title and
    city/tech from siteMetaData when (rarely) populated. The caller dedups
    across days and applies Ron's filters.
    """
    import requests
    import re
    import time

    API = "https://api.techjob.co.il/jobs"
    JOB_URL = "https://www.techjob.co.il/jobs-lobby?job="
    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")
    headers = {"User-Agent": UA, "Accept": "application/json",
               "Referer": "https://www.techjob.co.il/"}

    TECH_KEYS = [
        "python", "java", "javascript", "typescript", "react native", "react",
        "angular", "vue", "node.js", "nodejs", "node", ".net", "c#", "c++",
        "golang", "go", "rust", "ruby", "php", "scala", "kotlin", "swift",
        "django", "flask", "fastapi", "spring", "aws", "azure", "gcp",
        "kubernetes", "k8s", "docker", "terraform", "devops", "sql", "nosql",
        "mongodb", "postgres", "mysql", "redis", "kafka", "spark", "hadoop",
        "machine learning", "deep learning", "data science", "nlp", "llm",
        "genai", "ml", "ai", "android", "ios", "flutter", "embedded", "fpga",
        "verilog", "qa", "automation", "selenium", "cypress", "salesforce",
        "sap", "elixir", "linux", "graphql", "microservices", "cyber",
        "security", "fullstack", "full stack", "frontend", "backend",
    ]

    def guess_level(title):
        t = title.lower()
        if re.search(r"(?<![a-z])(student|intern|internship)(?![a-z])", t) \
           or "סטודנט" in title \
           or "התמחות" in title:
            return "student"
        if re.search(r"(?<![a-z])(senior|sr\.?|lead|principal|staff|expert|"
                     r"architect|head\s+of|team\s+lead|tl)(?![a-z])", t):
            return "senior"
        if re.search(r"(?<![a-z])(junior|jr\.?|entry[- ]?level)(?![a-z])", t):
            return "junior"
        return ""

    def guess_tech(title):
        t = title.lower()
        found = []
        for kw in TECH_KEYS:
            pat = r"(?<![a-z0-9])" + re.escape(kw) + r"(?![a-z0-9])"
            if re.search(pat, t):
                found.append(kw)
        seen = set()
        uniq = []
        for k in found:
            if k not in seen:
                seen.add(k)
                uniq.append(k)
        return uniq

    # ---- pull only the newest ~100 listings (4 pages of 25) ----
    records = []
    for skip in (0, 25, 50, 75):
        params = {"$sort[_modified]": "-1", "$limit": "25", "$skip": str(skip)}
        try:
            r = requests.get(API, params=params, headers=headers, timeout=20)
            if r.status_code != 200:
                continue
            data = r.json().get("data", [])
        except Exception:
            data = []
        if data:
            records.extend(data)
        try:
            time.sleep(0.3)
        except Exception:
            pass
        if len(records) >= 120:
            break

    out = []
    seen_ids = set()
    for rec in records:
        try:
            sid = rec.get("_id")
            if not sid or sid in seen_ids:
                continue
            seen_ids.add(sid)
            title = (rec.get("title") or "").strip()
            if not title:
                continue

            md = rec.get("siteMetaData") or {}
            regions = md.get("regions") if isinstance(md, dict) else None
            techs_meta = md.get("techs") if isinstance(md, dict) else None

            city = ""
            if isinstance(regions, list):
                parts = [str(x).strip() for x in regions if str(x).strip()]
                city = ", ".join(parts)

            tech = guess_tech(title)
            if isinstance(techs_meta, list):
                lowered = [x.lower() for x in tech]
                for tm in techs_meta:
                    tm = str(tm).strip()
                    if tm and tm.lower() not in lowered:
                        tech.append(tm)
                        lowered.append(tm.lower())

            out.append({
                "source": "techjob",
                "sid": str(sid),
                "title": title,
                "company": "",
                "city": city,
                "url": JOB_URL + str(sid),
                "level": guess_level(title),
                "years_min": None,
                "years_max": None,
                "tech": tech,
                "desc": "",
                "active": True,
            })
        except Exception:
            continue
        if len(out) >= 120:
            break

    return out


# ===== AllJobs (alljobs.co.il) tech-job adapter (works=yes) =====
# -*- coding: utf-8 -*-
import re, time
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote


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


# ===== comeet (works=yes) =====
def src_comeet():
    """
    Comeet adapter for Ron's Israel tech-job scanner.
    Comeet exposes a public careers JSON API per company board:
        GET https://www.comeet.co/careers-api/2.0/company/{uid}/positions?token={token}&details=true
    The (uid, token) pair is public: it is embedded in any public board page
    https://www.comeet.com/jobs/{slug}/{uid} (search the HTML for token=...).
    Adding &details=true makes each position include a top-level `details` list
    (Description / Requirements sections) so the full JD comes back in ONE call
    per company. Returns Israel (country == 'IL') tech/software roles only.
    Never raises: every network call is wrapped and partial results are returned.
    """
    import re, time
    try:
        import requests
    except Exception:
        return []
    try:
        from bs4 import BeautifulSoup
    except Exception:
        BeautifulSoup = None

    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
    HEADERS = {"User-Agent": UA, "Accept": "application/json, text/plain, */*"}

    # Registry of real Israeli companies on Comeet: (company_name, uid, token).
    # uid+token were read from the public comeet.com/jobs/{slug}/{uid} board pages.
    # These are public board tokens (not secrets); if one rotates, that board logs
    # 0 / an error in the per-board line printed on every run.
    # Giant (config.GIANTS) and referral boards FIRST; every board is requested on
    # every run (no global cap - the old CAP=120 never reached the last 8 boards).
    REGISTRY = [
        ("Samsung R&D Israel", "D4.005", "4D518291CFE13540135413544D518291CFE"),   # giant
        ("Fiverr",             "60.002", "62188018812631018862C4188"),              # giant
        ("Guideline",          "89.009", "98942BF98998939361C9B39361C9B2FAD989"),
        ("DealHub",            "86.005", "685271E6853AAD1A14D0A2099138F2DA33428"),
        ("Kela Technologies",  "2A.007", "A2747111E755B5F0513847114711A274711"),
        ("Team8",              "61.003", "16358C6EF2C61631639B558C0429"),
        ("DriveNets",          "72.006", "2769D81626762C4E762762C4EC4E1626"),
        ("VAST Data",          "43.001", "34110453411D4968234168209C31D49"),
        ("Exodigo",            "89.005", "98542A398504C28391E130A391E391E2614"),
        ("Oligo Security",     "5A.00B", "A5B487D296C487D01F1152D852D852D8487D"),
        ("Rapyd",              "73.00E", "37E11766FC1F6E11761F6E6FC01BF06FC"),
        ("Port",               "59.004", "954414C02550414C4AA01BFC12A81BFC2550"),
        ("Arpeely",            "57.001", "7512BE615F3249541D91D4415F31D4441D9EA2"),
        ("AT&T Israel",        "38.00A", "83A315C29223996399641D039963996107418AE"),
        ("Israel Tech Guard",  "29.009", "92936F65271401F125212521B7B929527136F6"),
        # added 2026-09-23 (board-discovery, verified IL positions):
        ("Earnix",             "93.00B", "39B1207AD1AD1736736120739B193D736"),
        ("Personetics",        "83.00A", "38A11B2A9E018C60153C714A9E38A"),
        ("Cellebrite",         "C3.00F", "3CF130BF3C0B6D16DA1AA9B6D130B16DA"),
        ("Cognyte",            "F2.009", "2F9EDD2F92F911D61AC12F914CF11D62F9"),
        ("Silverfort",         "54.007", "45715B315B38AE22B8D051A0A457D051E61"),
        ("Innoviz",            "52.004", "25495012A0104C012A0104C6FCBA40"),
        ("Gett",               "A0.002", "A2288A232A014432A28814432A"),
        ("Allot",              "C4.009", "4C917ED1CB699217ED04C92B11217F2B11"),
        # Moovit removed 2026-09-24: its board returns 200 with an empty list (stale token).
    ]
    GIANT_BOARDS = {"Samsung R&D Israel", "Fiverr"}   # no per-company cap for giants

    API = "https://www.comeet.co/careers-api/2.0/company/{uid}/positions?token={token}&details=true"

    TECH_RE = re.compile(
        r"\b(engineer|engineering|developer|programmer|devops|devsecops|sre|software|"
        r"back[\s-]?end|front[\s-]?end|full[\s-]?stack|data|machine\s*learning|\bml\b|\bai\b|"
        r"artificial intelligence|algorithm|algorithms|\bqa\b|automation|sdet|architect|"
        r"security|cyber|cloud|platform|infrastructure|\binfra\b|research|scientist|embedded|"
        r"firmware|hardware|asic|verification|vlsi|\bnlp\b|computer vision|analyst|"
        r"product manager|product owner|technical|python|java|golang|react|node|"
        r"network|mobile|android|test|solutions? (?:architect|engineer)|support engineer)\b",
        re.I)
    NONTECH_RE = re.compile(
        r"\b(sales|account executive|account manager|business development|\bbdr\b|\bsdr\b|"
        r"marketing|brand|content writer|copywriter|recruit|talent acquisition|\bpeople\b|"
        r"\bhr\b|human resources|finance|accountant|bookkeep|controller|payroll|legal|counsel|"
        r"office manager|receptionist|administrative|executive assistant|community manager|"
        r"customer success manager|social media|procurement)\b", re.I)
    TECH_DEPTS = ("engineering", "r&d", "research", "development", "data", "product",
                  "devops", "qa", "security", "algorithm", "infrastructure",
                  "software", "technology", "platform", "cyber")

    TECH_VOCAB = [
        "Python", "Java", "JavaScript", "TypeScript", "Go", "Golang", "C++", "C#",
        "Rust", "Scala", "Kotlin", "Swift", "Ruby", "PHP", "Elixir", "Node.js", "Node",
        "React", "React Native", "Angular", "Vue", "Next.js", "Redux", "Django", "Flask",
        "FastAPI", "Spring", ".NET", "Express", "GraphQL", "REST", "gRPC",
        "AWS", "Azure", "GCP", "Google Cloud", "Kubernetes", "K8s", "Docker", "Terraform",
        "Ansible", "Jenkins", "CI/CD", "Linux", "Bash",
        "SQL", "PostgreSQL", "MySQL", "MongoDB", "Redis", "Elasticsearch", "Cassandra",
        "Kafka", "RabbitMQ", "Spark", "Hadoop", "Airflow", "Snowflake", "BigQuery",
        "TensorFlow", "PyTorch", "Keras", "scikit-learn", "Pandas", "NumPy", "LLM", "LLMs",
        "NLP", "Computer Vision", "Machine Learning", "Deep Learning", "Generative AI", "GenAI",
        "Data Science", "MLOps", "Microservices",
        "Embedded", "FPGA", "ASIC", "VLSI", "Verilog", "SystemVerilog", "RTL", "Firmware",
        "Verification", "DSP", "PCIe", "Ethernet",
        "Cyber", "Security", "DevOps", "DevSecOps", "SRE", "QA", "Selenium", "Cypress", "Playwright",
    ]

    SENIOR_TITLE = re.compile(r"\b(senior|sr\.?|lead|principal|staff|head of|vp\b|"
                              r"director|architect|expert|manager)\b", re.I)
    JUNIOR_TITLE = re.compile(r"\b(junior|jr\.?|entry[\s-]?level|graduate|associate)\b", re.I)
    STUDENT_TITLE = re.compile(r"\b(intern|internship|student|working student|apprentice)\b", re.I)

    def classify_level(exp, title):
        e = (exp or "").strip().lower()
        if e in ("senior", "lead", "principal", "staff", "expert", "manager", "director"):
            return "senior"
        if e in ("student", "intern", "internship"):
            return "student"
        if e in ("entry-level", "entry level", "junior", "associate"):
            return "junior"
        if STUDENT_TITLE.search(title):
            return "student"
        if SENIOR_TITLE.search(title):
            return "senior"
        if JUNIOR_TITLE.search(title):
            return "junior"
        return ""

    def extract_years(text):
        if not text:
            return None, None
        t = text.lower()
        m = re.search(r"(\d{1,2})\s*(?:-|–|to|\+? ?up to)\s*(\d{1,2})\s*\+?\s*years", t)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if a <= b <= 40:
                return a, b
        m = re.search(r"(?:at least|minimum(?: of)?|min\.?|over|more than)\s*(\d{1,2})\s*\+?\s*years", t)
        if m:
            return int(m.group(1)), None
        m = re.search(r"(\d{1,2})\s*\+\s*years", t)
        if m:
            return int(m.group(1)), None
        m = re.search(r"(\d{1,2})\s*years?\s+(?:of\s+)?(?:experience|exp)", t)
        if m:
            v = int(m.group(1))
            if v <= 40:
                return v, None
        return None, None

    def extract_tech(text):
        if not text:
            return []
        low = text.lower()
        found = []
        for kw in TECH_VOCAB:
            k = kw.strip().lower()
            if len(k) <= 2:
                pat = r"(?<![a-z0-9])" + re.escape(k) + r"(?![a-z0-9])"
            elif re.match(r"^[a-z0-9]", k):
                pat = r"(?<![a-z0-9])" + re.escape(k)
            else:
                pat = re.escape(k)
            if re.search(pat, low):
                canon = kw.strip()
                if canon not in found:
                    found.append(canon)
        return found

    def html_text(html):
        if not html:
            return ""
        if BeautifulSoup is not None:
            try:
                return BeautifulSoup(html, "lxml").get_text(" ", strip=True)
            except Exception:
                pass
        return re.sub(r"<[^>]+>", " ", html)

    def is_tech(title, dept):
        dl = (dept or "").lower()
        tech = bool(TECH_RE.search(title)) or any(d in dl for d in TECH_DEPTS)
        if NONTECH_RE.search(title) and not TECH_RE.search(title):
            return False
        return tech

    PER_COMPANY = 60      # newest N tech/IL roles per board (giants: uncapped)
    jobs = []
    seen = set()
    per_board = {}

    for name, uid, token in REGISTRY:
        url = API.format(uid=uid, token=token)
        r = None
        try:
            r = requests.get(url, headers=HEADERS, timeout=25)
            data = r.json()
        except Exception as e:
            per_board[name] = "ERR %s" % ("HTTP %s" % r.status_code if r is not None else type(e).__name__)
            continue
        if not isinstance(data, list):
            per_board[name] = "ERR non-list (token rotated?)"
            continue
        # Comeet returns the whole board in one call; emulate "newest few pages"
        # by sorting on time_updated (newest first) and capping per company.
        try:
            data.sort(key=lambda p: (p.get("time_updated") or ""), reverse=True)
        except Exception:
            pass

        cap = None if name in GIANT_BOARDS else PER_COMPANY
        kept = 0
        for p in data:
            if cap is not None and kept >= cap:
                break
            if not isinstance(p, dict):
                continue
            try:
                loc = p.get("location") or {}
                if not isinstance(loc, dict):
                    loc = {}
                country = (loc.get("country") or "").strip().upper()
                if country and country != "IL":
                    continue  # keep IL (and unknown/blank country) only
                title = (p.get("name") or "").strip()
                if not title:
                    continue
                dept = p.get("department") or ""
                if not is_tech(title, dept):
                    continue

                sid = str(p.get("uid") or "").strip()
                if not sid:
                    continue
                key = ("comeet", sid)
                if key in seen:
                    continue

                desc = ""
                details = p.get("details")
                if isinstance(details, list) and details:
                    parts = []
                    for sec in details:
                        if not isinstance(sec, dict):
                            continue
                        secname = (sec.get("name") or "").strip()
                        secval = html_text(sec.get("value") or "")
                        if secval:
                            parts.append((secname + ": " + secval) if secname else secval)
                    desc = "\n".join(parts).strip()
                if not desc:
                    bits = [b for b in [dept, p.get("employment_type"),
                                        p.get("experience_level"), p.get("workplace_type")] if b]
                    desc = " | ".join(bits)
                if len(desc) > 4000:
                    desc = desc[:4000]

                company = (p.get("company_name") or name or "").strip()
                city = (loc.get("city") or "").strip()
                if not city:
                    city = (loc.get("name") or "").strip()
                url_job = (p.get("url_comeet_hosted_page") or p.get("url_active_page")
                           or p.get("url_recruit_hosted_page") or "")

                level = classify_level(p.get("experience_level"), title)
                blob = title + "\n" + desc
                ymin, ymax = extract_years(blob)
                tech = extract_tech(blob)

                jobs.append({
                    "source": "comeet",
                    "sid": sid,
                    "title": title,
                    "company": company,
                    "city": city,
                    "url": url_job,
                    "level": level,
                    "years_min": ymin,
                    "years_max": ymax,
                    "tech": tech,
                    "desc": desc,
                    "active": True,
                })
                seen.add(key)
                kept += 1
            except Exception:
                continue

        per_board[name] = "%d/%d" % (kept, len(data))
        time.sleep(0.3)

    try:
        # kept/board-size. x/0 = empty board (token rotated or board died)
        print("    comeet per-board (kept/board):", per_board)
    except Exception:
        pass
    return jobs


# ===== workday (works=yes) =====
import re, time, json, html
import requests
from bs4 import BeautifulSoup


def src_workday():
    """Generic Workday CXS adapter for Ron's referral/giant companies.

    Per brand (audit 2026-09-24, BUG 5 - the old adapter paged a GLOBAL keyword
    search and saw ~34% of NVIDIA's Israel postings):
      1. POST {searchText:'', limit:1} unfiltered and read `facets` (walking the nested
         locationMainGroup) -> every location facet value whose descriptor names Israel
         ('Israel', 'Israel, Yokneam', 'Tel Aviv-Yafo, Israel', 'Office - Israel - ...',
         'ISR-Tel Aviv ...'), grouped by facet parameter (locationHierarchy1,
         locations, Location_Country, Country, ...).
      2. For each such parameter, page {appliedFacets:{param:[ids]}, searchText:'',
         limit:20, offset} until offset >= total (total is only returned on page 1),
         union by externalPath. Every row is Israel by construction, so there is no
         multi-location probing and no country re-check.
      3. Fetch each posting's detail (JD, real city) with a per-brand budget; a row that
         misses the budget is kept with an empty desc.
    Prints "facet total vs fetched" per brand. Never raises.
    """
    import threading
    from concurrent.futures import ThreadPoolExecutor

    SOURCE = "workday"
    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

    # brand -> (tenant, wd-host, site). All confirmed live (Israel facet present).
    REGISTRY = {
        "NVIDIA":  ("nvidia",  "wd5", "NVIDIAExternalCareerSite"),
        "Intel":   ("intel",   "wd1", "External"),
        "Philips": ("philips", "wd3", "jobs-and-careers"),
        "Unity":   ("unitytech", "wd1", "Unity"),      # added 2026-09-23
        "Snyk":    ("snyk", "wd103", "External"),       # added 2026-09-23 (no IL facet today)
        # added 2026-09-24 (live-verified Israel facet rows):
        "Palo Alto Networks": ("paloaltonetworks", "wd5", "panwexternalcareers"),  # incl. CyberArk
        "Cisco":      ("cisco", "wd5", "Cisco_Careers"),
        "HP Inc":     ("hp", "wd5", "ExternalCareerSite"),
        "HPE":        ("hpe", "wd5", "Jobsathpe"),
        "Salesforce": ("salesforce", "wd12", "External_Career_Site"),
        "Marvell":    ("marvell", "wd1", "MarvellCareers"),
        "Broadcom":   ("broadcom", "wd1", "External_Career"),
    }

    LIMIT = 20                    # Workday CXS page size (max 20)
    MAX_TOTAL = 400               # per-brand row cap (runtime guard)
    MAX_DETAIL = 400              # per-brand detail-fetch cap
    BRAND_MAX = {"NVIDIA": 800}   # per-brand override of both (NVIDIA alone: ~425 IL postings)
    DETAIL_WORKERS = 4            # parallel detail GETs per brand (each paced 0.3s)

    # facet descriptor names Israel: "Israel", "Israel, Haifa", "Office - Israel - X",
    # or the ISO-3 prefix "ISR-Tel Aviv University" (Broadcom)
    IL_FACET_RX = re.compile(r"\bisrael\b|^\s*isr\b", re.I)

    # Distinctive Israeli location tokens (to pick the Israeli site of a
    # multi-location posting for the city field).
    IL_TOKENS = [
        "israel", "tel aviv", "tel-aviv", "telaviv", "haifa", "yokneam", "yoqneam",
        "jerusalem", "herzliya", "herzeliya", "hertzeliya", "raanana", "ra'anana",
        "raananna", "ra'ananna", "petah tikva", "petach tikva", "petah-tikva",
        "petah tiqwa", "rehovot", "rechovot", "netanya", "nethanya", "beer sheva",
        "be'er sheva", "beersheba", "kfar saba", "kefar sava", "hod hasharon",
        "ramat gan", "caesarea", "qesarya", "karmiel", "carmiel", "migdal haemek",
        "or yehuda", "airport city", "modiin", "modi'in", "holon", "ashdod",
        "nazareth", "kiryat gat", "kiryat", "tefen", "misgav", "yavne", "lod",
        "rosh haayin", "rosh ha'ayin", "ness ziona", "tel hai",
    ]

    TECH_PATTERNS = [
        (r"\bpython\b", "Python"), (r"\bjava\b", "Java"),
        (r"\bjavascript\b", "JavaScript"), (r"\btypescript\b", "TypeScript"),
        (r"c\+\+", "C++"), (r"\bc#\b|\.net\b", "C#/.NET"), (r"\bc\b(?!\+\+|#)", "C"),
        (r"\bgo\b|\bgolang\b", "Go"), (r"\brust\b", "Rust"),
        (r"\bkotlin\b", "Kotlin"), (r"\bswift\b", "Swift"), (r"\bruby\b", "Ruby"),
        (r"\bphp\b", "PHP"), (r"\bscala\b", "Scala"), (r"\bperl\b", "Perl"),
        (r"\bmatlab\b", "MATLAB"), (r"\bsql\b", "SQL"),
        (r"\breact\b", "React"), (r"\bangular\b", "Angular"), (r"\bvue\b", "Vue"),
        (r"\bnode(\.?js)?\b", "Node.js"), (r"\bspring\b", "Spring"),
        (r"\bdjango\b", "Django"), (r"\bflask\b", "Flask"), (r"\bfastapi\b", "FastAPI"),
        (r"\bkubernetes\b|\bk8s\b", "Kubernetes"), (r"\bdocker\b", "Docker"),
        (r"\bterraform\b", "Terraform"), (r"\bansible\b", "Ansible"),
        (r"\baws\b", "AWS"), (r"\bgcp\b|google cloud", "GCP"), (r"\bazure\b", "Azure"),
        (r"\blinux\b", "Linux"), (r"\bembedded\b", "Embedded"), (r"\brtos\b", "RTOS"),
        (r"\bverilog\b", "Verilog"), (r"\bsystemverilog\b", "SystemVerilog"),
        (r"\bvhdl\b", "VHDL"), (r"\bfpga\b", "FPGA"), (r"\basic\b", "ASIC"),
        (r"\bcuda\b", "CUDA"), (r"\bopencl\b", "OpenCL"),
        (r"\bpytorch\b", "PyTorch"), (r"\btensorflow\b", "TensorFlow"),
        (r"\bkeras\b", "Keras"), (r"scikit", "scikit-learn"),
        (r"\bpandas\b", "pandas"), (r"\bnumpy\b", "NumPy"),
        (r"\bspark\b", "Spark"), (r"\bhadoop\b", "Hadoop"), (r"\bkafka\b", "Kafka"),
        (r"\bmongodb\b", "MongoDB"), (r"\bpostgres(ql)?\b", "PostgreSQL"),
        (r"\bmysql\b", "MySQL"), (r"\bredis\b", "Redis"),
        (r"\belasticsearch\b", "Elasticsearch"), (r"\bgraphql\b", "GraphQL"),
        (r"\bgrpc\b", "gRPC"), (r"\bmicroservices?\b", "Microservices"),
        (r"ci/cd|ci-cd", "CI/CD"), (r"\bgit\b", "Git"), (r"\bjenkins\b", "Jenkins"),
        (r"machine learning|\bml\b", "Machine Learning"),
        (r"deep learning", "Deep Learning"), (r"\bnlp\b", "NLP"),
        (r"computer vision", "Computer Vision"), (r"\bllms?\b|large language model", "LLM"),
        (r"gen ?ai|generative ai", "GenAI"),
    ]

    HDRS = {"User-Agent": UA, "Accept": "application/json",
            "Content-Type": "application/json"}
    sess = requests.Session()
    sess.headers.update(HDRS)
    _tl = threading.local()

    def _tsess():
        # one Session per detail worker thread (Session is not guaranteed thread-safe)
        s = getattr(_tl, "s", None)
        if s is None:
            s = requests.Session()
            s.headers.update(HDRS)
            _tl.s = s
        return s

    def _log(msg):
        try:
            print("    workday " + msg)
        except Exception:
            pass

    def _looks_israeli(text):
        t = (text or "").lower()
        return any(tok in t for tok in IL_TOKENS)

    def _is_multi(loc_text):
        return bool(re.search(r"\d+\s+location", (loc_text or "").lower()))

    def _city_from(loc):
        # "Israel, Yokneam" -> Yokneam; "Tel Aviv-Yafo, Israel" -> Tel Aviv-Yafo;
        # "Ness Ziona, Center District, Israel" -> Ness Ziona, Center District;
        # "Office - Israel - Tel Aviv" -> Tel Aviv; "ISR-Tel Aviv University" ->
        # Tel Aviv University; "IL - Petah Tikva" -> Petah Tikva.
        if not loc:
            return ""
        loc = re.sub(r"\s+", " ", str(loc)).strip()
        if _is_multi(loc):
            return ""
        stripped = re.sub(r"^(?:\s*(?:office|israel|isr|il)\s*-\s*)+", "", loc, flags=re.I).strip()
        if stripped and stripped.lower() not in ("home based", "remote"):
            loc = stripped
        parts = [p.strip() for p in loc.split(",") if p.strip()]
        keep = [p for p in parts if p.lower() != "israel"]
        return ", ".join(keep) if keep else loc

    def _clean_text(htmltext):
        if not htmltext:
            return ""
        try:
            txt = BeautifulSoup(htmltext, "lxml").get_text(" ")
        except Exception:
            txt = re.sub(r"<[^>]+>", " ", htmltext)
        txt = html.unescape(txt)
        txt = txt.replace("�", " ")
        txt = re.sub(r"\s+", " ", txt).strip()
        return txt

    def _extract_years(text):
        # Only trust a "N years" number when "experience" is nearby, otherwise
        # marketing boilerplate ("more than 25 years of innovation") pollutes it.
        t = (text or "").lower()
        if not t:
            return (None, None)

        def _near_experience(start, end):
            ctx = t[max(0, start - 45):min(len(t), end + 45)]
            return "experien" in ctx or "exp." in ctx

        # range: "3-5 years" / "3 to 5 years"
        for m in re.finditer(r"(\d{1,2})\s*(?:[-–]|to)\s*(\d{1,2})\s*\+?\s*years?", t):
            a, b = int(m.group(1)), int(m.group(2))
            if 0 <= a <= 40 and a <= b <= 40 and _near_experience(m.start(), m.end()):
                return (a, b)
        # "5+ years"
        for m in re.finditer(r"(\d{1,2})\s*\+\s*years?", t):
            a = int(m.group(1))
            if 0 <= a <= 40 and _near_experience(m.start(), m.end()):
                return (a, None)
        # "at least/minimum/over N years"
        for m in re.finditer(r"(?:at least|minimum(?: of)?|min\.?|over|more than)\s*(\d{1,2})\s*years?", t):
            a = int(m.group(1))
            if 0 <= a <= 40 and _near_experience(m.start(), m.end()):
                return (a, None)
        # bare "N years" but only if next to "experience"
        for m in re.finditer(r"(\d{1,2})\s*years?", t):
            a = int(m.group(1))
            if 0 <= a <= 40 and _near_experience(m.start(), m.end()):
                return (a, None)
        return (None, None)

    def _extract_level(title, desc, years_min, years_max):
        # Decide from the TITLE first; the description is boilerplate-heavy
        # ("internship programs", etc.) and misleads a keyword scan.
        tl = title.lower()
        if re.search(r"\b(intern|interns|internship|student|working student|co-?op)\b", tl):
            return "student"
        if re.search(r"\b(senior|sr\.?|staff|principal|lead|expert|architect|fellow|director|distinguished)\b", tl):
            return "senior"
        if re.search(r"\b(junior|jr\.?|entry[- ]level|new grad|graduate|early career)\b", tl):
            return "junior"
        if years_min is not None and years_min >= 5:
            return "senior"
        if years_max is not None and years_max <= 2:
            return "junior"
        if years_min is not None and years_min <= 1 and (years_max is None or years_max <= 2):
            return "junior"
        return ""

    def _extract_tech(text):
        t = (text or "").lower()
        found = []
        for pat, label in TECH_PATTERNS:
            if label in found:
                continue
            try:
                if re.search(pat, t):
                    found.append(label)
            except re.error:
                continue
        return found

    def _walk_facets(facets):
        # yields (facetParameter, id, descriptor, count) for every leaf value, descending
        # into nested groups such as locationMainGroup -> locationHierarchy1/locations
        # (count = the value's posting count, 0 when the tenant doesn't report it)
        for f in facets or []:
            if not isinstance(f, dict):
                continue
            param = f.get("facetParameter") or ""
            for v in f.get("values") or []:
                if not isinstance(v, dict):
                    continue
                if "values" in v and "facetParameter" in v:
                    for x in _walk_facets([v]):
                        yield x
                    continue
                try:
                    cnt = int(v.get("count") or 0)
                except Exception:
                    cnt = 0
                yield param, v.get("id"), (v.get("descriptor") or ""), cnt

    def _post(base, facets, offset, limit):
        body = {"appliedFacets": facets, "limit": limit, "offset": offset, "searchText": ""}
        for attempt in range(2):
            try:
                r = sess.post(base, data=json.dumps(body), timeout=25)
                time.sleep(0.3)
                if r.status_code == 200 and "json" in r.headers.get("content-type", ""):
                    return r.json()
            except Exception:
                pass
            time.sleep(1.0 + attempt)
        return None

    def _fetch_detail(tenant, wd, site, ext):
        url = f"https://{tenant}.{wd}.myworkdayjobs.com/wday/cxs/{tenant}/{site}{ext}"
        for attempt in range(2):
            try:
                r = _tsess().get(url, timeout=20)
                time.sleep(0.3)
                if r.status_code == 200 and "json" in r.headers.get("content-type", ""):
                    return r.json().get("jobPostingInfo", {}) or {}
            except Exception:
                pass
            time.sleep(0.8)
        return None

    results = {}   # externalPath -> row dict (dedupe)

    for brand, (tenant, wd, site) in REGISTRY.items():
        try:
            base = f"https://{tenant}.{wd}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"
            pub_base = f"https://{tenant}.{wd}.myworkdayjobs.com/en-US/{site}"
            cap = BRAND_MAX.get(brand, MAX_TOTAL)
            det_cap = BRAND_MAX.get(brand, MAX_DETAIL)

            # 1) discover this tenant's Israel location facet ids
            j0 = _post(base, {}, 0, 1)
            if not j0:
                _log("%s: facet discovery request FAILED -> 0" % brand)
                continue
            global_total = j0.get("total") or 0
            cands = {}   # facetParameter -> [(id, descriptor, count)]
            for param, fid, desc, cnt in _walk_facets(j0.get("facets")):
                if param and fid and IL_FACET_RX.search(desc):
                    cands.setdefault(param, []).append((fid, desc, cnt))
            if not cands:
                _log("%s: no Israel location facet (global %d) -> 0" % (brand, global_total))
                continue
            il_descs = [d for vals in cands.values() for _, d, _ in vals]

            # 2) page every Israel facet parameter until offset >= total
            listed = {}          # ext -> posting (dedupe across parameters)
            facet_total = 0
            for param, vals in cands.items():
                facets = {param: [fid for fid, _, _ in vals]}
                il_count = sum(c for _, _, c in vals)   # what the Israel values say they hold
                offset, total = 0, None
                while len(listed) < cap:
                    jj = _post(base, facets, offset, LIMIT)
                    if jj is None:
                        _log("%s: page offset %d of %s FAILED" % (brand, offset, param))
                        break
                    if total is None:
                        total = jj.get("total") or 0     # only page 1 carries the total
                        # the server ignored the facet (returned the whole tenant) only when the
                        # Israel values themselves hold fewer postings than the tenant: an
                        # Israel-only tenant legitimately has total == global and is kept
                        if total >= global_total and 0 < il_count < global_total:
                            _log("%s: facet %s ignored by server (total %d = global, Israel %d) -> skipped"
                                 % (brand, param, total, il_count))
                            total = 0
                            break
                    postings = jj.get("jobPostings") or []
                    if not postings:
                        break
                    for p in postings:
                        ext = p.get("externalPath") or ""
                        if ext and ext not in listed:
                            listed[ext] = p
                    offset += LIMIT
                    if total and offset >= total:
                        break
                    if (not total and len(postings) < LIMIT) or offset > 5000:
                        break
                facet_total = max(facet_total, total or 0)

            # 3) detail fetch (JD + real city) within the per-brand budget
            exts = list(listed.keys())[:cap]
            to_detail = exts[:det_cap]
            details = {}
            if to_detail:
                with ThreadPoolExecutor(max_workers=DETAIL_WORKERS) as ex:
                    for ext, det in zip(to_detail, ex.map(
                            lambda e: _fetch_detail(tenant, wd, site, e), to_detail)):
                        details[ext] = det

            n_desc = 0
            for ext in exts:
                p = listed[ext]
                title = (p.get("title") or "").strip()
                if not title:
                    continue
                loc_text = (p.get("locationsText") or "").strip()
                detail = details.get(ext)
                locs = []
                desc = ""
                url_final = f"{pub_base}{ext}"
                if detail:
                    locs = [detail.get("location") or ""] + list(detail.get("additionalLocations") or [])
                    desc = _clean_text(detail.get("jobDescription"))
                    if detail.get("externalUrl"):
                        url_final = detail["externalUrl"]
                locs.append(loc_text)
                # the Israeli site of a (possibly multi-location) posting
                il_loc = (next((l for l in locs if l and IL_FACET_RX.search(l)), "")
                          or next((l for l in locs if l and not _is_multi(l) and _looks_israeli(l)), ""))
                if not il_loc:
                    il_loc = il_descs[0] if len(il_descs) == 1 else "Israel"
                city = _city_from(il_loc) or "Israel"
                if desc:
                    n_desc += 1

                company = brand
                if brand == "Palo Alto Networks" and any("cyberark" in (l or "").lower() for l in locs):
                    company = "Palo Alto Networks (CyberArk)"

                years_min, years_max = _extract_years(desc) if desc else (None, None)
                level = _extract_level(title, desc, years_min, years_max)
                tech = _extract_tech((title + " " + desc) if desc else title)

                results[ext] = {
                    "source": SOURCE,
                    "sid": ext,
                    "title": title,
                    "company": company,
                    "city": city,
                    "url": url_final,
                    "level": level,
                    "years_min": years_min,
                    "years_max": years_max,
                    "tech": tech,
                    "desc": desc[:2500],
                    "active": True,
                }
            _log("%s: facet total %d vs fetched %d (with JD %d)%s"
                 % (brand, facet_total, len(exts), n_desc,
                    "  CAP HIT" if len(listed) >= cap else ""))
        except Exception as e:
            # never raise: keep whatever we already collected
            _log("%s: ERROR %s" % (brand, e))
            continue

    return list(results.values())


# ===== apple (works=yes) =====
# -*- coding: utf-8 -*-
def src_apple():
    """Apple careers -> Israel tech/software roles (jobs.apple.com).

    Israel is selected via the public search route ?location=israel-ISR (the
    /en-il/ prefix is only display locale, NOT a country filter). Apple's site is
    a React app that server-renders each page with the full result set embedded in
    `window.__staticRouterHydrationData = JSON.parse("...")`; we pull the newest few
    pages, extract that JSON, and read the job records straight out of it (no CSRF /
    POST needed). bs4 fallback scrapes the rendered cards if the blob ever moves.
    """
    import re, json, time, html as _html
    import requests
    from bs4 import BeautifulSoup

    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
    BASE = "https://jobs.apple.com"
    SEARCH = BASE + "/en-il/search?location=israel-ISR&sort=newest&page=%d"
    PAGE_SIZE = 20
    MAX_PAGES = 15         # hard ceiling; the real page count is ceil(totalRecords/20)+1
    FALLBACK_PAGES = 6     # used only if page 1 carries no totalRecords
    CAP = 300

    SENIOR = ("senior", "sr.", "sr ", " lead", "lead ", "principal", "staff",
              "architect", "manager", "head of", "director", "chief", " vp", "expert")
    JUNIOR = ("junior", "jr.", "jr ", "entry", "associate", "new grad",
              "new-grad", "graduate")
    TECH_KW = ["python", "java", "javascript", "typescript", "c++", "c#", "swift",
               "objective-c", "kotlin", "go ", "golang", "rust", "scala", "ruby",
               ".net", "node", "react", "angular", "vue", "django", "flask",
               "spring", "kubernetes", "docker", "aws", "gcp", "azure", "sql",
               "nosql", "spark", "kafka", "linux", "embedded", "firmware", "rtos",
               "verilog", "systemverilog", "machine learning", "deep learning",
               "pytorch", "tensorflow", "llm", "genai", "nlp", "computer vision",
               "devops", "ci/cd", "graphql", "rest", "microservices", "wifi",
               "bluetooth", "silicon", "soc", "fpga", "matlab"]

    s = requests.Session()
    s.headers.update({"User-Agent": UA,
                      "Accept": "text/html,application/xhtml+xml",
                      "Accept-Language": "en-US,en;q=0.9"})

    def level_of(title):
        t = " " + (title or "").lower() + " "
        if _is_student_title(title) or any(w in t for w in ("working student", "co op")):
            return "student"     # word-bound: 'intern' must not hit "Internal ..."
        if any(w in t for w in SENIOR):
            return "senior"
        if any(w in t for w in JUNIOR):
            return "junior"
        return ""

    def years_of(text):
        t = (text or "").lower()
        mn = mx = None
        m = re.search(r'(\d{1,2})\s*(?:-|to|–)\s*(\d{1,2})\s*\+?\s*years?', t)
        if m:
            mn, mx = int(m.group(1)), int(m.group(2))
        else:
            m = re.search(r'(\d{1,2})\s*\+\s*years?', t)
            if m:
                mn = int(m.group(1))
            else:
                m = re.search(r'(\d{1,2})\s*years?', t)
                if m:
                    mn = int(m.group(1))
        if mn is not None and mn > 30:
            mn = None
        if mx is not None and mx > 40:
            mx = None
        return mn, mx

    def tech_of(text):
        t = (text or "").lower()
        seen = set(); out = []
        for kw in TECH_KW:
            k = kw.strip()
            if k in seen:
                continue
            if re.fullmatch(r'[a-z0-9 ]+', k):     # wordy kw -> word-boundary match
                hit = re.search(r'(?<![a-z0-9])' + re.escape(k) + r'(?![a-z0-9])', t)
            else:                                   # symbol kw (c++, c#, .net) -> substring
                hit = k in t
            if hit:
                seen.add(k); out.append(k)
        return out[:12]

    def parse_hydration(page_html):
        """-> (searchResults list or None, totalRecords int or None)"""
        m = re.search(r'window\.__staticRouterHydrationData\s*=\s*JSON\.parse\("(.*?)"\);',
                      page_html, re.S)
        if not m:
            return None, None
        try:
            data = json.loads(json.loads('"' + m.group(1) + '"'))
        except Exception:
            return None, None
        try:
            srch = data["loaderData"]["search"]
        except Exception:
            return None, None
        total = srch.get("totalRecords") if isinstance(srch, dict) else None
        try:
            total = int(total) if total is not None else None
        except Exception:
            total = None
        try:
            return srch["searchResults"], total
        except Exception:
            return None, total

    def rec_to_job(rec):
        try:
            pid = str(rec.get("positionId") or rec.get("id") or "")
            if not pid:
                return None
            title = (rec.get("postingTitle") or rec.get("transformedPostingTitle") or "").strip()
            locs = rec.get("locations") or []
            city = ""
            for l in locs:
                if not isinstance(l, dict):
                    continue
                c = (l.get("city") or "").strip()
                if not c:
                    nm = (l.get("name") or "").strip()
                    # skip bare country names, keep city-like names
                    c = "" if nm.lower() in ("israel", "") else nm
                if c:
                    city = c
                    break
            slug = rec.get("transformedPostingTitle") or ""
            url = "%s/en-il/details/%s%s" % (BASE, pid, ("/" + slug if slug else ""))
            desc = _html.unescape((rec.get("jobSummary") or "").strip())
            team = ((rec.get("team") or {}).get("teamName") or "").strip()
            blob = title + " \n " + desc + " \n " + team
            ymin, ymax = years_of(desc)
            return {
                "source": "apple",
                "sid": pid,
                "title": title,
                "company": "Apple",
                "city": city,
                "url": url,
                "level": level_of(title),
                "years_min": ymin,
                "years_max": ymax,
                "tech": tech_of(blob),
                "desc": desc,
                "active": True,
            }
        except Exception:
            return None

    def scrape_cards(page_html):
        """bs4 fallback: read visible result cards if the hydration blob is gone."""
        out = []
        try:
            soup = BeautifulSoup(page_html, "lxml")
        except Exception:
            return out
        for a in soup.select('a[href*="/details/"]'):
            href = a.get("href") or ""
            m = re.search(r'/details/(\d+)(?:/([^/?#]+))?', href)
            if not m:
                continue
            pid, slug = m.group(1), (m.group(2) or "")
            title = a.get_text(" ", strip=True)
            if not title:
                continue
            url = href if href.startswith("http") else BASE + href
            out.append({
                "source": "apple", "sid": pid, "title": title, "company": "Apple",
                "city": "", "url": url, "level": level_of(title),
                "years_min": None, "years_max": None, "tech": tech_of(title),
                "desc": "", "active": True,
            })
        return out

    def fetch_page(pg):
        """-> (page_jobs, totalRecords or None). Never raises."""
        try:
            r = s.get(SEARCH % pg, timeout=30)
            r.encoding = "utf-8"
            page_html = r.text
        except Exception:
            return [], None
        recs, total = parse_hydration(page_html)
        page_jobs = []
        if recs:
            for rec in recs:
                j = rec_to_job(rec)
                if j:
                    page_jobs.append(j)
        else:
            page_jobs = scrape_cards(page_html)
        return page_jobs, total

    # Page count comes from page 1's totalRecords (Israel had 110 = 6 pages when the old
    # fixed MAX_PAGES=5 cut it). Apple randomly serves ~25-40% of page loads EMPTY
    # (totalRecords=0; measured live 2026-09-24, any page, any session). Such a page is
    # retried with backoff, skipped if it stays empty, and retried again after the main
    # pass - it no longer ends the whole run at ~15 roles (audit BUG 21).
    RETRIES = 4
    jobs = []
    seen_ids = set()

    def add(page_jobs):
        new = 0
        for j in page_jobs:
            if j["sid"] in seen_ids:
                continue
            seen_ids.add(j["sid"])
            jobs.append(j)
            new += 1
        return new

    total_records = None
    last_page = FALLBACK_PAGES
    pg = 1
    empty_pages = []
    while pg <= min(last_page, MAX_PAGES) and len(jobs) < CAP:
        expected = pg == 1 or pg < last_page   # the +1 page past the end may be empty
        page_jobs, total = fetch_page(pg)
        tries = 0
        while not page_jobs and expected and tries < RETRIES:
            tries += 1
            time.sleep(1.0 * tries)
            page_jobs, total = fetch_page(pg)
        if total_records is None and total:
            total_records = total
            last_page = min(MAX_PAGES, -(-total_records // PAGE_SIZE) + 1)
        if not page_jobs:
            if pg == 1:                 # page 1 empty after retries -> site down/blocked
                break
            if pg < last_page:
                empty_pages.append(pg)
        new = add(page_jobs)
        # no totalRecords known and nothing new -> past the end
        if total_records is None and new == 0 and pg > 1:
            break
        pg += 1
        time.sleep(0.35)
    # second pass over pages that stayed empty
    still_empty = []
    for epg in empty_pages:
        page_jobs = []
        for tries in range(3):
            time.sleep(2.0)
            page_jobs, _ = fetch_page(epg)
            if page_jobs:
                break
        if page_jobs:
            add(page_jobs)
        else:
            still_empty.append(epg)
    jobs = jobs[:CAP]
    try:
        print("    apple: totalRecords %s, pages %d, fetched %d%s"
              % (total_records, min(last_page, MAX_PAGES), len(jobs),
                 (", pages still EMPTY after retries %s" % still_empty) if still_empty else ""))
    except Exception:
        pass
    return jobs


# ===== Camtek careers adapter (+ PwC Israel bonus) (works=yes) =====
# -*- coding: utf-8 -*-
import re, time, requests
from bs4 import BeautifulSoup

def src_camtek():
    """
    Camtek careers adapter (+ best-effort bonus: PwC Israel).
    Palo Alto Networks moved to src_workday 2026-09-24 (tenant paloaltonetworks /
    panwexternalcareers, Israel location facet = every IL posting incl. CyberArk);
    the old Phenom keyword search here saw 14 of ~150 Israel rows.
    Each company has its own cap. Returns a list of normalized job dicts. Never raises.
    """
    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
    HDRS = {"User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9"}
    out = []
    CAMTEK_CAP = 120
    PWC_CAP = 120

    def _get(url, timeout=25):
        return requests.get(url, headers=HDRS, timeout=timeout, allow_redirects=True)

    def _level(title, desc=""):
        # title-driven only: JD text ("we hire students", "3 years") gives false positives.
        # Word-bound: 'intern' must not hit "Internal Audit" / "Linux Internals".
        t = title.lower()
        if re.search(r"\b(student|intern(ship)?s?)\b", t) or "סטודנט" in t:
            return "student"
        if any(w in t for w in ("senior", "sr.", "sr ", " lead", "lead ", "principal",
                                "staff", "architect", "manager", "head of", "director",
                                "team lead", "expert", " vp", "vp ", "chief")):
            return "senior"
        if any(w in t for w in ("junior", "jr.", "jr ", "entry", "graduate")):
            return "junior"
        return ""

    def _years(text):
        t = (text or "").lower().replace("–", "-").replace("—", "-")
        ymin = ymax = None
        m = re.search(r'(\d{1,2})\s*(?:-|to|up to)\s*(\d{1,2})\s*\+?\s*(?:years|yrs|year)', t)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            ymin, ymax = min(a, b), max(a, b)
        else:
            singles = [int(x) for x in re.findall(r'(\d{1,2})\s*\+?\s*(?:years|yrs|year)', t)]
            singles = [s for s in singles if s <= 30]
            if singles:
                ymin = min(singles)
        return ymin, ymax

    TECHKW = ["python", "c++", "c#", ".net", "java", "javascript", "typescript", "react",
              "angular", "vue", "node", "sql", "nosql", "mongodb", "aws", "azure", "gcp",
              "docker", "kubernetes", "k8s", "tensorrt", "onnx", "pytorch", "tensorflow",
              "keras", "opencv", "cuda", "machine learning", "deep learning", "ml", "ai",
              "llm", "nlp", "computer vision", "embedded", "firmware", "rtos", "linux",
              "go ", "golang", "rust", "matlab", "verilog", "vhdl", "fpga", "qa",
              "automation", "selenium", "cypress", "rest", "microservices", "spark",
              "kafka", "algorithms", "image processing", "devops", "ci/cd"]

    def _tech(text, extra=None):
        t = (text or "").lower()
        found = []
        for k in TECHKW:
            if k in t and k.strip() not in found:
                found.append(k.strip())
        if extra:
            for e in extra:
                e = (e or "").strip()
                if e and e.lower() not in [f.lower() for f in found]:
                    found.append(e)
        return found[:15]

    # ---------------- 1) CAMTEK (primary) ----------------
    # Single listing page: div.item.read-more-click -> h3.title / p.department /
    # p.location / a[href] (code = last URL path segment). Then enrich each role
    # from its own /open-positions/{code}/ page (small co -> only ~29 requests).
    try:
        r = _get("https://www.camtek.com/careers/open-positions/")
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "lxml")
            items = soup.select("div.item.read-more-click")
            for it in items:
                if len(out) >= CAMTEK_CAP:
                    break
                try:
                    a = it.find("a", href=True)
                    if not a:
                        continue
                    url = a["href"].strip()
                    if url.startswith("/"):
                        url = "https://www.camtek.com" + url
                    code = url.rstrip("/").rsplit("/", 1)[-1]
                    ttl = it.select_one("h3.title") or it.select_one(".title")
                    dep = it.select_one("p.department") or it.select_one(".department")
                    loc = it.select_one("p.location") or it.select_one(".location")
                    title = ttl.get_text(" ", strip=True) if ttl else ""
                    dept = dep.get_text(" ", strip=True) if dep else ""
                    city = loc.get_text(" ", strip=True) if loc else ""
                    if not title:
                        continue
                    desc = ""
                    # enrich with the individual role page (small company -> cheap)
                    try:
                        d = _get(url, timeout=20)
                        if d.status_code == 200:
                            ds = BeautifulSoup(d.text, "lxml")
                            art = ds.select_one("article") or ds.select_one("div.main")
                            if art:
                                txt = art.get_text(" ", strip=True)
                                txt = re.sub(r'^\s*Back to Careers\s*', '', txt)
                                desc = re.sub(r'\s+', ' ', txt)[:1500]
                        time.sleep(0.25)
                    except Exception:
                        pass
                    ymin, ymax = _years(desc)
                    out.append({
                        "source": "camtek", "sid": code, "title": title, "company": "Camtek",
                        "city": city, "url": url, "level": _level(title, desc),
                        "years_min": ymin, "years_max": ymax,
                        "tech": _tech(title + " " + desc, extra=[dept] if dept else None),
                        "desc": desc, "active": True,
                    })
                except Exception:
                    continue
    except Exception:
        pass
    n_camtek = len(out)

    # ---------------- 2) PwC ISRAEL (bonus, best-effort) ----------------
    # PwC Israel has no clean public JSON/HTML job board (postings live on LinkedIn / a
    # gated Hebrew ATS). We probe a couple of candidate pages; if none expose a parseable
    # list we simply return nothing for PwC. Never raises.
    pwc = []
    try:
        pwc_urls = [
            "https://www.pwc.com/il/en/careers/open-positions.html",
            "https://www.pwc.com/il/en/careers/job-openings.html",
        ]
        for u in pwc_urls:
            if len(pwc) >= PWC_CAP:
                break
            try:
                r = _get(u, timeout=20)
                if r.status_code != 200:
                    continue
                soup = BeautifulSoup(r.text, "lxml")
                cards = soup.select("a[href*='job'], li.job, div.job-item, .position")
                for c in cards:
                    if len(pwc) >= PWC_CAP:
                        break
                    title = c.get_text(" ", strip=True)
                    href = c.get("href", "")
                    if not title or len(title) < 4 or not href:
                        continue
                    if href.startswith("/"):
                        href = "https://www.pwc.com" + href
                    sid = href.rstrip("/").rsplit("/", 1)[-1][:40]
                    pwc.append({
                        "source": "pwc", "sid": sid, "title": title, "company": "PwC Israel",
                        "city": "", "url": href, "level": _level(title),
                        "years_min": None, "years_max": None, "tech": _tech(title),
                        "desc": "", "active": True,
                    })
                if pwc:
                    break
            except Exception:
                continue
    except Exception:
        pass
    out.extend(pwc)

    try:
        print("    camtek per-company: Camtek %d, PwC %d" % (n_camtek, len(pwc)))
    except Exception:
        pass
    return out



# ===== Lever (open JSON API) — added 2026-09-23 =====
def src_lever():
    """Lever public postings API: GET {host}/v0/postings/{slug}?mode=json -> JSON array.
    Registry of Israeli-employer Lever boards, each with its own API host (Lever's EU
    instance api.eu.lever.co hosts e.g. Mobileye; the US api.lever.co 404s for it).
    Filter to Israel by country / categories.location / allLocations. A failed board is
    logged (slug + status/exception), never silently skipped. Never raises."""
    import json, re, time, urllib.request, urllib.error
    UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    # slug -> (API host, company name). Grows as more Israeli Lever boards are confirmed.
    BOARDS = {
        "walkme":   ("api.lever.co", "walkme"),
        "mobileye": ("api.eu.lever.co", "Mobileye"),    # giant; added 2026-09-24 (~147 IL roles)
    }
    ILC = ("israel", "tel aviv", "tel-aviv", "herzliya", "haifa", "yokneam", "ramat", "netanya",
           "petah", "raanana", "kfar", "jerusalem", "beer", "hod hasharon", "caesarea")
    out = []
    per_board = {}
    for slug, (host, company) in BOARDS.items():
        try:
            req = urllib.request.Request("https://%s/v0/postings/%s?mode=json" % (host, slug),
                                         headers={"User-Agent": UA, "Accept": "application/json"})
            arr = json.loads(urllib.request.urlopen(req, timeout=30).read().decode("utf-8"))
            if not isinstance(arr, list):
                raise ValueError("non-list response")
        except urllib.error.HTTPError as e:
            per_board[slug] = "FAILED HTTP %s" % e.code
            continue
        except Exception as e:
            per_board[slug] = "FAILED %s" % (type(e).__name__)
            continue
        n = 0
        for p in arr:
            try:
                cats = p.get("categories", {}) or {}
                loc = cats.get("location") or ""
                all_locs = " | ".join(cats.get("allLocations") or [])
                if not ((p.get("country") or "").upper() == "IL"
                        or any(k in (loc + " | " + all_locs).lower() for k in ILC)):
                    continue
                if not any(k in loc.lower() for k in ILC):
                    # primary site abroad, Israel only in allLocations -> show the IL site
                    loc = next((l for l in (cats.get("allLocations") or [])
                                if any(k in l.lower() for k in ILC)), loc)
                desc = re.sub("<[^>]+>", " ", (p.get("descriptionPlain") or p.get("description") or ""))
                # requirements (the years) live in `lists`, not in the description
                for lst in (p.get("lists") or []):
                    body = re.sub("<[^>]+>", " ", (lst.get("content") or ""))
                    desc += "\n" + (lst.get("text") or "") + ": " + body
                desc = re.sub(r"[ \t]+", " ", desc).strip()
                out.append({"source": "lever:" + slug, "sid": p.get("id", ""), "title": p.get("text", ""),
                            "company": company, "city": loc, "url": p.get("hostedUrl", ""),
                            "level": "", "years_min": None, "years_max": None, "tech": [],
                            "desc": desc[:3000], "active": True})
                n += 1
            except Exception:
                continue
        per_board[slug] = n
        time.sleep(0.2)
    try:
        print("    lever per-board:", per_board)
    except Exception:
        pass
    return out


# ===== Scrape adapters added 2026-09-23 (career-site scrapers; requests+bs4) =====

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

def src_lemonade():
    """Lemonade careers (makers.lemonade.com) -> Israel tech/software roles.
    Jobs are embedded in the Next.js __NEXT_DATA__ JSON blob on the careers page
    (props.pageProps.allRecipes). No pagination; the whole roster ships in one page."""
    import json, re, time, random
    try:
        import requests
    except Exception:
        return []
    try:
        from bs4 import BeautifulSoup
    except Exception:
        BeautifulSoup = None

    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
    HEADERS = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9",
               "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}

    # ---- helpers -----------------------------------------------------------
    def _html_to_text(html):
        if not html:
            return ""
        try:
            if BeautifulSoup is not None:
                return BeautifulSoup(html, "lxml").get_text("\n", strip=True)
        except Exception:
            pass
        # stdlib fallback
        txt = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
        txt = re.sub(r"(?is)<br\s*/?>", "\n", txt)
        txt = re.sub(r"(?is)</p>", "\n", txt)
        txt = re.sub(r"(?s)<[^>]+>", " ", txt)
        import html as _h
        txt = _h.unescape(txt)
        return re.sub(r"[ \t]+", " ", txt).strip()

    def _level(title):
        t = (title or "").lower()
        # student: word-bound title test ('intern' no longer hits "Internal ...");
        # 'graduate' is a junior signal, never student
        if _is_student_title(title) or re.search(r"\bapprentice", t):
            return "student"
        if any(k in t for k in ("senior", "sr.", "sr ", " staff", "staff ", "principal",
                                "lead", "director", "head of", "vp ", "chief", "manager",
                                "architect")):
            return "senior"
        if any(k in t for k in ("junior", "jr.", "jr ", "entry level", "entry-level",
                                "graduate")):
            return "junior"
        return ""

    def _years(text):
        if not text:
            return (None, None)
        low = text.lower()
        # range: "3-5 years"
        m = re.search(r"(\d{1,2})\s*[-–to]{1,4}\s*(\d{1,2})\s*\+?\s*years?", low)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if a <= b <= 40:
                return (a, b)
        # "3+ years" / "at least 3 years" / "3 years of experience"
        m = re.search(r"(?:at least|minimum(?: of)?|min\.?)\s*(\d{1,2})\s*\+?\s*years?", low)
        if not m:
            m = re.search(r"(\d{1,2})\s*\+\s*years?", low)
        if not m:
            m = re.search(r"(\d{1,2})\s*years?\s+of\s+(?:experience|software|hands|professional|relevant|industry|backend|back-end)", low)
        if m:
            a = int(m.group(1))
            if 0 <= a <= 40:
                return (a, None)
        return (None, None)

    # canonical label -> list of patterns to look for (matched with boundaries)
    TECH_TERMS = [
        "python", "java", "javascript", "typescript", "node.js", "react native",
        "react", "angular", "vue", "ruby on rails", "ruby", "rails", "golang",
        "rust", "c++", "c#", ".net", "scala", "kotlin", "swift", "php", "elixir",
        "kubernetes", "docker", "terraform", "aws", "azure", "gcp", "google cloud",
        "graphql", "grpc", "kafka", "spark", "airflow", "snowflake",
        "postgresql", "postgres", "mysql", "mongodb", "redis", "dynamodb", "nosql",
        "sql", "elasticsearch", "microservices", "ci/cd", "machine learning",
        "genai", "llm", "llms", "pytorch", "tensorflow", "data warehouse", "etl",
        "dbt", "sagemaker", "linux", "bigquery", "hadoop", "pandas", "numpy",
        "infrastructure-as-code", "devops", "sre", "observability", "ml platform",
        "kubernetes", "rest api", "restful",
    ]

    def _tech(text):
        if not text:
            return []
        low = text.lower()
        found = []
        for term in TECH_TERMS:
            # boundary that treats +, #, . as part of the token (not word chars)
            pat = r"(?<![a-z0-9+#.])" + re.escape(term) + r"(?![a-z0-9+#])"
            try:
                if re.search(pat, low):
                    label = term
                    if label not in found:
                        found.append(label)
            except Exception:
                continue
        return found[:25]

    # department/title based gate for "tech / software only"
    TECH_DEPTS = {"tech development", "product", "it", "data", "engineering",
                  "r&d", "research & development"}
    TECH_TITLE_HINTS = ("engineer", "developer", "software", "devops", "sre",
                        "data ", "data scientist", "machine learning", "ml ",
                        " ai", "ai ", "backend", "back-end", "frontend", "front-end",
                        "full stack", "full-stack", "fullstack", "architect",
                        "infrastructure", "platform", "security", "qa ",
                        "product manager", "product designer", "technical",
                        "analytics", "database", "cloud")
    NON_TECH_TITLE = ("marketing", "brand", "sales", "recruit", "people ops",
                      "finance", "legal", "counsel", "actuar", "compliance",
                      "insurance pricing", "biz ", "bizops")

    def _is_tech(dept, title):
        d = (dept or "").strip().lower()
        t = (title or "").strip().lower()
        strong = ("engineer", "developer", "software", "data ", "machine learning",
                  "platform", "devops", "sre", "architect")
        if any(h in t for h in NON_TECH_TITLE) and not any(h in t for h in strong):
            return False
        if d in TECH_DEPTS:
            return True
        if any(h in t for h in TECH_TITLE_HINTS):
            return True
        return False

    def _fetch(url):
        try:
            r = requests.get(url, headers=HEADERS, timeout=25)
            if r.status_code == 200 and r.content:
                r.encoding = "utf-8"  # page is utf-8; header omits charset
                return r.text
        except Exception:
            return None
        return None

    def _extract_recipes(html):
        if not html:
            return []
        blob = None
        # 1) proper parse of the __NEXT_DATA__ script via bs4
        try:
            if BeautifulSoup is not None:
                soup = BeautifulSoup(html, "lxml")
                tag = soup.find("script", id="__NEXT_DATA__")
                if tag and tag.string:
                    blob = tag.string
        except Exception:
            blob = None
        # 2) regex fallback
        if not blob:
            try:
                m = re.search(
                    r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>',
                    html, re.S)
                if m:
                    blob = m.group(1)
            except Exception:
                blob = None
        if not blob:
            return []
        try:
            data = json.loads(blob)
        except Exception:
            return []
        try:
            rec = data.get("props", {}).get("pageProps", {}).get("allRecipes")
            if isinstance(rec, list):
                return rec
        except Exception:
            pass
        # deep fallback: hunt for a list of dicts that look like roles
        found = []
        def walk(o):
            if found:
                return
            if isinstance(o, list):
                if o and isinstance(o[0], dict) and "link" in o[0] and (
                        "location" in o[0] or "department" in o[0]):
                    found.append(o)
                    return
                for v in o:
                    walk(v)
            elif isinstance(o, dict):
                for v in o.values():
                    walk(v)
        try:
            walk(data)
        except Exception:
            pass
        return found[0] if found else []

    # ---- main --------------------------------------------------------------
    results = []
    try:
        recipes = []
        for url in ("https://makers.lemonade.com/careers",
                    "https://makers.lemonade.com/"):
            html = _fetch(url)
            recipes = _extract_recipes(html)
            if recipes:
                break
            time.sleep(random.uniform(0.6, 1.2))

        # newest / display order first when an order key exists
        try:
            recipes = sorted(recipes, key=lambda x: x.get("order", 1e9))
        except Exception:
            pass

        seen = set()
        for j in recipes:
            try:
                loc = str(j.get("location") or "")
                low_loc = loc.lower()
                if "israel" not in low_loc and "tel aviv" not in low_loc:
                    continue
                title = (j.get("title") or "").strip()
                dept = (j.get("department") or "").strip()
                if not title:
                    continue
                if not _is_tech(dept, title):
                    continue

                sid = str(j.get("postingId") or j.get("id") or j.get("slug") or "").strip()
                if sid and sid in seen:
                    continue
                if sid:
                    seen.add(sid)

                url = (j.get("link") or "").strip()
                if not url and j.get("slug"):
                    url = "https://makers.lemonade.com/role/" + str(j["slug"])

                desc = _html_to_text(j.get("content") or "")
                city = loc.split(",")[0].strip() if loc else ""
                ymin, ymax = _years(desc)

                results.append({
                    "source": "lemonade",
                    "sid": sid,
                    "title": title,
                    "company": "Lemonade",
                    "city": city or "Tel Aviv",
                    "url": url,
                    "level": _level(title),
                    "years_min": ymin,
                    "years_max": ymax,
                    "tech": _tech(desc),
                    "desc": desc[:4000],
                    "active": True,
                })
                if len(results) >= 120:
                    break
            except Exception:
                continue
    except Exception:
        return results
    return results

# ===== Ashby (open JSON posting API) - generalized from src_moonactive 2026-09-24 =====
# slug -> (company, source, tech_only). The whole board comes back in ONE call:
#   GET https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=false
# moonactive keeps source "moonactive" so rows already in seen.json keep their keys.
# monday.com moved here from Greenhouse (its GH board 404s) and is a GIANT, so every
# Israel role is returned (tech_only=False; its departments are product-area names).
ASHBY_BOARDS = {
    "moonactive": ("Moon Active", "moonactive", True),
    "monday.com": ("monday.com", "ashby:monday.com", False),
}


def src_ashby(slugs=None):
    """Ashby public posting API -> newest Israel-based roles for each registered board
    (tech/software roles only unless the board is a giant). A failed board is logged
    with its status/exception. Never raises."""
    import re, time, json
    try:
        import requests
    except Exception:
        return []
    try:
        from bs4 import BeautifulSoup
    except Exception:
        BeautifulSoup = None

    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
    headers = {"User-Agent": UA, "Accept": "application/json"}
    out = []
    per_board = {}
    try:
        slugs = list(slugs) if slugs else list(ASHBY_BOARDS.keys())
    except Exception:
        slugs = list(ASHBY_BOARDS.keys())

    # ---- helpers ---------------------------------------------------------
    def is_israel(job):
        try:
            pa = ((job.get("address") or {}).get("postalAddress") or {})
            if str(pa.get("addressCountry", "")).strip().lower() == "israel":
                return True
            blob = json.dumps(
                [job.get("location"), job.get("secondaryLocations"),
                 job.get("address")], ensure_ascii=False).lower()
            return ("israel" in blob or "tel aviv" in blob
                    or "tel-aviv" in blob or "herzliya" in blob
                    or "petah" in blob or "raanana" in blob)
        except Exception:
            return False

    TECH_DEPTS = ("r&d", "data", "analytics", "security", " it",
                  "it ", "engineering", "platform", "technology", "devops",
                  "infrastructure")
    TECH_KW = ("engineer", "developer", "devops", "sre", "backend",
               "back end", "frontend", "front end", "full stack", "fullstack",
               "full-stack", "software", "data ", "data analyst",
               "data scientist", "security", "qa ", "automation", "architect",
               "unity", "game engineer", "technical", "infrastructure",
               "cloud", "machine learning", " ml", "ml ", " ai", "ai ",
               "algorithm", "programmer", "android", "ios",
               "platform", "python", "researcher")

    def is_tech(job):
        dept = str(job.get("department") or "").lower()
        team = str(job.get("team") or "").lower()
        title = str(job.get("title") or "").lower()
        if any(d in dept or d in team for d in TECH_DEPTS):
            return True
        if any(k in title for k in TECH_KW):
            return True
        return False

    def derive_level(title):
        if _is_student_title(title):
            return "student"
        t = " " + title.lower() + " "
        if any(w in t for w in (" apprentice ",)):
            return "student"
        if any(w in t for w in (" junior ", " jr ", " jr. ", " entry ",
                                " graduate ", " grad ")):
            return "junior"
        if any(w in t for w in (" senior ", " sr ", " sr. ", " lead ",
                                " principal ", " staff ", " head ",
                                " director ", " manager ", " expert ",
                                " team lead ", " architect ")):
            return "senior"
        return ""

    def parse_years(text):
        if not text:
            return (None, None)
        t = text.lower().replace("–", "-").replace("—", "-")
        # range: "3-5 years"
        m = re.search(r"(\d{1,2})\s*-\s*(\d{1,2})\s*\+?\s*(?:years|yrs|year)",
                      t)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if 0 <= a <= 40 and 0 <= b <= 40 and a <= b:
                return (a, b)
        # "at least/minimum of N years", "N+ years", "N years"
        for pat in (r"(?:at least|minimum of|min\.?)\s*(\d{1,2})\s*\+?\s*"
                    r"(?:years|yrs|year)",
                    r"(\d{1,2})\s*\+\s*(?:years|yrs|year)",
                    r"(\d{1,2})\s*(?:years|yrs|year)s?\s+of\s+"
                    r"(?:experience|exp|relevant|hands)"):
            m = re.search(pat, t)
            if m:
                v = int(m.group(1))
                if 0 <= v <= 40:
                    return (v, None)
        return (None, None)

    TECH_TAGS = [
        ("python", r"\bpython\b"), ("java", r"\bjava\b"),
        ("javascript", r"\bjavascript\b|\bjs\b"),
        ("typescript", r"\btypescript\b|\bts\b"),
        ("node.js", r"\bnode\.?js\b|\bnode\b"), ("react", r"\breact\b"),
        ("angular", r"\bangular\b"), ("vue", r"\bvue\b"),
        ("go", r"\bgolang\b|\bgo lang\b"), ("c++", r"c\+\+"),
        ("c#", r"c#|\.net\b|\bdotnet\b"), ("ruby", r"\bruby\b"),
        ("php", r"\bphp\b"), ("kotlin", r"\bkotlin\b"),
        ("swift", r"\bswift\b"), ("scala", r"\bscala\b"),
        ("rust", r"\brust\b"), ("unity", r"\bunity\b"),
        ("unreal", r"\bunreal\b"), ("aws", r"\baws\b|amazon web services"),
        ("gcp", r"\bgcp\b|google cloud"), ("azure", r"\bazure\b"),
        ("kubernetes", r"\bkubernetes\b|\bk8s\b"), ("docker", r"\bdocker\b"),
        ("terraform", r"\bterraform\b"), ("ansible", r"\bansible\b"),
        ("jenkins", r"\bjenkins\b"), ("ci/cd", r"\bci/?cd\b"),
        ("sql", r"\bsql\b"), ("mongodb", r"\bmongo\b|\bmongodb\b"),
        ("postgresql", r"\bpostgres\b|\bpostgresql\b"),
        ("mysql", r"\bmysql\b"), ("redis", r"\bredis\b"),
        ("kafka", r"\bkafka\b"), ("spark", r"\bspark\b"),
        ("airflow", r"\bairflow\b"), ("tensorflow", r"\btensorflow\b"),
        ("pytorch", r"\bpytorch\b"),
        ("machine learning", r"machine learning|\bml\b"),
        ("graphql", r"\bgraphql\b"), ("grpc", r"\bgrpc\b"),
        ("microservices", r"\bmicroservices?\b"), ("linux", r"\blinux\b"),
        ("bash", r"\bbash\b|\bshell scripting\b"), ("git", r"\bgit\b"),
        ("elasticsearch", r"\belasticsearch\b|\belastic\b"),
        ("snowflake", r"\bsnowflake\b"), ("bigquery", r"\bbigquery\b"),
        ("tableau", r"\btableau\b"), ("looker", r"\blooker\b"),
        ("rest", r"\brest\b|\brestful\b"), ("graphite", r"\bgraphite\b"),
    ]

    def extract_tech(text):
        if not text:
            return []
        t = text.lower()
        found = []
        for name, pat in TECH_TAGS:
            try:
                if re.search(pat, t):
                    found.append(name)
            except Exception:
                pass
        return found

    def clean_text(html, plain):
        if plain:
            return plain.strip()
        if html and BeautifulSoup is not None:
            try:
                return BeautifulSoup(html, "lxml").get_text(" ", strip=True)
            except Exception:
                pass
        if html:
            return re.sub(r"<[^>]+>", " ", html).strip()
        return ""

    def pub_key(job):
        return str(job.get("publishedAt") or "")

    for slug in slugs:
        company, source, tech_only = ASHBY_BOARDS.get(slug, (slug, "ashby:" + slug, True))
        url = ("https://api.ashbyhq.com/posting-api/job-board/"
               + slug + "?includeCompensation=false")
        data = None
        try:
            r = requests.get(url, headers=headers, timeout=30)
            if r.status_code == 200:
                data = r.json()
            else:
                per_board[slug] = "FAILED HTTP %s" % r.status_code
        except Exception as e:
            per_board[slug] = "FAILED %s" % type(e).__name__
        if not isinstance(data, dict) or not data.get("jobs"):
            per_board.setdefault(slug, "FAILED empty board")
            time.sleep(0.5)
            continue

        jobs = data.get("jobs") or []
        # ---- sort newest first, then filter ------------------------------
        try:
            jobs = sorted(jobs, key=pub_key, reverse=True)
        except Exception:
            pass

        n = 0
        for job in jobs[:400]:
            try:
                if not job.get("isListed", True):
                    continue
                if not is_israel(job):
                    continue
                if tech_only and not is_tech(job):
                    continue

                title = str(job.get("title") or "").strip()
                if not title:
                    continue
                sid = str(job.get("id") or job.get("jobUrl") or title)
                jurl = (job.get("jobUrl") or job.get("applyUrl") or "")

                pa = ((job.get("address") or {}).get("postalAddress") or {})
                city = (pa.get("addressLocality")
                        or job.get("location") or "Israel")
                city = str(city).strip()
                if job.get("isRemote") and "remote" not in city.lower():
                    city = city + " (Remote)"

                desc_full = clean_text(job.get("descriptionHtml"),
                                       job.get("descriptionPlain"))
                level = derive_level(title)
                ymin, ymax = parse_years(desc_full)
                tech = extract_tech(desc_full + " " + title)
                desc = desc_full[:1500].strip()

                out.append({
                    "source": source,
                    "sid": sid,
                    "title": title,
                    "company": company,
                    "city": city,
                    "url": jurl,
                    "level": level,
                    "years_min": ymin,
                    "years_max": ymax,
                    "tech": tech,
                    "desc": desc,
                    "active": True,
                })
                n += 1
                if n >= 120:
                    break
            except Exception:
                continue
        per_board[slug] = n
        time.sleep(0.5)

    try:
        print("    ashby per-board:", per_board)
    except Exception:
        pass
    return out


def src_moonactive():
    """Moon Active (Coin Master) careers via the Ashby public posting API.
    Thin wrapper kept so an existing ("moonactive", src_moonactive) registration keeps
    working; src_ashby() covers moonactive + monday.com. Never raises."""
    return src_ashby(["moonactive"])

# -*- coding: utf-8 -*-
def src_hibob():
    """
    hibob (HiBob) adapter for Ron's Israel tech-job scanner.
    HiBob's careers page (https://www.hibob.com/careers/) is a WordPress site
    that SERVER-RENDERS its Comeet board via the 'hibob-hiring' plugin, so the
    whole board comes back in one HTML GET (no JS, no pagination). Every opening
    is an <a class="comeet-position"> carrying:
        span.comeet-position-name  -> title
        span.comeet-position-meta  -> "<employment type> | <country>" e.g. "Permanent | Israel"
        href                       -> the Comeet-hosted job page (.../jobs/<uuid>); uuid = sid
    Positions are grouped under <div class="comeet-g-r"> blocks headed by
    <h3 class="comeet-group-name"> (the department), which we use for tech
    classification. The individual job pages are a JS SPA with no server HTML,
    so there is no JD to fetch server-side; desc is a synthesized context line
    (department + employment type + country) and years come from the title only.
    Returns Israel (meta contains 'Israel') tech/software roles only; the caller
    applies seniority/relevance/dedup filters. Never raises: all network is
    wrapped and partial results are returned.
    """
    import re, time
    try:
        import requests
    except Exception:
        return []
    try:
        from bs4 import BeautifulSoup
    except Exception:
        return []

    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
    HEADERS = {"User-Agent": UA,
               "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
               "Accept-Language": "en-US,en;q=0.9"}
    URLS = ["https://www.hibob.com/careers/", "https://www.hibob.com/careers"]
    CAP = 120

    # Broad tech signal (used inside tech / unknown departments).
    TECH_RE = re.compile(
        r"\b(engineer|engineering|developer|programmer|devops|devsecops|sre|software|"
        r"back[\s-]?end|front[\s-]?end|full[\s-]?stack|data|machine\s*learning|\bml\b|\bai\b|"
        r"artificial intelligence|algorithm|algorithms|\bqa\b|automation|sdet|architect|"
        r"security|cyber|cloud|platform|infrastructure|\binfra\b|research|scientist|embedded|"
        r"firmware|hardware|asic|verification|vlsi|\bnlp\b|computer vision|analyst|"
        r"product manager|product owner|technical|python|java|golang|react|node|"
        r"network|mobile|android|test|solutions? (?:architect|engineer)|support engineer)\b",
        re.I)
    # Strong tech signal (required to keep a role that sits in a NON-tech department).
    STRONG_TECH_RE = re.compile(
        r"\b(engineer|engineering|developer|programmer|devops|devsecops|sre|software|"
        r"back[\s-]?end|front[\s-]?end|full[\s-]?stack|architect|algorithm|algorithms|"
        r"\bqa\b|sdet|verification|vlsi|asic|firmware|embedded|data engineer|data scientist|"
        r"data platform|machine\s*learning|\bml\b|\bnlp\b|computer vision|"
        r"infrastructure engineer|platform engineer|security engineer|cloud engineer|"
        r"tech lead|technical lead)\b", re.I)
    NONTECH_RE = re.compile(
        r"\b(sales|account executive|account manager|business development|\bbdr\b|\bsdr\b|"
        r"marketing|brand|content writer|copywriter|recruit|talent acquisition|\bpeople\b|"
        r"\bhr\b|human resources|finance|accountant|bookkeep|controller|payroll|legal|counsel|"
        r"office manager|receptionist|administrative|executive assistant|community manager|"
        r"customer success manager|social media|procurement|lifecycle marketing|"
        r"paid acquisition|creative director|commission|finops)\b", re.I)
    TECH_DEPTS = ("tech", "business technolog", "r&d", "engineering", "data",
                  "product", "devops", "qa", "security", "platform",
                  "infrastructure", "software", "development")
    NONTECH_DEPTS = ("gtm", "go-to-market", "go to market", "marketing", "sales",
                     "finance", "operations", "people", "p&c", "legal", "talent",
                     "​hr", "human resources")

    def is_tech(title, dept):
        dl = (dept or "").lower()
        title_tech = bool(TECH_RE.search(title))
        title_strong = bool(STRONG_TECH_RE.search(title))
        title_nontech = bool(NONTECH_RE.search(title))
        dept_tech = any(d in dl for d in TECH_DEPTS)
        dept_nontech = any(d in dl for d in NONTECH_DEPTS)
        if dept_tech:
            # tech department: keep unless the title is unambiguously non-tech
            return not (title_nontech and not title_tech)
        if dept_nontech:
            # non-tech department: keep only with a strong engineering/tech title
            return title_strong
        # unknown department: fall back to broad title signal
        return title_tech and not (title_nontech and not title_strong)

    SENIOR_TITLE = re.compile(r"\b(senior|sr\.?|lead|principal|staff|head of|\bvp\b|"
                              r"director|architect|expert)\b", re.I)
    JUNIOR_TITLE = re.compile(r"\b(junior|jr\.?|entry[\s-]?level|graduate|associate)\b", re.I)
    STUDENT_TITLE = re.compile(r"\b(intern|internship|student|working student|apprentice|"
                               r"co[\s-]?op)\b", re.I)

    def classify_level(title):
        if STUDENT_TITLE.search(title):
            return "student"
        if JUNIOR_TITLE.search(title):
            return "junior"
        if SENIOR_TITLE.search(title):
            return "senior"
        return ""

    def extract_years(text):
        if not text:
            return None, None
        t = text.lower()
        m = re.search(r"(\d{1,2})\s*(?:-|–|to)\s*(\d{1,2})\s*\+?\s*years", t)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if a <= b <= 40:
                return a, b
        m = re.search(r"(?:at least|minimum(?: of)?|min\.?|over|more than)\s*(\d{1,2})\s*\+?\s*years", t)
        if m:
            return int(m.group(1)), None
        m = re.search(r"(\d{1,2})\s*\+\s*years", t)
        if m:
            return int(m.group(1)), None
        m = re.search(r"(\d{1,2})\s*years?\s+(?:of\s+)?(?:experience|exp)", t)
        if m:
            v = int(m.group(1))
            if v <= 40:
                return v, None
        return None, None

    TECH_VOCAB = [
        "Python", "Java", "JavaScript", "TypeScript", "Go", "Golang", "C++", "C#",
        "Rust", "Scala", "Kotlin", "Swift", "Ruby", "PHP", "Node.js", "Node",
        "React", "Angular", "Vue", "Next.js", "Django", "Flask", "FastAPI", "Spring",
        ".NET", "GraphQL", "REST", "gRPC",
        "AWS", "Azure", "GCP", "Google Cloud", "Kubernetes", "K8s", "Docker", "Terraform",
        "Ansible", "Jenkins", "CI/CD", "Linux", "Bash",
        "SQL", "PostgreSQL", "MySQL", "MongoDB", "Redis", "Elasticsearch",
        "Kafka", "Spark", "Airflow", "Snowflake", "BigQuery",
        "TensorFlow", "PyTorch", "Pandas", "NumPy", "LLM", "LLMs", "NLP",
        "Computer Vision", "Machine Learning", "Deep Learning", "Generative AI", "GenAI",
        "Data Science", "MLOps", "Microservices", "Backend", "Frontend", "Full Stack",
        "DevOps", "DevSecOps", "SRE", "QA", "Platform", "Infrastructure",
        "Embedded", "Firmware", "AI", "Data",
    ]

    def extract_tech(text):
        if not text:
            return []
        low = text.lower()
        found = []
        for kw in TECH_VOCAB:
            k = kw.lower()
            if len(k) <= 2:
                pat = r"(?<![a-z0-9])" + re.escape(k) + r"(?![a-z0-9])"
            elif re.match(r"^[a-z0-9]", k):
                pat = r"(?<![a-z0-9])" + re.escape(k)
            else:
                pat = re.escape(k)
            if re.search(pat, low):
                if kw not in found:
                    found.append(kw)
        return found

    # ---- fetch the (single) server-rendered board, with a light retry ----
    html_bytes = None
    for url in URLS:
        for attempt in range(2):
            try:
                r = requests.get(url, headers=HEADERS, timeout=30)
                if r.status_code == 200 and r.content and b"comeet-position" in r.content:
                    html_bytes = r.content
                    break
            except Exception:
                pass
            time.sleep(0.5)
        if html_bytes:
            break
    if not html_bytes:
        return []

    try:
        soup = BeautifulSoup(html_bytes, "lxml")  # bytes -> correct utf-8 from <meta>
    except Exception:
        try:
            soup = BeautifulSoup(html_bytes, "html.parser")
        except Exception:
            return []

    jobs = []
    seen = set()

    # Prefer department-grouped traversal; fall back to a flat scan.
    groups = soup.select("div.comeet-g-r")
    if not groups:
        groups = [soup]

    UUID_RE = re.compile(r"/jobs/([0-9a-fA-F-]{16,})")

    for grp in groups:
        if len(jobs) >= CAP:
            break
        head = grp.select_one("h3.comeet-group-name")
        dept = head.get_text(" ", strip=True) if head else ""
        for a in grp.select("a.comeet-position"):
            if len(jobs) >= CAP:
                break
            try:
                nm_el = a.select_one("span.comeet-position-name")
                title = nm_el.get_text(" ", strip=True) if nm_el else ""
                if not title:
                    continue
                meta_el = a.select_one("span.comeet-position-meta")
                meta = meta_el.get_text(" ", strip=True) if meta_el else ""

                # Israel only (meta country segment contains 'Israel').
                if "israel" not in meta.lower():
                    continue
                if not is_tech(title, dept):
                    continue

                href = (a.get("href") or "").strip()
                if not href:
                    continue
                m = UUID_RE.search(href)
                sid = m.group(1) if m else href
                if sid in seen:
                    continue

                # employment type + country from the meta ("Permanent | Israel").
                parts = [p.strip() for p in meta.split("|") if p.strip()]
                emp_type = parts[0] if len(parts) >= 2 else ""
                location = parts[-1] if parts else meta  # -> "Israel"

                # city best-effort: the board exposes country only, not a city.
                city = location if location and location.lower() != "israel" else ""

                desc_bits = [b for b in (dept, emp_type, location) if b]
                desc = " | ".join(desc_bits)

                level = classify_level(title)
                ymin, ymax = extract_years(title)
                tech = extract_tech(title)

                jobs.append({
                    "source": "hibob",
                    "sid": sid,
                    "title": title,
                    "company": "HiBob",
                    "city": city,
                    "url": href,
                    "level": level,
                    "years_min": ymin,
                    "years_max": ymax,
                    "tech": tech,
                    "desc": desc,
                    "active": True,
                })
                seen.add(sid)
            except Exception:
                continue

    return jobs

import re
import time
import requests
from bs4 import BeautifulSoup


def src_kaltura():
    """
    Kaltura careers adapter -> corp.kaltura.com/company/careers/

    The careers "lobby" ships every open role in the static HTML as
    <a class="b-new-careers-lobby__job" data-title=.. data-department=..
    data-location=.. href="/careers/{slug}/{code}/"> (country in data-location,
    city in the .job-location text, code = last URL path segment). We keep the
    Israel rows and enrich each from its own role page. Every Kaltura JD opens
    with ~1,400 chars of identical company boilerplate ("This is us ... 15+ years
    since starting the company"), so description/tech/years are parsed only from
    the role-specific text after that preamble. Returns a list of job dicts;
    never raises.
    """
    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
    HDRS = {"User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9"}
    # full navigate-style browser headers for the retry (CI runners get 0 rows while a
    # desktop gets ~17; a bot filter keyed on the bare header set is the usual cause)
    FULL_HDRS = {
        "User-Agent": UA,
        "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
                   "image/avif,image/webp,image/apng,*/*;q=0.8"),
        "Accept-Language": "en-US,en;q=0.9,he;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Cache-Control": "max-age=0",
    }
    BASE = "https://corp.kaltura.com"
    LIST = BASE + "/company/careers/"
    CAP = 120
    out = []

    def _log(msg):
        try:
            print("    kaltura " + msg)
        except Exception:
            pass

    def _get(url, timeout=25, headers=None):
        r = requests.get(url, headers=headers or HDRS, timeout=timeout, allow_redirects=True)
        # page is UTF-8; guard against requests guessing latin-1 (would mojibake)
        if not r.encoding or r.encoding.lower() in ("iso-8859-1", "latin-1"):
            r.encoding = r.apparent_encoding or "utf-8"
        return r

    def _list_anchors(headers, label):
        """-> (anchors, status/exception text). Never raises."""
        try:
            r = _get(LIST, headers=headers)
        except Exception as e:
            return [], "%s: EXC %s" % (label, type(e).__name__)
        if r.status_code != 200:
            return [], "%s: HTTP %s (%d bytes)" % (label, r.status_code, len(r.content or b""))
        try:
            soup = BeautifulSoup(r.text, "lxml")
            anchors = soup.select("a.b-new-careers-lobby__job")
            if not anchors:
                # fallback: any anchor carrying the job data-attrs
                anchors = [a for a in soup.find_all("a", href=True) if a.get("data-title")]
        except Exception as e:
            return [], "%s: parse EXC %s" % (label, type(e).__name__)
        return anchors, "%s: HTTP 200, %d job anchors (%d bytes)" % (
            label, len(anchors), len(r.content or b""))

    def _role_text(full):
        # drop the leading identical company boilerplate; keep from the first
        # real role/section header onward.
        tl = full.lower()
        heads = ["the role", "about the role", "what you'll do", "what you will do",
                 "the opportunity", "responsibilities", "your impact", "who you are",
                 "what you'll bring", "you bring", "qualifications"]
        pos = [tl.find(h) for h in heads if tl.find(h) != -1]
        idx = min(pos) if pos else -1
        return full[idx:] if idx > 0 else full

    def _level(title):
        t = (title or "").lower()
        if _is_student_title(title):     # word-bound: 'intern' must not hit "Internal ..."
            return "student"
        if any(w in t for w in ("senior", "sr.", "sr ", " lead", "lead ", "principal",
                                "staff", "architect", "manager", "head of", "director",
                                "team lead", "expert", " vp", "vp ", "chief")):
            return "senior"
        if any(w in t for w in ("junior", "jr.", "jr ", "entry", "graduate")):
            return "junior"
        return ""

    def _years(text):
        # role text only; still guard the stock "N years since starting" phrasing.
        t = (text or "").lower().replace("–", "-").replace("—", "-")
        ymin = ymax = None
        m = re.search(r'(\d{1,2})\s*\+?\s*(?:-|to|up to)\s*(\d{1,2})\s*\+?\s*(?:years|yrs|year)', t)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if max(a, b) <= 30:
                ymin, ymax = min(a, b), max(a, b)
        got = []
        for mm in re.finditer(r'(\d{1,2})\s*\+?\s*(?:years|yrs|year)\s*(?P<after>.{0,15})', t):
            after = mm.group("after")
            if "since" in after or "ago" in after:
                continue
            n = int(mm.group(1))
            if n <= 30:
                got.append(n)
        if got and ymin is None:
            ymin = min(got)
        return ymin, ymax

    # bare "go"/"video" excluded: "go-to-market"/"go live" and Kaltura's whole
    # video domain match every role and carry no signal. "golang" catches real Go.
    TECHKW = ["python", "c++", "c#", ".net", "java", "javascript", "typescript",
              "react", "angular", "vue", "node", "sql", "nosql", "mongodb", "redis",
              "postgres", "mysql", "aws", "azure", "gcp", "docker", "kubernetes",
              "k8s", "terraform", "ansible", "pytorch", "tensorflow",
              "machine learning", "deep learning", "ml", "ai", "llm", "genai",
              "nlp", "rag", "computer vision", "linux", "golang", "rust", "php",
              "ruby", "scala", "kotlin", "swift", "graphql", "rest", "grpc",
              "microservices", "kafka", "rabbitmq", "spark", "elasticsearch",
              "algorithms", "devops", "ci/cd", "sre", "qa", "automation",
              "selenium", "cypress", "playwright", "webrtc", "streaming", "html",
              "css", "netsuite", "salesforce", "prometheus", "grafana"]

    def _tech(text):
        t = " " + (text or "").lower() + " "
        found = []
        for k in TECHKW:
            # boundary match so "ai" != "email", "go" != "google", etc.
            if re.search(r'(?<![a-z0-9])' + re.escape(k) + r'(?![a-z0-9])', t):
                if k not in found:
                    found.append(k)
        return found[:15]

    no_jd = 0
    try:
        use_hdrs = HDRS
        anchors, note = _list_anchors(HDRS, "list")
        if not anchors:
            # one retry with the full browser header set (after a short pause)
            time.sleep(2.0)
            use_hdrs = FULL_HDRS
            anchors, note2 = _list_anchors(FULL_HDRS, "retry(full headers)")
            note = note + " | " + note2
        _log(note)

        for a in anchors:
            if len(out) >= CAP:
                break
            try:
                country = (a.get("data-location") or "").strip()
                if "israel" not in country.lower():
                    continue

                href = (a.get("href") or "").strip()
                if not href:
                    continue
                if href.startswith("/"):
                    href = BASE + href
                sid = href.rstrip("/").rsplit("/", 1)[-1]

                title = (a.get("data-title") or "").strip()
                if not title:
                    tn = a.select_one(".b-new-careers-lobby__job-name")
                    title = tn.get_text(" ", strip=True) if tn else ""
                if not title:
                    continue

                loc_el = a.select_one(".b-new-careers-lobby__job-location")
                city = loc_el.get_text(" ", strip=True) if loc_el else ""
                if not city:
                    city = country  # fall back to "Israel"

                # enrich from the role page (small list -> cheap); one retry on flakiness
                full = ""
                for _attempt in range(2):
                    try:
                        d = _get(href, timeout=20, headers=use_hdrs)
                        if d.status_code == 200:
                            ds = BeautifulSoup(d.text, "lxml")
                            art = (ds.select_one("div.b-new-career-inner__content")
                                   or ds.select_one(".b-new-career-inner__content-texts")
                                   or ds.select_one("article"))
                            if art:
                                txt = art.get_text(" ", strip=True)
                                txt = re.sub(r'^\s*Back to jobs\s*', '', txt)
                                full = re.sub(r'\s+', ' ', txt)
                        time.sleep(0.3)
                        if full:
                            break
                    except Exception:
                        time.sleep(0.5)

                if not full:
                    no_jd += 1
                role = _role_text(full)
                desc = role[:2500]
                ymin, ymax = _years(role)
                out.append({
                    "source": "kaltura",
                    "sid": sid,
                    "title": title,
                    "company": "Kaltura",
                    "city": city,
                    "url": href,
                    "level": _level(title),
                    "years_min": ymin,
                    "years_max": ymax,
                    "tech": _tech(title + " " + role),
                    "desc": desc,
                    "active": True,
                })
            except Exception:
                continue
    except Exception as e:
        _log("ERROR %s" % e)

    _log("%d Israel rows (%d without JD)" % (len(out), no_jd))
    return out


# ======================================================================================
# ===== Giant-company adapters (own ATS / career sites) - added 2026-09-24 =====
# Built and live-tested separately; appended verbatim. Each is self-contained
# (imports inside), returns the standard row dicts, and never raises.
#   src_eightfold       Eightfold PCSX sites (Qualcomm, Microsoft)
#   src_oracle_hcm      Oracle Recruiting Cloud tenants (Oracle, Dell)
#   src_smartrecruiters SmartRecruiters public API (Wix, SanDisk)
#   src_google          Google careers
#   src_checkpoint      Check Point careers (+ SmartRecruiters cross-check)
#   src_meta            Meta careers (GraphQL)
#   src_booking         Booking.com (iCIMS Jibe)
#   src_sap             SAP (SuccessFactors CSB)
# ======================================================================================


def src_eightfold():
    """Eightfold "PCSX" careers sites (Qualcomm, Microsoft) -> Israel jobs.

    Flow (verified live 2026-09-24, plain HTTP, no cookies/CSRF/JS):
      1. GET https://{host}/api/pcsx/search?domain={domain}&query=&location=Israel
         &start={0,10,20..}&sort_by=timestamp  -> data.positions[], data.count
         (10 per page; step start by 10 until empty or start >= count).
         The location filter is radius-based, so neighbours (e.g. Jordan) leak in:
         every position is re-checked client-side for Israel.
      2. GET https://{host}/api/pcsx/position_details?position_id={id}&domain={domain}&hl=en
         -> data.jobDescription (HTML) for the plain-text desc, capped per company.
    The old /api/apply/v2/jobs endpoint answers 403 "Not authorized for PCSX" - don't use it.
    Brands run in parallel (one thread + one session per host, each host paced on its
    own), so adding a brand does not add to the wall-clock time.
    Never raises; on any failure returns whatever was collected so far.
    """
    import re, time, html
    try:
        import requests
        from concurrent.futures import ThreadPoolExecutor, wait
    except Exception:
        return []
    try:
        from bs4 import BeautifulSoup
    except Exception:
        BeautifulSoup = None

    # brand -> (careers_host, eightfold domain)
    REGISTRY = {
        "Qualcomm":  ("careers.qualcomm.com", "qualcomm.com"),
        "Microsoft": ("apply.careers.microsoft.com", "microsoft.com"),
    }
    # Microsoft 429s after ~8 rapid calls; give it a slower per-host pace.
    HOST_PACE = {"apply.careers.microsoft.com": 1.0}
    DEFAULT_PACE = 0.3
    PAGE = 10
    MAX_PAGES = 25              # 250 listings per brand, hard stop
    MAX_DETAIL_PER_BRAND = 80
    DESC_MAX = 2500
    BUDGET_S = 80.0             # whole-adapter runtime budget

    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

    t0 = time.time()

    def time_left():
        return BUDGET_S - (time.time() - t0)

    # ---------------- location helpers ----------------
    NOISE = {"israel", "il", "multiple locations", "multiple location", "remote", ""}
    # Microsoft uses "Israel, <region>, <city>"; these region words are never the city.
    REGION_WORDS = {"southern", "northern", "central", "center", "north", "south",
                    "tel aviv district", "haifa district", "center district",
                    "south district", "north district", "jerusalem district", "central district"}
    CITY_FIX = {
        "kfar-netter": "Kfar Netter", "kfar netter": "Kfar Netter",
        "hod hasharon": "Hod HaSharon", "beer-sheva": "Beer Sheva", "beer sheva": "Beer Sheva",
        "be'er sheva": "Beer Sheva", "beersheba": "Beer Sheva", "tel aviv-yafo": "Tel Aviv",
        "tel aviv": "Tel Aviv", "petah-tikva": "Petah Tikva", "petach tikva": "Petah Tikva",
        "raanana": "Ra'anana", "ra'anana": "Ra'anana", "herzeliya": "Herzliya",
        "yokneam": "Yokneam", "yoqneam": "Yokneam", "yokneam illit": "Yokneam",
    }
    # Rank sites so a multi-site role is labelled by a site the scanner keeps
    # (scanner drops South/Jerusalem; North is the preferred region).
    NORTH_K = ("haifa", "yokneam", "yoqneam", "nazareth", "migdal haemek", "karmiel", "carmiel",
               "caesarea", "hadera", "tefen", "nesher", "tirat carmel", "afula", "akko", "nahariya",
               "zichron", "zikhron", "kiryat ata", "kiryat bialik", "kiryat motzkin", "kiryat yam")
    DROP_K = ("beer sheva", "be'er sheva", "beersheba", "ashkelon", "ashdod", "kiryat gat",
              "sderot", "dimona", "eilat", "arad", "jerusalem", "omer", "lehavim", "gedera")

    def city_rank(c):
        cl = c.lower()
        if any(k in cl for k in NORTH_K):
            return 0
        if any(k in cl for k in DROP_K):
            return 2
        return 1

    def is_israel(p):
        for l in (p.get("locations") or []):
            if "israel" in [x.strip().lower() for x in str(l).split(",")]:
                return True
        for l in (p.get("standardizedLocations") or []):
            s = str(l).strip()
            if s == "IL" or s.endswith(", IL"):
                return True
        return False

    def city_of_loc(l):
        # NB: use `locations`, not `standardizedLocations` - Qualcomm's standardized
        # data files Hod HaSharon under "Haifa" and abbreviates cities in Hebrew.
        parts = [x.strip() for x in str(l).split(",") if x.strip()]
        low = [x.lower() for x in parts]
        if not parts or "israel" not in low:
            return ""
        if low[0] == "israel":          # Microsoft: "Israel, Tel Aviv, Herzliya"
            cand = parts[-1] if len(parts) > 1 else ""
        else:                           # Qualcomm: "Hod Hasharon, Haifa District, Israel"
            cand = parts[0]
        cl = cand.lower()
        if cl in NOISE or cl in REGION_WORDS or cl.endswith(" district"):
            return ""
        return CITY_FIX.get(cl, cand)

    def city_of(p):
        seen, cities = set(), []
        for l in (p.get("locations") or []):
            c = city_of_loc(l)
            if c and c.lower() not in seen:
                seen.add(c.lower())
                cities.append(c)
        if not cities:
            return "Israel"
        cities.sort(key=city_rank)                  # stable: keeps site order within a rank
        keep = [c for c in cities if city_rank(c) < 2] or cities[:1]
        return " / ".join(keep[:3])

    # ---------------- text helpers ----------------
    # Everything from the first of these on is legal/EEO/agency boilerplate.
    CUT_MARKERS = [
        "*references to a particular number of years",
        "qualcomm is an equal opportunity employer",
        "applicants: qualcomm is",
        "to all staffing and recruiting agencies",
        "microsoft is an equal opportunity employer",
        "this position will be open for a minimum of",
        "other requirements: ability to meet microsoft",
        "if you would like more information about this role",
    ]
    CUT_RES = [re.compile(re.escape(m).replace("\\ ", r"\s+"), re.I) for m in CUT_MARKERS]
    BOILER_RES = [
        re.compile(r"^\s*Company:\s*Qualcomm[^\n]*(?:\n|$)", re.I),
        re.compile(r"As a leading technology innovator, Qualcomm pushes the boundaries.{0,300}?"
                   r"connected future for all\.?", re.I | re.S),
        re.compile(r"Microsoft[’']s mission is to empower every person.{0,500}?"
                   r"at work and beyond\.?", re.I | re.S),
        re.compile(r"(?m)^\s*#[\w+\-]+\s*$"),               # "#IL", "#W+D" hashtag lines
    ]
    # A short line like this opens the requirements block (used by smart_cap).
    REQ_HEAD = re.compile(
        r"^(?:minimum |required |basic |must[- ]have |key |job )?(?:qualifications|requirements)\b"
        r"|^what (?:you(?:'|’)ll need|we(?:'|’)re looking for|you bring)"
        r"|^(?:about you|who you are|you have|you should have|must have)\b", re.I)

    def clean_desc(raw):
        """HTML JD -> (single-spaced plain text, char offset of requirements heading or -1)."""
        if not raw:
            return "", -1
        try:
            if BeautifulSoup is not None:
                txt = BeautifulSoup(raw, "html.parser").get_text("\n")
            else:
                txt = re.sub(r"<[^>]+>", "\n", raw)
        except Exception:
            txt = re.sub(r"<[^>]+>", "\n", raw)
        txt = html.unescape(txt).replace("\xa0", " ").replace("�", " ")
        cut = len(txt)
        for rx in CUT_RES:
            m = rx.search(txt)
            if m and 200 < m.start() < cut:
                cut = m.start()
        txt = txt[:cut]
        for rx in BOILER_RES:
            txt = rx.sub(" ", txt)
        out, req_at = "", -1
        for ln in txt.split("\n"):
            ln = re.sub(r"\s+", " ", ln).strip()
            if not ln:
                continue
            if req_at < 0 and len(out) >= 400 and len(ln) <= 60 and REQ_HEAD.match(ln):
                req_at = len(out) + 1
            out = (out + " " + ln) if out else ln
        return out, req_at

    def cap(txt, n):
        if len(txt) <= n:
            return txt
        cut = txt[:n]
        sp = cut.rfind(" ")
        return (cut[:sp] if sp > n - 200 else cut).rstrip()

    def smart_cap(txt, req_at):
        """Cap at DESC_MAX, but if the requirements block would be cut off, keep the
        head of the JD plus the start of the requirements (years/stack live there)."""
        if len(txt) <= DESC_MAX:
            return txt
        if req_at < 0 or req_at <= DESC_MAX - 500:
            return cap(txt, DESC_MAX)
        tail = cap(txt[req_at:], 1300)
        head = cap(txt[:req_at], DESC_MAX - len(tail) - 5)
        return (head + " ... " + tail)[:DESC_MAX]

    YEARS_RX = re.compile(
        r"(?P<a>\d{1,2})\s*(?:-|–|—|to)\s*(?P<b>\d{1,2})\s*\+?\s*(?:years?|yrs?)\b"
        r"|(?P<c>\d{1,2})\s*\+?\s*(?:years?|yrs?)\b")

    def years_of(text):
        """First experience requirement in reading order (the team-specific ask comes
        before Qualcomm's generic degree ladder). Only numbers next to 'experien'."""
        t = (text or "").lower()
        for m in YEARS_RX.finditer(t):
            if "experien" not in t[max(0, m.start() - 30):min(len(t), m.end() + 70)]:
                continue
            if m.group("a") is not None:
                a, b = int(m.group("a")), int(m.group("b"))
                if 0 <= a <= 30 and a <= b <= 30:
                    return (a, b)
            else:
                a = int(m.group("c"))
                if 0 <= a <= 30:
                    return (a, None)
        return (None, None)

    def level_of(title):
        tl = (title or "").lower()
        if re.search(r"\b(intern|interns|internship|student|co-?op|apprentice)\b", tl):
            return "student"
        if re.search(r"\b(senior|sr\.?|staff|principal|lead|architect|chief|director|head of|"
                     r"vp|vice president|distinguished|fellow|expert)\b", tl):
            return "senior"
        if re.search(r"\b(junior|jr\.?|entry[- ]level|new grad|graduate|early[- ]career)\b", tl):
            return "junior"
        return ""

    # dev-ish titles get their JD fetched first if the budget runs short
    DEV_TITLE = re.compile(r"software|developer|engineer|devops|firmware|embedded|backend|"
                           r"full[- ]?stack|frontend|\bai\b|data|automation|validation|security", re.I)

    TECH = [
        (r"\bpython\b", "Python"), (r"\bjava\b", "Java"), (r"\bjavascript\b", "JavaScript"),
        (r"\btypescript\b", "TypeScript"), (r"c\+\+", "C++"), (r"\bc#|\.net\b", "C#/.NET"),
        (r"\bc\s*(?:/|,|and|or)\s*c\+\+|c\+\+\s*(?:/|,|and|or)\s*c\b|\bembedded c\b|\bc programming\b|\bin c\b",
         "C"),
        (r"\bgolang\b|\b(?:java|python|c\+\+|rust|kotlin|scala),?\s*(?:,|/|or|and)\s*go\b", "Go"),
        (r"\brust\b", "Rust"), (r"\bkotlin\b", "Kotlin"), (r"\bscala\b", "Scala"),
        (r"\bmatlab\b", "MATLAB"), (r"\bsql\b", "SQL"),
        (r"\breact(?:\.js|js)?\b(?!\s+to\b)", "React"), (r"\bangular\b", "Angular"),
        (r"\bnode\.?js\b", "Node.js"), (r"\bspring boot\b", "Spring"),
        (r"\bkubernetes\b|\bk8s\b", "Kubernetes"), (r"\bdocker\b", "Docker"),
        (r"\bterraform\b", "Terraform"), (r"\baws\b", "AWS"), (r"\bgcp\b|google cloud", "GCP"),
        (r"\bazure\b", "Azure"), (r"\blinux\b", "Linux"), (r"\bembedded\b", "Embedded"),
        (r"\bfirmware\b", "Firmware"), (r"\brtos\b", "RTOS"),
        (r"\bverilog\b", "Verilog"), (r"\bsystemverilog\b", "SystemVerilog"), (r"\buvm\b", "UVM"),
        (r"\bvhdl\b", "VHDL"), (r"\bfpga\b", "FPGA"), (r"\basic\b", "ASIC"), (r"\bdsp\b", "DSP"),
        (r"\bcuda\b", "CUDA"), (r"\bpytorch\b", "PyTorch"), (r"\btensorflow\b", "TensorFlow"),
        (r"\bspark\b", "Spark"), (r"\bkafka\b", "Kafka"),
        (r"\bmicroservices?\b", "Microservices"), (r"ci/cd|ci-cd", "CI/CD"),
        (r"\bgit\b", "Git"), (r"machine learning|\bml\b", "Machine Learning"),
        (r"deep learning|\bdnns?\b", "Deep Learning"),
        (r"\bllms?\b|large language model", "LLM"), (r"gen ?ai\b|generative ai", "GenAI"),
        (r"\bagents?\b|agentic", "AI Agents"), (r"computer vision", "Computer Vision"),
        (r"\b5g\b|\blte\b|\bmodem\b", "5G/Modem"),
    ]

    def tech_of(text):
        t = (text or "").lower()
        out = []
        for pat, label in TECH:
            try:
                if label not in out and re.search(pat, t):
                    out.append(label)
            except re.error:
                pass
        return out

    # ---------------- per-brand worker (one thread, one session, one host) ----------------
    def run_brand(brand, host, domain):
        rows = []
        try:
            sess = requests.Session()
            sess.headers.update({"User-Agent": UA, "Accept": "application/json",
                                 "Accept-Language": "en-US,en;q=0.9"})
        except Exception:
            return rows
        st = {"last": 0.0, "pace": HOST_PACE.get(host, DEFAULT_PACE), "fails": 0}

        def get_json(path, params, tries=3):
            """Paced GET with 429/5xx/connection backoff + circuit breaker.
            Returns dict, {} for a live-but-empty answer (e.g. 404), or None on failure."""
            if st["fails"] >= 4:
                return None
            j = None
            for attempt in range(tries):
                if time_left() < 3:
                    break
                last = attempt == tries - 1
                gap = st["pace"] - (time.time() - st["last"])
                if gap > 0:
                    time.sleep(gap)
                try:
                    r = sess.get("https://%s%s" % (host, path), params=params,
                                 timeout=(6, max(3.0, min(15.0, time_left()))))
                except Exception:
                    st["last"] = time.time()
                    if not last:
                        time.sleep(min(1.5 * (attempt + 1), max(0.0, time_left() - 3)))
                    continue
                st["last"] = time.time()
                if r.status_code == 429 or r.status_code >= 500:
                    st["pace"] = min(3.0, max(st["pace"] * 2, 1.5))   # slow down for the rest of the run
                    if not last:
                        wait_s = 2.0 * (attempt + 1)
                        ra = str(r.headers.get("Retry-After", "") or "")
                        if ra.isdigit():
                            wait_s = max(wait_s, min(float(ra), 10.0))
                        time.sleep(min(wait_s, max(0.0, time_left() - 3)))
                    continue
                if r.status_code != 200:
                    j = {}
                    break
                try:
                    j = r.json()
                    j = j if isinstance(j, dict) else None
                except Exception:
                    j = None
                break
            st["fails"] = 0 if j is not None else st["fails"] + 1
            return j

        # 1) listings
        listings, seen_ids = [], set()
        try:
            start, count = 0, None
            for _ in range(MAX_PAGES):
                if time_left() < 10:
                    break
                j = get_json("/api/pcsx/search",
                             {"domain": domain, "query": "", "location": "Israel",
                              "start": start, "sort_by": "timestamp"})
                if not j:
                    break
                data = j.get("data") or {}
                pos = data.get("positions") or []
                if count is None:
                    try:
                        count = int(data.get("count") or 0)
                    except Exception:
                        count = 0
                if not pos:
                    break
                for p in pos:
                    pid = p.get("id") if isinstance(p, dict) else None
                    if pid is None or pid in seen_ids:
                        continue
                    seen_ids.add(pid)
                    if is_israel(p):
                        listings.append(p)
                start += PAGE
                if count and start >= count:
                    break
        except Exception:
            pass

        # 2) JDs - dev-ish titles first (stable sort keeps newest-first within a group)
        descs = {}
        try:
            order = sorted(listings, key=lambda p: 0 if DEV_TITLE.search(str(p.get("name") or "")) else 1)
            for p in order[:MAX_DETAIL_PER_BRAND]:
                if time_left() <= 4 or st["fails"] >= 4:
                    break
                try:
                    j = get_json("/api/pcsx/position_details",
                                 {"position_id": p.get("id"), "domain": domain, "hl": "en"})
                    jd = ((j or {}).get("data") or {}).get("jobDescription")
                    if jd:
                        descs[p.get("id")] = jd
                except Exception:
                    continue
        except Exception:
            pass

        # 3) rows (every Israel listing, with or without a JD)
        slug = re.sub(r"[^a-z0-9]+", "", brand.lower())
        for p in listings:
            try:
                pid = p.get("id")
                title = re.sub(r"\s+", " ", str(p.get("name") or "")).strip()
                if not title:
                    continue
                pu = str(p.get("positionUrl") or ("/careers/job/%s" % pid))
                url = pu if pu.startswith("http") else "https://%s%s" % (host, pu)
                full, req_at = clean_desc(descs.get(pid, ""))
                ymin, ymax = years_of(full)
                rows.append({
                    "source": "eightfold:%s" % slug,
                    "sid": str(pid),
                    "title": title,
                    "company": brand,
                    "city": city_of(p),
                    "url": url,
                    "level": level_of(title),
                    "years_min": ymin,
                    "years_max": ymax,
                    "tech": tech_of(title + " " + full),
                    "desc": smart_cap(full, req_at),
                    "active": True,
                })
            except Exception:
                continue
        return rows

    # ---------------- run all brands in parallel ----------------
    out = []
    try:
        ex = ThreadPoolExecutor(max_workers=max(1, len(REGISTRY)))
        futs = {ex.submit(run_brand, b, h, d): b for b, (h, d) in REGISTRY.items()}
        done, _ = wait(list(futs), timeout=BUDGET_S + 25)   # workers self-stop at BUDGET_S
        try:
            ex.shutdown(wait=False)
        except Exception:
            pass
        seen = set()
        for f in futs:                                       # REGISTRY order, deterministic
            if f not in done:
                continue
            try:
                for r in f.result() or []:
                    k = (r["source"], r["sid"])
                    if k not in seen:
                        seen.add(k)
                        out.append(r)
            except Exception:
                continue
    except Exception:
        pass
    return out


def src_oracle_hcm():
    """Oracle Recruiting Cloud (ORC / "Candidate Experience") -> Israel roles.

    Serves every company whose careers site runs on Oracle HCM Recruiting Cloud.
    Public, login-free REST:
      list   : GET https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions
               ?onlyData=true&expand=requisitionList.secondaryLocations
               &finder=findReqs;siteNumber=..,facetsList=LOCATIONS,limit=..,offset=..,locationId=..
               -> items[0].TotalJobsCount + items[0].requisitionList[]
               (the `expand` param is REQUIRED - without it requisitionList is omitted)
      detail : GET .../recruitingCEJobRequisitionDetails?expand=all&onlyData=true
               &finder=ById;Id="{Id}",siteNumber=..
               -> ExternalDescriptionStr / ExternalQualificationsStr /
                  ExternalResponsibilitiesStr + workLocation[].TownOrCity (real city)
      public : https://{host}/hcmUI/CandidateExperience/en/sites/{siteNumber}/job/{Id}

    GOTCHA (verified live): an unknown/stale locationId is SILENTLY IGNORED - the API
    returns 200 with the whole global board (Oracle ~2.2k, Dell ~470). So every
    strategy is validated (first page must be Israel jobs), with fallbacks
    location=Israel -> facet-id rediscovery via keyword="Israel", and a hard
    client-side IL country filter on every row. Never raises.
    """
    import re, time, html as _html
    import requests
    from concurrent.futures import ThreadPoolExecutor

    # brand -> (host, siteNumber, Israel country locationId)
    REGISTRY = {
        "Oracle": ("eeho.fa.us2.oraclecloud.com", "CX_45001", "300000000106941"),
        "Dell":   ("enterpriseplatform.dell.com", "CX_1001", "300000000471047"),
    }
    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
    T0 = time.time()
    BUDGET = 80.0          # seconds, whole run (brands run in parallel, 1 thread each)
    PAGE = 100             # requisitions per list page
    MAX_PAGES = 10         # safety: Israel boards are tiny (tens of jobs)
    DETAIL_CAP = 80        # JD detail fetches per company
    DESC_MAX = 2500
    SLEEP = 0.3

    def left():
        return BUDGET - (time.time() - T0)

    # ---------------- text helpers ----------------
    def html_to_text(s):
        if not s:
            return ""
        s = re.sub(r'(?is)<(script|style)[^>]*>.*?</\1>', ' ', s)
        s = re.sub(r'(?i)<li[^>]*>', '\n- ', s)
        s = re.sub(r'(?i)<br\s*/?>|</p>|</div>|</li>|</h\d>|</tr>|</ul>|</ol>', '\n', s)
        s = re.sub(r'<[^>]+>', ' ', s)
        s = _html.unescape(s).replace('\xa0', ' ').replace('​', '')
        s = re.sub(r'(?m)^\s*#LI-\S+\s*$', '', s)          # LinkedIn tracking tags
        s = re.sub(r'#LI-\S+', '', s)
        s = re.sub(r'[ \t\r\f\v]+', ' ', s)
        s = re.sub(r' *\n *', '\n', s)
        s = re.sub(r'\n(?:-\s*\n)+', '\n', s)                # empty bullets
        s = re.sub(r'\n{3,}', '\n\n', s)
        return s.strip()

    SENIOR = ("senior", "sr.", "sr ", "lead", "principal", "staff", "architect",
              "head of", "director", "chief", "vp", "vice president",
              "distinguished", "fellow")
    JUNIOR = ("junior", "jr.", "jr ", "entry level", "entry-level", "new grad",
              "new-grad", "graduate", "associate engineer", "associate developer",
              "associate software")
    STUDENT = ("intern", "internship", "student", "co-op", "apprentice")

    def has_word(t, w):
        return re.search(r'(?<![a-z0-9])' + re.escape(w.strip()) + r'(?![a-z0-9])', t) is not None

    def level_of(title):
        t = (title or "").lower()
        if any(has_word(t, w) for w in STUDENT):
            return "student"
        if any(has_word(t, w) for w in SENIOR):
            return "senior"
        if any(has_word(t, w) for w in JUNIOR):
            return "junior"
        return ""

    def years_of(text):
        """Lowest stated experience floor (same semantics as jobscan.parse_years:
        a range '0-3 years' contributes its LOW end). Runs on the FULL untruncated
        JD so requirements past the 2500-char desc cap still count. Values >20 are
        company-history noise ("40 years of innovation") and ignored."""
        t = (text or "").lower().replace('–', '-').replace('—', '-')
        yrs = r'(?:years?|yrs?)'
        best = None       # (low, high)
        for a, b in re.findall(r'(\d{1,2})\s*(?:-|to)\s*(\d{1,2})\s*\+?\s*' + yrs, t):
            lo, hi = int(a), int(b)
            if lo <= 20 and hi <= 25 and lo <= hi and (best is None or lo < best[0]):
                best = (lo, hi)
        for a in re.findall(r'(?<![\d-])(\d{1,2})\s*\+?\s*(?:or more\s+)?' + yrs, t):
            lo = int(a)
            if lo <= 20 and (best is None or lo < best[0]):
                best = (lo, None)
        return (best[0], best[1]) if best else (None, None)

    TECH_KW = ["python", "java", "javascript", "typescript", "c++", "c#", "golang",
               "rust", "scala", "kotlin", "ruby", ".net", "node.js", "react",
               "angular", "vue", "django", "flask", "fastapi", "spring",
               "kubernetes", "docker", "terraform", "ansible", "aws", "gcp",
               "azure", "oci", "sql", "nosql", "postgresql", "mysql", "mongodb",
               "redis", "elasticsearch", "spark", "kafka", "airflow", "linux",
               "bash", "embedded", "firmware", "machine learning", "deep learning",
               "pytorch", "tensorflow", "llm", "genai", "nlp", "computer vision",
               "mlops", "devops", "ci/cd", "jenkins", "git", "graphql",
               "microservices", "rest api", "tcp/ip", "bgp", "sdn", "prometheus",
               "grafana", "snowflake", "databricks", "cryptography"]

    def tech_of(text):
        t = (text or "").lower()
        out = []
        for kw in TECH_KW:
            if kw == "c++":
                hit = re.search(r'(?<![a-z0-9])c\+\+', t)
            elif kw == "c#":
                hit = re.search(r'(?<![a-z0-9])c#', t)
            elif kw == ".net":
                hit = re.search(r'(?<![a-z0-9])\.net(?![a-z0-9])', t)
            elif kw == "node.js":
                hit = re.search(r'(?<![a-z0-9])node\.?js(?![a-z0-9])', t)
            elif kw == "ci/cd":
                hit = "ci/cd" in t or "ci / cd" in t
            else:
                hit = has_word(t, kw)
            if hit and kw not in out:
                out.append(kw)
        return out[:12]

    # ---------------- city helpers ----------------
    CITY = {   # normalized key -> canonical (matches config NORTH/SOUTH/JERUSALEM spellings)
        "petach tikva": "Petah Tikva", "petah tikva": "Petah Tikva",
        "petach tikvah": "Petah Tikva", "petah tiqwa": "Petah Tikva", "petah tikwa": "Petah Tikva",
        "beer sheba": "Beer Sheva", "beer sheva": "Beer Sheva", "beersheba": "Beer Sheva",
        "beersheva": "Beer Sheva", "bersheba": "Beer Sheva",
        "herzliya": "Herzliya", "herzliyya": "Herzliya", "herzlia": "Herzliya",
        "hertzliya": "Herzliya", "herzliya pituach": "Herzliya",
        "tel aviv": "Tel Aviv", "tel aviv yafo": "Tel Aviv", "tel aviv jaffa": "Tel Aviv",
        "jerusalem": "Jerusalem", "haifa": "Haifa", "raanana": "Ra'anana",
        "netanya": "Netanya", "rehovot": "Rehovot", "yokneam": "Yokneam",
        "yoqneam": "Yokneam", "yokneam illit": "Yokneam", "hod hasharon": "Hod Hasharon",
        "kfar saba": "Kfar Saba", "ramat gan": "Ramat Gan", "airport city": "Airport City",
        "caesarea": "Caesarea", "modiin": "Modiin", "rosh haayin": "Rosh HaAyin",
        "or yehuda": "Or Yehuda", "holon": "Holon", "bnei brak": "Bnei Brak",
        "givatayim": "Givatayim", "ramat hasharon": "Ramat Hasharon", "lod": "Lod",
        "ness ziona": "Ness Ziona", "nes ziona": "Ness Ziona", "rishon lezion": "Rishon LeZion",
        "rishon letsiyon": "Rishon LeZion", "ashdod": "Ashdod", "ashkelon": "Ashkelon",
        "kiryat gat": "Kiryat Gat", "migdal haemek": "Migdal HaEmek", "nazareth": "Nazareth",
        "karmiel": "Karmiel", "omer": "Omer", "sderot": "Sderot", "hadera": "Hadera",
    }
    FAR = {"Beer Sheva", "Jerusalem", "Ashdod", "Ashkelon", "Kiryat Gat", "Omer", "Sderot"}

    def ckey(s):
        s = (s or "").lower().replace("'", "").replace("’", "")
        s = re.sub(r'[^a-z0-9]+', ' ', s)
        return re.sub(r'\s+', ' ', s).strip()

    def canon_city(raw):
        k = ckey(raw)
        if not k or k == "israel" or k == "il":
            return ""
        if k in CITY:
            return CITY[k]
        for ck in sorted(CITY, key=len, reverse=True):    # e.g. "il beer sheba 77 haenergia st"
            if re.search(r'(?<![a-z0-9])' + re.escape(ck) + r'(?![a-z0-9])', k):
                return CITY[ck]
        return raw.strip().title()

    def city_of(req, det, title):
        cands = []
        if det:
            for key in ("workLocation", "otherWorkLocations"):
                for w in det.get(key) or []:
                    if not isinstance(w, dict):
                        continue
                    if (w.get("Country") or "IL").upper() != "IL":
                        continue
                    c = canon_city(w.get("TownOrCity") or "") or canon_city(w.get("LocationName") or "")
                    if c:
                        cands.append(c)
        prim = (req.get("PrimaryLocation") or "").strip()
        if prim and (req.get("PrimaryLocationCountry") or "").upper() == "IL":
            segs = [x.strip() for x in prim.split(",") if x.strip()]
            if len(segs) > 1:                 # "Herzliya, Tel Aviv, Israel" -> Herzliya
                c = canon_city(segs[0])
                if c:
                    cands.append(c)
        for sl in req.get("secondaryLocations") or []:
            if isinstance(sl, dict) and (sl.get("CountryCode") or "").upper() == "IL":
                segs = [x.strip() for x in (sl.get("Name") or "").split(",") if x.strip()]
                if len(segs) > 1:
                    c = canon_city(segs[0])
                    if c:
                        cands.append(c)
        if not cands:                          # e.g. "Software Engineer (Beer-Sheva)"
            tk = ckey(title)
            for ck in sorted(CITY, key=len, reverse=True):
                if re.search(r'(?<![a-z0-9])' + re.escape(ck) + r'(?![a-z0-9])', tk):
                    cands.append(CITY[ck])
                    break
        if not cands:
            return "Israel"
        # multi-site role: prefer a non-far site so a role also open in the center isn't region-dropped
        for c in cands:
            if c not in FAR:
                return c
        return cands[0]

    def is_il(req):
        if (req.get("PrimaryLocationCountry") or "").upper() == "IL":
            return True
        for sl in req.get("secondaryLocations") or []:
            if isinstance(sl, dict) and (sl.get("CountryCode") or "").upper() == "IL":
                return True
        return "israel" in (req.get("PrimaryLocation") or "").lower()

    # ---------------- HTTP ----------------
    def get_json(s, url, timeout=30, tries=2):
        for i in range(tries):
            if left() < 3:
                return None
            try:
                r = s.get(url, timeout=min(timeout, max(3, left())))
                if r.status_code == 200:
                    r.encoding = "utf-8"
                    return r.json()
                if r.status_code in (400, 401, 403, 404, 422):
                    return None
            except Exception:
                pass
            time.sleep(1.0 + i)
        return None

    def list_url(host, site, filt, limit, offset):
        return ("https://%s/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
                "?onlyData=true&expand=requisitionList.secondaryLocations"
                "&finder=findReqs;siteNumber=%s,facetsList=LOCATIONS,limit=%d,offset=%d,%s"
                ",sortBy=POSTING_DATES_DESC") % (host, site, limit, offset, filt)

    def first_item(data):
        try:
            return (data.get("items") or [None])[0] or {}
        except Exception:
            return {}

    def run_filter(s, host, site, filt):
        """Page one Israel-scoped query. Returns (reqs, status) where status is
        'ok' | 'empty' | 'ignored' (filter not honoured -> global board) | 'fail'."""
        data = get_json(s, list_url(host, site, filt, PAGE, 0))
        if data is None:
            return [], "fail"
        it = first_item(data)
        page = it.get("requisitionList") or []
        total = it.get("TotalJobsCount")
        if not page:
            return [], "empty"
        il_share = sum(1 for r in page if is_il(r)) / float(len(page))
        if il_share < 0.8:
            return [], "ignored"
        out, offset, pages = list(page), len(page), 1
        while (isinstance(total, int) and offset < total and pages < MAX_PAGES
               and left() > 10):
            time.sleep(SLEEP)
            d2 = get_json(s, list_url(host, site, filt, PAGE, offset))
            p2 = (first_item(d2).get("requisitionList") or []) if d2 else []
            if not p2:
                break
            out.extend(p2)
            offset += len(p2)
            pages += 1
        return out, "ok"

    def discover_loc_id(s, host, site):
        """Stale-id self-heal: a keyword search returns a few Israel jobs, and its
        location facets carry the current Israel country facet id."""
        data = get_json(s, list_url(host, site, 'keyword="Israel"', 5, 0))
        facets = (first_item(data).get("locationsFacet") or []) if data else []
        for f in facets:
            if (f.get("Name") or "").strip().lower() == "israel" and f.get("Id"):
                return str(f.get("Id"))
        return None

    def fetch_reqs(s, host, site, loc_id):
        tried = []
        reqs, st = run_filter(s, host, site, "locationId=%s" % loc_id)
        tried.append("locationId:" + st)
        if st != "ok":
            time.sleep(SLEEP)
            reqs, st = run_filter(s, host, site, "location=Israel")
            tried.append("location=Israel:" + st)
        if st != "ok":
            time.sleep(SLEEP)
            new_id = discover_loc_id(s, host, site)
            if new_id and new_id != str(loc_id):
                time.sleep(SLEEP)
                reqs, st = run_filter(s, host, site, "locationId=%s" % new_id)
                tried.append("rediscovered %s:%s" % (new_id, st))
        if len(tried) > 1:
            print("[oracle_hcm] %s: fallback path %s" % (host, " -> ".join(tried)))
        seen, out = set(), []
        for r in reqs:
            rid = str(r.get("Id") or "").strip()
            if not rid or rid in seen or not is_il(r):
                continue
            seen.add(rid)
            out.append(r)
        return out

    def fetch_detail(s, host, site, rid):
        url = ('https://%s/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails'
               '?expand=all&onlyData=true&finder=ById;Id="%s",siteNumber=%s') % (host, rid, site)
        data = get_json(s, url, timeout=20, tries=1)
        it = first_item(data) if data else {}
        return it if it.get("Id") or it.get("Title") else None

    def compose_desc(det, req):
        """Full JD text (uncapped) from the detail record; corporate/EEO boilerplate
        (CorporateDescriptionStr) is deliberately left out. A short qualifications
        field (Oracle: "Career Level - IC2") leads; a long one is a real
        requirements block and goes last under a heading fit_desc() can find."""
        if not det:
            return html_to_text(req.get("ShortDescriptionStr") or "")
        d = html_to_text(det.get("ExternalDescriptionStr") or "")
        q = html_to_text(det.get("ExternalQualificationsStr") or "")
        r = html_to_text(det.get("ExternalResponsibilitiesStr") or "")
        head, parts = [], []
        if q and len(q) < 200:
            head.append(q)
            q = ""
        for t in (d, r):
            if t and t not in parts:
                parts.append(t)
        if q and q not in parts:
            parts.append(q if re.match(r'(?i)\s*(qualifications|requirements)', q)
                         else "Qualifications:\n" + q)
        out = "\n\n".join(head + parts)
        return out or html_to_text(det.get("ShortDescriptionStr") or req.get("ShortDescriptionStr") or "")

    REQ_HEAD = re.compile(
        r'(?im)^[ \t\-•*]*(?:essential |minimum |basic |required |preferred |key |your )?'
        r'(?:requirements|qualifications|what you.ll need|what you need|what we.re looking for|'
        r'what you bring|what you.ll bring|you have|you bring|must have|skills (?:and|&) experience|'
        r'about you|who you are)\b[^\n]{0,60}$')

    def fit_desc(full):
        """Cap at DESC_MAX without losing the requirements block: ORC JDs put
        requirements AFTER ~2.5k chars of intro/responsibilities, so a blind [:2500]
        would cut exactly what the judge needs. Keep a trimmed intro head + the
        requirements section."""
        full = (full or "").strip()
        if len(full) <= DESC_MAX:
            return full
        m = REQ_HEAD.search(full, 300)
        if not m or m.start() < DESC_MAX // 2:
            return full[:DESC_MAX].strip()
        req = full[m.start():].strip()
        head_room = max(700, DESC_MAX - len(req) - 7)
        head = full[:min(head_room, m.start())]
        cut = max(head.rfind("\n"), head.rfind(". "))
        if cut > 400:
            head = head[:cut + 1]
        out = head.rstrip() + "\n[...]\n" + req
        return out[:DESC_MAX].strip()

    # ---------------- per-brand worker ----------------
    def work(brand, host, site, loc_id, sink):
        try:
            s = requests.Session()
            s.headers.update({"User-Agent": UA, "Accept": "application/json",
                              "Accept-Language": "en-US,en;q=0.9"})
            reqs = fetch_reqs(s, host, site, loc_id)
            n_det = 0
            for r in reqs:
                try:
                    rid = str(r.get("Id")).strip()
                    title = re.sub(r'\s+', ' ', (r.get("Title") or "")).strip()
                    if not title:
                        continue
                    det = None
                    if n_det < DETAIL_CAP and left() > 8:
                        time.sleep(SLEEP)
                        det = fetch_detail(s, host, site, rid)
                        n_det += 1
                    full = compose_desc(det, r)
                    ymin, ymax = years_of(full)
                    sink.append({
                        "source": "oracle_hcm:%s" % brand.lower(),
                        "sid": rid,
                        "title": title,
                        "company": brand,
                        "city": city_of(r, det, title),
                        "url": "https://%s/hcmUI/CandidateExperience/en/sites/%s/job/%s" % (host, site, rid),
                        "level": level_of(title),
                        "years_min": ymin,
                        "years_max": ymax,
                        "tech": tech_of(title + "\n" + full),
                        "desc": fit_desc(full),
                        "active": True,
                    })
                except Exception:
                    continue
        except Exception:
            pass

    # ---------------- run brands in parallel (sequential + polite per host) ----------------
    sinks = {b: [] for b in REGISTRY}
    ex = None
    try:
        ex = ThreadPoolExecutor(max_workers=max(1, len(REGISTRY)))
        futs = [ex.submit(work, b, h, st, loc, sinks[b])
                for b, (h, st, loc) in REGISTRY.items()]
        for f in futs:
            try:
                f.result(timeout=max(1.0, left() + 5))
            except Exception:
                pass
    except Exception:
        pass
    finally:
        try:
            if ex is not None:
                ex.shutdown(wait=False)
        except Exception:
            pass

    jobs, seen = [], set()
    for b in REGISTRY:
        for j in list(sinks.get(b) or []):
            k = (j["source"], j["sid"])
            if k in seen:
                continue
            seen.add(k)
            jobs.append(j)
    return jobs


def src_smartrecruiters():
    """SmartRecruiters public postings API adapter (Wix, SanDisk).

    List:   GET https://api.smartrecruiters.com/v1/companies/{cid}/postings?country=il&limit=100&offset=N
    Detail: GET https://api.smartrecruiters.com/v1/companies/{cid}/postings/{postingId}
            -> postingUrl + jobAd.sections (jobDescription / qualifications / ...)
    No auth, no cookies, no JS. Returns only Israel postings. Never raises.
    """
    out = []
    try:
        import re
        import time
        import html as _html
        import requests

        try:
            from bs4 import BeautifulSoup
        except Exception:
            BeautifulSoup = None

        # brand (as shown in the tracker) -> SmartRecruiters company identifier.
        # Verified live 2026-09-24. NOTE: Wix is "Wix2" ("Wix" returns totalFound=0).
        REGISTRY = {
            "Wix": "Wix2",
            "SanDisk": "Sandisk",
        }

        API = "https://api.smartrecruiters.com/v1/companies/%s/postings"
        UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
        PAGE_LIMIT = 100
        MAX_PAGES = 10              # 1000 postings per company, far above real IL volume
        MAX_DETAIL = 80             # JD detail fetches per company
        DESC_CAP = 2500
        SLEEP = 0.3
        BUDGET_S = 85.0             # whole-adapter wall-clock budget
        t0 = time.time()

        def _time_left():
            return (time.time() - t0) < BUDGET_S

        sess = requests.Session()
        sess.headers.update({"User-Agent": UA, "Accept": "application/json",
                             "Accept-Language": "en-US,en;q=0.9"})

        def _get_json(url, params=None):
            for attempt in range(2):
                try:
                    r = sess.get(url, params=params, timeout=20)
                    if r.status_code == 200:
                        r.encoding = "utf-8"
                        return r.json()
                    if r.status_code in (429, 500, 502, 503, 504) and attempt == 0:
                        time.sleep(1.5)
                        continue
                    return None
                except Exception:
                    if attempt == 0:
                        time.sleep(1.0)
                        continue
                    return None
            return None

        def _clean(h):
            if not h:
                return ""
            txt = ""
            if BeautifulSoup is not None:
                try:
                    txt = BeautifulSoup(h, "html.parser").get_text(" ")
                except Exception:
                    txt = ""
            if not txt:
                txt = re.sub(r"<[^>]+>", " ", h)
            txt = _html.unescape(txt).replace(" ", " ").replace("�", " ")
            return re.sub(r"\s+", " ", txt).strip()

        def _city(loc):
            loc = loc or {}
            c = re.sub(r"\s+", " ", str(loc.get("city") or "")).strip(" ,")
            if not c:
                return "Israel"
            low = c.lower()
            if low in ("israel", "il", "isr"):
                return "Israel"
            if low.startswith("tel aviv") or low.startswith("tel-aviv"):
                return "Tel Aviv"       # "Tel Aviv-Yafo" -> "Tel Aviv"
            return c

        def _is_israel(loc):
            loc = loc or {}
            if str(loc.get("country") or "").lower() == "il":
                return True
            return "israel" in str(loc.get("fullLocation") or "").lower()

        def _level(title):
            t = (title or "").lower()
            if re.search(r"\b(intern|internship|student)\b", t):
                return "student"
            if re.search(r"\b(senior|sr\.?|lead|principal|staff|head of|director|"
                         r"architect|manager|vp|expert|experienced)\b", t):
                return "senior"
            if re.search(r"\b(junior|jr\.?|entry[- ]level|graduate)\b", t):
                return "junior"
            return ""

        def _years(text):
            t = (text or "").lower().replace("–", "-").replace("—", "-")
            if not t:
                return (None, None)

            def _near(s, e):
                # "4+ years of professional software development experience" puts
                # the word ~50 chars after the number -> wider window on the right.
                ctx = t[max(0, s - 45):min(len(t), e + 75)]
                return "experien" in ctx or "exp." in ctx

            # FIRST experience-requirement in text order wins: the headline requirement
            # comes first ("4+ years SWE ... 2-3 years as team lead" -> 4, not 2-3;
            # "5+ years testing and 2 years in API testing" -> 5).
            rx = re.compile(r"(\d{1,2})\s*(?:(?:-|to)\s*(\d{1,2})\s*)?\+?\s*(?:years?|yrs)\b")
            for m in rx.finditer(t):
                a = int(m.group(1))
                b = int(m.group(2)) if m.group(2) else None
                if a > 40 or (b is not None and not (a <= b <= 40)):
                    continue
                # "N+ years" / "N-M years" in the role/requirements text is a requirement
                # even without the word "experience" ("3+ years in data engineering");
                # a bare "N years" needs "experience" nearby (avoids "20 years of innovation").
                explicit = (b is not None or "+" in m.group(0)) and a <= 15
                if not (explicit or _near(m.start(), m.end())):
                    continue
                return (a, b)
            return (None, None)

        TECH = [
            (r"\bpython\b", "Python"), (r"\bjava\b", "Java"),
            (r"\bjavascript\b", "JavaScript"), (r"\btypescript\b", "TypeScript"),
            (r"c\+\+", "C++"), (r"\bc#|\.net\b", "C#/.NET"),
            # plain C only in unambiguous phrasings (a bare "c" is often a list letter)
            (r"\bc\s*/\s*c\+\+|\bc\s+(?:and|or|&)\s+c\+\+|\bc\s+programming|\bansi c\b"
             r"|\bembedded c\b|\b(?:in|with)\s+c\b(?![+#])", "C"),
            # "go" alone is plain English ("go live") -> only golang or "go" inside a language list
            (r"\bgolang\b|\bgo\s*\(golang\)"
             r"|\b(?:python|java|rust|kotlin|scala|node(?:\.?js)?|c\+\+),\s*go\b"
             r"|\bgo,\s*(?:python|java|rust|kotlin|scala|node|c\+\+)", "Go"),
            (r"\brust\b", "Rust"),
            (r"\bkotlin\b", "Kotlin"), (r"\bscala\b", "Scala"), (r"\bsql\b", "SQL"),
            (r"\breact\b", "React"), (r"\bangular\b", "Angular"), (r"\bvue\b", "Vue"),
            (r"\bnode(\.?js)?\b", "Node.js"), (r"\bspring\b", "Spring"),
            (r"\bkubernetes\b|\bk8s\b", "Kubernetes"), (r"\bdocker\b", "Docker"),
            (r"\bterraform\b", "Terraform"), (r"\baws\b", "AWS"),
            (r"\bgcp\b|google cloud", "GCP"), (r"\bazure\b", "Azure"),
            (r"\blinux\b", "Linux"), (r"\bembedded\b", "Embedded"), (r"\brtos\b", "RTOS"),
            (r"\bsystemverilog\b", "SystemVerilog"), (r"\bverilog\b", "Verilog"),
            (r"\buvm\b", "UVM"), (r"\bvhdl\b", "VHDL"), (r"\bfpga\b", "FPGA"),
            (r"\basic\b", "ASIC"), (r"\bpcie\b", "PCIe"), (r"\bnvme\b", "NVMe"),
            (r"\bpytorch\b", "PyTorch"), (r"\btensorflow\b", "TensorFlow"),
            (r"\bspark\b", "Spark"), (r"\bkafka\b", "Kafka"),
            (r"\bmongodb\b", "MongoDB"), (r"\bpostgres(ql)?\b", "PostgreSQL"),
            (r"\bmysql\b", "MySQL"), (r"\bredis\b", "Redis"),
            (r"\bgraphql\b", "GraphQL"), (r"\bgrpc\b", "gRPC"),
            (r"\bmicroservices?\b", "Microservices"), (r"ci/cd|ci-cd", "CI/CD"),
            (r"\bselenium\b", "Selenium"), (r"\bplaywright\b", "Playwright"),
            (r"\bcypress\b", "Cypress"), (r"\bjenkins\b", "Jenkins"),
            (r"machine learning", "Machine Learning"), (r"deep learning", "Deep Learning"),
            (r"\bnlp\b", "NLP"), (r"computer vision", "Computer Vision"),
            (r"\bllms?\b|large language model", "LLM"),
            (r"\bgen ?ai\b|generative ai", "GenAI"),
        ]

        def _tech(text):
            t = (text or "").lower()
            found = []
            for rx, name in TECH:
                try:
                    if re.search(rx, t) and name not in found:
                        found.append(name)
                except Exception:
                    pass
            return found

        def _desc_from(detail):
            """JD text: role + requirements first (company blurb last, only if room)."""
            secs = ((detail or {}).get("jobAd") or {}).get("sections") or {}

            def _sec(key):
                s = secs.get(key) or {}
                txt = _clean(s.get("text") or "")
                if not txt:
                    return ""
                label = (s.get("title") or "").strip()
                return (label + ": " + txt) if label else txt

            def _cut(s, n):
                if n <= 0:
                    return ""
                return s if len(s) <= n else s[:n].rsplit(" ", 1)[0] + " ..."

            jd, qual = _sec("jobDescription"), _sec("qualifications")
            core = (jd + " " + qual).strip()          # full text for years/tech
            # Requirements must survive the cap (the fit judge needs them): if both
            # don't fit, shrink the role description first, never below ~900 chars.
            if len(jd) + len(qual) + 2 > DESC_CAP:
                jd_room = max(900, DESC_CAP - len(qual) - 2)
                jd = _cut(jd, jd_room)
                qual = _cut(qual, DESC_CAP - len(jd) - 2)
            parts = [p for p in (jd, qual) if p]
            # boilerplate sections only if there is room left
            for key in ("additionalInformation", "companyDescription"):
                used = len("\n".join(parts))
                extra = _sec(key)
                if extra and used + 2 + len(extra) <= DESC_CAP:
                    parts.append(extra)
            desc = "\n".join(parts)
            if not desc:
                # unusual jobAd layout: fall back to any section text
                desc = " ".join(_clean((v or {}).get("text") or "")
                                for v in secs.values() if isinstance(v, dict))
                core = core or desc
            if len(desc) > DESC_CAP:
                desc = desc[:DESC_CAP].rsplit(" ", 1)[0]
            return desc, core

        seen = set()
        for brand, cid in REGISTRY.items():
            try:
                # ---- 1. list all Israel postings (paginated) ----
                postings, offset = [], 0
                for _ in range(MAX_PAGES):
                    # list pages are cheap and are the whole point -> small grace period
                    if (time.time() - t0) > BUDGET_S + 5:
                        break
                    d = _get_json(API % cid, {"country": "il", "limit": PAGE_LIMIT,
                                              "offset": offset})
                    time.sleep(SLEEP)
                    if not isinstance(d, dict):
                        break
                    content = d.get("content") or []
                    postings.extend(content)
                    total = int(d.get("totalFound") or 0)
                    offset += len(content)
                    if not content or offset >= total:
                        break

                # ---- 2. build rows, enrich the first MAX_DETAIL with JD detail ----
                n_detail, fails = 0, 0
                for p in postings:
                    try:
                        pid = str(p.get("id") or "").strip()
                        loc = p.get("location") or {}
                        if not pid or not _is_israel(loc):
                            continue
                        sid = pid           # SmartRecruiters posting ids are globally unique
                        if sid in seen:
                            continue
                        title = re.sub(r"\s+", " ", _html.unescape(p.get("name") or "")).strip()
                        if not title:
                            continue
                        url = "https://jobs.smartrecruiters.com/%s/%s" % (cid, pid)
                        desc, core = "", ""
                        # detail = JD text + canonical URL; circuit-breaker after 3 straight
                        # failures so an outage of the detail endpoint can't eat the budget
                        # (rows are still emitted with the fallback URL and empty desc).
                        if n_detail < MAX_DETAIL and fails < 3 and _time_left():
                            det = _get_json((API % cid) + "/" + pid)
                            n_detail += 1
                            time.sleep(SLEEP)
                            if isinstance(det, dict):
                                fails = 0
                                if det.get("active") is False:
                                    continue
                                url = det.get("postingUrl") or url
                                desc, core = _desc_from(det)
                            else:
                                fails += 1
                        ymin, ymax = _years(core or desc)
                        seen.add(sid)
                        out.append({
                            "source": "smartrecruiters:%s" % brand.lower(),
                            "sid": sid,
                            "title": title,
                            "company": brand,
                            "city": _city(loc),
                            "url": url,
                            "level": _level(title),
                            "years_min": ymin,
                            "years_max": ymax,
                            "tech": _tech(title + " " + (core or desc)),
                            "desc": desc,
                            "active": True,
                        })
                    except Exception:
                        continue
            except Exception:
                continue
    except Exception:
        pass
    return out


def src_google():
    """Google careers (own site, no third-party ATS) -> Israeli jobs.

    GET https://www.google.com/about/careers/applications/jobs/results?location=Israel&page=N
    is server-rendered; the job data sits in AF_initDataCallback({key: 'ds:1', ... data:<JSON>}).
    d[0] = jobs (20/page), d[2] = total, d[3] = page size. Full JD text is in the listing,
    so no per-job detail fetches are needed. Google's own experience-level facet
    (target_level=INTERN_AND_APPRENTICE / EARLY / ADVANCED / DIRECTOR_PLUS) is fetched
    separately to label level. Never raises.
    """
    out = []
    try:
        import re, json, time, html
        import requests

        SOURCE = "google"
        COMPANY = "Google"
        BASE = "https://www.google.com/about/careers/applications/jobs/results"
        UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
        MAX_PAGES = 15            # 300 jobs; Israel had 106 on 2026-09-24
        SLEEP = 0.8               # be polite to google.com
        DEADLINE = time.time() + 85
        LEVEL_FACETS = [("INTERN_AND_APPRENTICE", "student"), ("EARLY", "junior"),
                        ("ADVANCED", "senior"), ("DIRECTOR_PLUS", "senior")]

        # region tokens (mirrors config.SOUTH / JERUSALEM) so a multi-city post is
        # not labelled with a dropped region when it is also offered elsewhere
        DROP_TOKENS = ["jerusalem", "yerushalayim", "har hotzvim", "maale adumim", "mevaseret",
                       "beer sheva", "be'er sheva", "beersheba", "ashkelon", "ashdod",
                       "kiryat gat", "netivot", "sderot", "ofakim", "dimona", "eilat",
                       "yeruham", "rahat", "arad", "lehavim", "meitar", "omer", "gedera"]
        CITY_FIX = {"tel aviv-yafo": "Tel Aviv", "tel aviv yafo": "Tel Aviv",
                    "tel-aviv": "Tel Aviv", "herzliyya": "Herzliya"}

        TECH_PATTERNS = [
            (r"\bpython\b", "Python"), (r"\bjava\b", "Java"),
            (r"\bjavascript\b", "JavaScript"), (r"\btypescript\b", "TypeScript"),
            (r"c\+\+", "C++"), (r"\bc#|\.net\b", "C#/.NET"), (r"(?<![\w#+])c(?![\w#+])(?=\s*(?:/|,|\band\b|\bor\b|programming|language|code))", "C"),
            (r"\bgolang\b|\bgo\b(?=\s*(?:,|/|\)|\bor\b|\band\b|programming|language))", "Go"),
            (r"\brust\b", "Rust"), (r"\bkotlin\b", "Kotlin"), (r"\bswift\b", "Swift"),
            (r"\bruby\b", "Ruby"), (r"\bscala\b", "Scala"), (r"\bperl\b", "Perl"),
            (r"\bmatlab\b", "MATLAB"), (r"\bsql\b", "SQL"), (r"\bbash\b|\bshell script", "Shell"),
            (r"\bandroid\b", "Android"), (r"\bios\b", "iOS"),
            (r"\breact\b", "React"), (r"\bangular\b", "Angular"), (r"\bnode(?:\.?js)?\b", "Node.js"),
            (r"\bkubernetes\b|\bk8s\b", "Kubernetes"), (r"\bdocker\b", "Docker"),
            (r"\bterraform\b", "Terraform"), (r"\baws\b", "AWS"), (r"\bgcp\b", "GCP"),
            (r"\bazure\b", "Azure"), (r"\blinux\b", "Linux"), (r"\bembedded\b", "Embedded"),
            (r"\brtos\b", "RTOS"), (r"\bfirmware\b", "Firmware"),
            (r"\bverilog\b", "Verilog"), (r"\bsystemverilog\b", "SystemVerilog"),
            (r"\bvhdl\b", "VHDL"), (r"\bfpga\b", "FPGA"), (r"\basic\b", "ASIC"), (r"\buvm\b", "UVM"),
            (r"\bcuda\b", "CUDA"), (r"\bpytorch\b", "PyTorch"), (r"\btensorflow\b", "TensorFlow"),
            (r"\bjax\b", "JAX"), (r"\bspark\b", "Spark"), (r"\bkafka\b", "Kafka"),
            (r"\bgrpc\b", "gRPC"), (r"\bmicroservices?\b", "Microservices"),
            (r"ci/cd", "CI/CD"), (r"\bgit\b", "Git"),
            (r"machine learning|\bml\b", "Machine Learning"), (r"deep learning", "Deep Learning"),
            (r"\bnlp\b|natural language processing", "NLP"), (r"computer vision", "Computer Vision"),
            (r"\bllms?\b|large language model", "LLM"), (r"\bgen ?ai\b|generative ai", "GenAI"),
            (r"distributed systems?", "Distributed Systems"),
        ]

        sess = requests.Session()
        sess.headers.update({"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9",
                             "Accept": "text/html,application/xhtml+xml"})

        DS_RX = re.compile(r"AF_initDataCallback\(\{key: 'ds:1'.*?data:(.*?), sideChannel: \{\}\}\);</script>", re.S)
        ANY_RX = re.compile(r"AF_initDataCallback\(\{key: '[^']+'.*?data:(.*?), sideChannel: \{\}\}\);</script>", re.S)

        def _looks_like_results(d):
            return (isinstance(d, list) and len(d) >= 3 and (d[0] is None or isinstance(d[0], list))
                    and isinstance(d[2], int))

        def _fetch(params):
            """Return (jobs_list, total) or (None, None) on failure."""
            if time.time() > DEADLINE:
                return None, None
            try:
                r = sess.get(BASE, params=params, timeout=25)
                time.sleep(SLEEP)
                if r.status_code != 200:
                    return None, None
                txt = r.text
                cands = []
                m = DS_RX.search(txt)
                if m:
                    cands.append(m.group(1))
                cands += [x.group(1) for x in ANY_RX.finditer(txt)]
                for raw in cands:
                    try:
                        d = json.loads(raw)
                    except Exception:
                        continue
                    if _looks_like_results(d):
                        return (d[0] or []), d[2]
            except Exception:
                pass
            return None, None

        def _g(a, *idx):
            try:
                for i in idx:
                    a = a[i]
                return a
            except Exception:
                return None

        def _to_text(h):
            if not h or not isinstance(h, str):
                return ""
            t = re.sub(r"(?i)<br\s*/?>", "\n", h)
            t = re.sub(r"(?i)<li[^>]*>", "\n- ", t)
            t = re.sub(r"(?i)</(p|div|ul|ol|h\d)>", "\n", t)
            t = re.sub(r"<[^>]+>", " ", t)
            t = html.unescape(t).replace("\xa0", " ")
            t = re.sub(r"[ \t]+", " ", t)
            t = re.sub(r" *\n *", "\n", t)
            t = re.sub(r"\n{2,}", "\n", t)
            return t.strip()

        def _li_items(h):
            if not h or not isinstance(h, str):
                return []
            items = re.findall(r"(?is)<li[^>]*>(.*?)</li>", h)
            if not items:
                items = [x for x in re.split(r"\n|\. ", _to_text(h)) if x.strip()]
            return [_to_text(x) for x in items]

        YRS_RX = re.compile(r"(\d{1,2})\s*\+?\s*(?:-|to|–)?\s*(?:\d{1,2}\s*)?years?\b", re.I)

        def _years(min_quals_html):
            # Google's minimum qualifications are conjunctive bullets. Within a bullet the
            # first "N years ... experience" is the baseline path ("or 1 year with an advanced
            # degree" is an alternative). The real floor is the MAX across bullets.
            best = None
            for li in _li_items(min_quals_html):
                low = li.lower()
                for m in YRS_RX.finditer(low):
                    ctx = low[m.start():m.end() + 60]
                    if "experience" in ctx or "industry" in ctx:
                        n = int(m.group(1))
                        if 0 <= n <= 30:
                            best = n if best is None else max(best, n)
                        break
            return best

        def _title_level(title):
            tl = title.lower()
            if re.search(r"\b(intern|interns|internship|student|apprentice|apprenticeship)\b", tl):
                return "student"
            if re.search(r"\b(senior|sr\.?|staff|principal|lead|head|director|manager|architect|distinguished|fellow)\b", tl):
                return "senior"
            if re.search(r"\b(junior|jr\.?|entry[- ]level|new grad|graduate|early career)\b", tl):
                return "junior"
            return ""

        def _tech(text):
            t = (text or "").lower()
            found = []
            for pat, label in TECH_PATTERNS:
                if label in found:
                    continue
                try:
                    if re.search(pat, t):
                        found.append(label)
                except re.error:
                    continue
            return found

        def _slug(title):
            s = re.sub(r"[^a-z0-9 ]+", "", (title or "").lower())
            return re.sub(r"\s+", "-", s.strip())

        def _city(locs):
            names = []
            for loc in locs:
                disp = _g(loc, 0) or ""
                c = disp.split(",")[0].strip() if disp else ""
                if not c or c.lower() == "israel":
                    c = (_g(loc, 2) or "").strip() or "Israel"
                c = CITY_FIX.get(c.lower(), c)
                if c not in names:
                    names.append(c)
            real = [c for c in names if c.lower() != "israel"]
            if not real:
                return "Israel"
            keep = [c for c in real if not any(tok in c.lower() for tok in DROP_TOKENS)]
            return " / ".join(keep or real)

        # ---- 1) level map from Google's own experience facet ----
        level_of = {}
        for facet, lvl in LEVEL_FACETS:
            for page in range(1, 6):
                jobs, total = _fetch({"location": "Israel", "target_level": facet, "page": page})
                if not jobs:
                    break
                for j in jobs:
                    jid = _g(j, 0)
                    if jid:
                        level_of.setdefault(str(jid), lvl)
                if total is None or page * 20 >= total:
                    break

        # ---- 2) all Israel jobs ----
        seen = set()
        for page in range(1, MAX_PAGES + 1):
            jobs, total = _fetch({"location": "Israel", "page": page})
            if not jobs:
                break
            for j in jobs:
                try:
                    if not isinstance(j, list) or len(j) < 11:
                        continue
                    jid = str(_g(j, 0) or "").strip()
                    title = (_g(j, 1) or "").strip()
                    if not jid or not title or jid in seen:
                        continue
                    locs = _g(j, 9) or []
                    il_locs = [l for l in locs if isinstance(l, list) and len(l) > 5
                               and str(l[5] or "").upper() == "IL"]
                    if not il_locs:
                        continue
                    seen.add(jid)

                    resp_h = _g(j, 3, 1) or ""
                    quals_h = _g(j, 4, 1) or ""
                    about_h = _g(j, 10, 1) or ""
                    minq_h = _g(j, 19, 1) if len(j) > 19 else None
                    if not minq_h and quals_h:
                        minq_h = re.split(r"(?i)preferred qualifications", quals_h)[0]

                    quals_t = _to_text(quals_h)
                    resp_t = _to_text(resp_h)
                    about_t = _to_text(about_h)
                    parts = []
                    if quals_t:
                        parts.append(quals_t if quals_t.lower().startswith("minimum")
                                     else "Qualifications:\n" + quals_t)
                    if resp_t:
                        parts.append("Responsibilities:\n" + resp_t)
                    if about_t:
                        parts.append("About the job:\n" + about_t)
                    desc = "\n\n".join(parts)[:2500]

                    ymin = _years(minq_h)
                    level = _title_level(title) or level_of.get(jid, "")

                    out.append({
                        "source": SOURCE,
                        "sid": jid,
                        "title": title,
                        "company": COMPANY,
                        "city": _city(il_locs),
                        "url": "https://www.google.com/about/careers/applications/jobs/results/%s-%s"
                               % (jid, _slug(title)),
                        "level": level,
                        "years_min": ymin,
                        "years_max": None,
                        "tech": _tech(title + "\n" + quals_t + "\n" + resp_t),
                        "desc": desc,
                        "active": True,
                    })
                except Exception:
                    continue
            if total is not None and page * 20 >= total:
                break
    except Exception:
        pass
    return out


def src_checkpoint():
    """Check Point Software Technologies -> normalized job dicts (Israel only).

    Primary: careers.checkpoint.com own PHP/Solr search, server-rendered HTML,
      GET /index.php?m=cpcareers&a=search&fa[]=country_s:Israel&start=0,10,20...
      (page size fixed at 10; stop on an empty page or once start >= total).
    Cross-check: the same postings are mirrored to SmartRecruiters company
      "CheckPointSoftwareTechnologies2" (the careers site's APPLY button goes there).
      SR posting id "7440001" + joborderid  (e.g. 744000150936589 <-> 0936589),
      so one cheap JSON call (country=il) is unioned in by joborderid. A job that
      is live on SR but missing from the careers index (or the careers site being
      down / re-templated) therefore cannot slip through.
    Detail: /index.php?m=cpcareers&a=show&joborderid=N -> "Key Responsibilities" +
      "Qualifications" blocks (the shared "Why Join Us?" blurb is dropped).
      Capped at 80 fetches, non-senior titles first; the rest keep the short
      responsibilities snippet from the listing card (or the SR JD as fallback).
    Never raises; returns whatever was collected so far.
    """
    out = []
    try:
        import re
        import time
        import html as _html
        import requests

        UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
        BASE = "https://careers.checkpoint.com/index.php"
        SHOW = BASE + "?m=cpcareers&a=show&joborderid=%s"
        SR_CO = "CheckPointSoftwareTechnologies2"
        SR_API = "https://api.smartrecruiters.com/v1/companies/%s/postings" % SR_CO
        COMPANY = "Check Point"
        SOURCE = "checkpoint"
        PAGE = 10
        MAX_PAGES = 40            # 400 Israel jobs; today there are ~103
        DETAIL_CAP = 80
        BUDGET = 80.0             # seconds; detail loop stops early past this
        SLEEP = 0.3
        t0 = time.time()

        sess = requests.Session()
        sess.headers.update({"User-Agent": UA,
                             "Accept": "text/html,application/xhtml+xml,application/json;q=0.9",
                             "Accept-Language": "en-US,en;q=0.9"})

        def _get(url, params=None, timeout=25):
            try:
                r = sess.get(url, params=params, timeout=timeout)
                if r.status_code == 200:
                    r.encoding = r.encoding if (r.encoding and r.encoding.lower() != "iso-8859-1") else "utf-8"
                    return r
            except Exception:
                pass
            return None

        def _text(frag):
            """HTML fragment -> plain text, list items on their own lines."""
            s = frag or ""
            s = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", s)
            s = re.sub(r"(?i)<li[^>]*>", "\n- ", s)
            s = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</ul>|</ol>|</h\d>", "\n", s)
            s = re.sub(r"<[^>]+>", " ", s)
            s = _html.unescape(s).replace("\xa0", " ").replace("​", "")
            s = re.sub(r"[ \t\r\f\v]+", " ", s)
            s = re.sub(r" *\n *", "\n", s)
            s = re.sub(r"\n{2,}", "\n", s)
            return s.strip()

        def _city(loc):
            # "Israel: Tel Aviv-Yafo" / "Israel: Tel Aviv/ Hybrid (Israel)" / "Israel: Tel Aviv"
            c = (loc or "").strip()
            c = re.sub(r"(?i)^\s*israel\s*[:,\-]?\s*", "", c)
            c = re.sub(r"\([^)]*\)", " ", c)
            c = re.split(r"\s*/\s*", c)[0]
            c = re.sub(r"(?i)\b(hybrid|remote|on[- ]?site)\b", " ", c)
            c = re.sub(r"\s+", " ", c).strip(" ,;:-/")
            if re.match(r"(?i)^tel[\s-]*aviv", c):
                return "Tel Aviv"
            return c or "Israel"

        STU = re.compile(r"(?i)\b(student|intern|internship|co-?op)\b")
        JUN = re.compile(r"(?i)\b(junior|jr\.?|entry[\s-]?level|graduate|new[\s-]?grad)\b")
        SEN = re.compile(r"(?i)\b(senior|sr\.?|principal|staff|lead|leader|head of|director|"
                         r"vp|vice president|chief|distinguished)\b")

        def _level(title):
            t = title or ""
            if STU.search(t):
                return "student"
            if JUN.search(t):
                return "junior"
            if SEN.search(t):
                return "senior"
            return ""

        YRS = r"(?:years|year|yrs|yr)"
        NUMW = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
                "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
        NUMW_RX = re.compile(r"\b(" + "|".join(NUMW) + r")\b")

        def _years(q):
            """Lowest experience floor stated in the qualifications text (mirrors the
            scanner's own parse_years: a range contributes its LOW end). Also reads
            spelled-out numbers ("at least three years") which the scanner can't."""
            t = (q or "").lower().replace("–", "-").replace("—", "-")
            t = NUMW_RX.sub(lambda m: str(NUMW[m.group(1)]), t)
            best = None
            for a, b in re.findall(r"(\d{1,2})\s*(?:-|to)\s*(\d{1,2})\s*\+?\s*" + YRS, t):
                a, b = int(a), int(b)
                if a <= 25 and (best is None or a < best[0]):
                    best = (a, b if b >= a else None)
            for a in re.findall(r"(\d{1,2})\s*\+?\s*" + YRS, t):
                a = int(a)
                if a <= 25 and (best is None or a < best[0]):
                    best = (a, None)
            if best is None:
                return None, None
            return best[0], best[1]

        TECH = ["Python", "Java", "C++", "C#", "Golang", "Rust", "JavaScript", "TypeScript",
                "Node.js", "React", "Angular", "Vue", ".NET", "Spring", "Django", "Flask",
                "FastAPI", "SQL", "NoSQL", "PostgreSQL", "MySQL", "MongoDB", "Redis",
                "Elasticsearch", "Kafka", "RabbitMQ", "Spark", "Airflow", "Kubernetes", "K8s",
                "Docker", "Terraform", "Helm", "Ansible", "Jenkins", "GitHub Actions", "CI/CD",
                "AWS", "Azure", "GCP", "Linux", "Bash", "PowerShell", "Git", "REST",
                "GraphQL", "gRPC", "Microservices", "LLM", "RAG", "PyTorch", "TensorFlow",
                "Machine Learning", "Deep Learning", "NLP", "Selenium", "Playwright",
                "Cypress", "Pytest", "TCP/IP", "Networking", "Embedded", "Kernel",
                "Reverse Engineering", "Assembly", "Splunk", "SIEM", "Firewall", "VPN"]
        # plain-English collisions ("the rest of", "spark", "spring", "assembly line")
        # only count when written the way the tech is spelled
        CASED = {"REST", "Spring", "Spark", "Rust", "Helm", "RAG", "Assembly", "Kernel", "Vue"}
        TECH_RX = [(k, re.compile(r"(?<![\w.+#])" + re.escape(k) + r"(?![\w+#])",
                                  0 if k in CASED else re.I))
                   for k in TECH]

        def _tech(blob):
            found = []
            for k, rx in TECH_RX:
                if rx.search(blob or "") and k not in found:
                    found.append(k)
            return found[:20]

        CARD_RX = re.compile(
            r'<a href="https://careers\.checkpoint\.com/index\.php\?m=cpcareers&(?:amp;)?a=show&(?:amp;)?'
            r'joborderid=(\d+)"\s*>\s*(.*?)\s*</a>\s*<div class="posInfo">(.*?)(?=<div class="position">|$)',
            re.S)

        jobs = {}      # joborderid -> partial row
        order = []

        # ---------- 1) careers.checkpoint.com Israel facet ----------
        try:
            total = None
            for pg in range(MAX_PAGES):
                start = pg * PAGE
                if total is not None and start >= total:
                    break
                r = _get(BASE, params={"m": "cpcareers", "a": "search",
                                       "fa[]": "country_s:Israel", "start": start})
                if r is None:
                    break
                t = r.text
                if total is None:
                    m = re.search(r'class="currentPage">\s*\d+\s*-\s*\d+\s*of\s*(\d+)', t) or \
                        re.search(r'id="resSize">\s*(\d+)', t)
                    if m:
                        total = int(m.group(1))
                new = 0
                for m in CARD_RX.finditer(t):
                    try:
                        jid, title_html, info = m.group(1), m.group(2), m.group(3)
                        if jid in jobs:
                            continue
                        title = re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", title_html))).strip()
                        lm = re.search(r'class="place"\s*>\s*(.*?)\s*</p>', info, re.S)
                        loc = re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", lm.group(1)))).strip() if lm else ""
                        if loc and not re.match(r"(?i)^\s*israel\b", loc):
                            continue                  # facet says Israel; double-check the label
                        dm = re.search(r'class="briefcase"\s*>(.*?)</p>', info, re.S)
                        dept = ""
                        if dm:
                            dept = _text(dm.group(1)).split("|")[0].strip()
                        sm = re.search(r'<div class="resp shortResp">(.*?)</div>', info, re.S)
                        short = _text(sm.group(1)) if sm else ""
                        if not title:
                            continue
                        jobs[jid] = {"title": title, "loc": loc, "dept": dept, "short": short, "sr": None}
                        order.append(jid)
                        new += 1
                    except Exception:
                        continue
                if new == 0 and not CARD_RX.search(t):
                    break                             # ran past the last page
                time.sleep(SLEEP)
        except Exception:
            pass            # keep what was parsed; SR union below still runs

        # ---------- 2) SmartRecruiters mirror (union, catches anything missed) ----------
        try:
            offset = 0
            while offset < 1000 and time.time() - t0 < 40:
                r = _get(SR_API, params={"country": "il", "limit": 100, "offset": offset})
                if r is None:
                    break
                d = r.json()
                content = d.get("content") or []
                for p in content:
                    try:
                        pid = str(p.get("id") or "")
                        loc = p.get("location") or {}
                        if (loc.get("country") or "").lower() != "il":
                            continue
                        jid = pid[-7:] if (pid.startswith("7440001") and len(pid) == 15) else pid
                        if not jid:
                            continue
                        if jid in jobs:
                            jobs[jid]["sr"] = pid
                            continue
                        title = re.sub(r"\s+", " ", _html.unescape(p.get("name") or "")).strip()
                        if not title:
                            continue
                        dept = ((p.get("department") or {}).get("label") or
                                (p.get("function") or {}).get("label") or "")
                        jobs[jid] = {"title": title,
                                     "loc": "Israel: " + (loc.get("city") or ""),
                                     "dept": dept, "short": "", "sr": pid, "sr_only": True}
                        order.append(jid)
                    except Exception:
                        continue
                offset += 100
                if offset >= int(d.get("totalFound") or 0) or not content:
                    break
                time.sleep(SLEEP)
        except Exception:
            pass

        # ---------- 3) detail JDs (non-senior titles first, capped, time-boxed) ----------
        LIMIT = 2500

        def _fit(sections, limit=LIMIT):
            """Join sections within `limit` chars, giving each a fair share, so a long
            'Key Responsibilities' block can't push 'Qualifications' (where the years
            and stack live) past the cut."""
            sections = [s for s in sections if s]
            if not sections:
                return ""
            sep = "\n"
            n = len(sections)
            avail = limit - len(sep) * (n - 1)
            lens = [len(s) for s in sections]
            if sum(lens) <= avail:
                return sep.join(sections)
            alloc, remaining = [0] * n, avail
            for k, i in enumerate(sorted(range(n), key=lambda i: lens[i])):
                alloc[i] = min(lens[i], remaining // (n - k))
                remaining -= alloc[i]
            return sep.join(s[:a].rstrip() for s, a in zip(sections, alloc))[:limit]

        QHEAD = re.compile(r"(?i)qualif|requirement|what you (?:will )?bring|who you are|"
                           r"about you|must have|what we.re looking for|you have")
        NICE = re.compile(r"(?i)advantage|nice to have|bonus|great if|a plus|preferred")

        def _careers_detail(jid):
            r = _get(SHOW % jid, timeout=12)
            if r is None:
                return "", "", ""
            t = r.text
            if "joborderid=%s" % jid not in t:
                return "", "", ""
            parts, quals = [], ""
            for m in re.finditer(r'<div class="info">\s*<h3>\s*(.*?)\s*</h3>(.*?)</div>', t, re.S):
                head = _text(m.group(1))
                if not head or re.search(r"(?i)why join", head):
                    continue
                body = _text(m.group(2))
                if not body:
                    continue
                parts.append(head + ":\n" + body)
                if QHEAD.search(head) and not NICE.search(head):
                    quals += " " + body
            return _fit(parts), quals, "\n".join(parts)

        def _sr_detail(pid):
            r = _get(SR_API + "/" + pid, timeout=12)
            if r is None:
                return "", "", ""
            d = r.json()
            secs = ((d.get("jobAd") or {}).get("sections") or {})
            parts, quals = [], ""
            for key in ("jobDescription", "qualifications", "additionalInformation"):
                s = secs.get(key) or {}
                body = _text(s.get("text") or "")
                if not body or re.search(r"(?i)^why join", s.get("title") or ""):
                    continue
                parts.append(((s.get("title") or key).strip()) + ":\n" + body)
                if key == "qualifications":
                    quals += " " + body
            return _fit(parts), quals, "\n".join(parts)

        prio = sorted(order, key=lambda j: (1 if _level(jobs[j]["title"]) == "senior" else 0))
        fetched = 0
        for jid in prio:
            if fetched >= DETAIL_CAP or time.time() - t0 > BUDGET:
                break
            job = jobs[jid]
            desc, quals, full = "", "", ""
            try:
                if not job.get("sr_only"):
                    desc, quals, full = _careers_detail(jid)
                    fetched += 1
                    time.sleep(SLEEP)
                if (not desc and job.get("sr") and fetched < DETAIL_CAP
                        and time.time() - t0 <= BUDGET):
                    desc, quals, full = _sr_detail(job["sr"])
                    fetched += 1
                    time.sleep(SLEEP)
            except Exception:
                pass
            if desc:
                job["desc"], job["quals"], job["full"] = desc, quals, full

        # ---------- 4) normalize ----------
        for jid in order:
            try:
                job = jobs[jid]
                title = job["title"]
                desc = job.get("desc") or (("Key Responsibilities:\n" + job["short"]) if job.get("short") else "")
                quals = job.get("quals") or ""
                ymin, ymax = _years(quals) if quals else _years(desc)
                if job.get("sr_only") and job.get("sr"):
                    url = "https://jobs.smartrecruiters.com/%s/%s" % (SR_CO, job["sr"])
                else:
                    url = SHOW % jid
                out.append({
                    "source": SOURCE,
                    "sid": str(jid),
                    "title": title,
                    "company": COMPANY,
                    "city": _city(job.get("loc")),
                    "url": url,
                    "level": _level(title),
                    "years_min": ymin,
                    "years_max": ymax,
                    "tech": _tech(title + "\n" + (job.get("full") or desc)),
                    "desc": desc[:LIMIT],
                    "active": True,
                })
            except Exception:
                continue
    except Exception:
        pass
    return out


def src_meta():
    """Meta (metacareers.com) adapter - Meta's own Relay/GraphQL careers site, no outside ATS.

    Flow (plain HTTP, no login / cookies / JS rendering):
      1. GET /jobsearch/ with browser navigate-style sec-fetch-* headers -> fresh LSD token
         (a bare GET without sec-fetch-* gets an HTTP 400 "Sorry, something went wrong").
      2. POST /graphql CareersJobSearchResultsV2DataQuery. doc_id is tried hardcoded first;
         if Meta rotated it, the current doc_id is discovered at runtime from the
         static.xx.fbcdn.net rsrc.php bundles linked from the /jobsearch/ HTML, and the V1
         query (CareersJobSearchResultsDataQuery) is the last fallback.
         Two searches, unioned by id: the whole global list (offices=[], ~1000 jobs, one
         response, no paging) filtered locally for Israel, plus offices=["Tel Aviv, Israel"].
      3. Per Israeli job: GET /profile/job_details/{id}/ and read the schema.org JobPosting
         ld+json (description + responsibilities + qualifications) for desc/years/tech.
    Never raises: on any failure returns what was collected so far (or []).
    """
    import json
    import re
    import time
    import html as _html

    out = []
    try:
        import requests
    except Exception:
        return out

    SOURCE = "metacareers:meta"
    COMPANY = "Meta"
    BASE = "https://www.metacareers.com"
    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
    T0 = time.time()
    BUDGET_S = 85            # hard wall for the whole adapter
    DETAIL_STOP_S = 70       # stop starting new JD fetches after this
    MAX_DETAIL = 80
    SLEEP = 0.3

    # Relay operations, newest first: (friendly_name, fallback doc_id, response key).
    # doc_ids verified live 2026-09-24; they rotate on Meta builds -> runtime discovery below.
    OPS = [
        ("CareersJobSearchResultsV2DataQuery", "27129360303422352", "job_search_with_featured_jobs_v2"),
        ("CareersJobSearchResultsDataQuery", "27506805582236862", "job_search_with_featured_jobs"),
    ]
    TLV_OFFICE = "Tel Aviv, Israel"

    NAV = {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "sec-fetch-dest": "document", "sec-fetch-mode": "navigate",
        "sec-fetch-site": "none", "sec-fetch-user": "?1",
        "upgrade-insecure-requests": "1",
    }

    IL_RE = re.compile(
        r"\bisrael\b|tel[\s-]?aviv|\bhaifa\b|herzl?iy?a|petah?\s*tikv?a|ra'?anana|jerusalem|"
        r"yokneam|yoqneam|be'?er\s*sheva|beersheba|rehovot|netanya|kfar\s*saba|ramat\s*gan|"
        r"hod\s*hasharon|caesarea|modi'?in|holon|ashdod|airport\s*city|or\s*yehuda", re.I)

    TECH_PATTERNS = [
        (r"\bpython\b", "Python"), (r"\bjava\b", "Java"),
        (r"\bjavascript\b", "JavaScript"), (r"\btypescript\b", "TypeScript"),
        (r"c\+\+", "C++"), (r"\bc#|\.net\b", "C#/.NET"), (r"\bgolang\b", "Go"),
        (r"\brust\b", "Rust"), (r"\bkotlin\b", "Kotlin"), (r"\bswift\b", "Swift"),
        (r"\bphp\b|\bhacklang\b", "PHP"), (r"\bscala\b", "Scala"), (r"\bsql\b", "SQL"),
        (r"\breact\b", "React"), (r"\bnode(\.?js)?\b", "Node.js"), (r"\bgraphql\b", "GraphQL"),
        (r"\bkubernetes\b|\bk8s\b", "Kubernetes"), (r"\bdocker\b", "Docker"),
        (r"\baws\b", "AWS"), (r"\blinux\b", "Linux"), (r"\bembedded\b", "Embedded"),
        (r"\bcuda\b", "CUDA"), (r"\bpytorch\b", "PyTorch"), (r"\btensorflow\b", "TensorFlow"),
        (r"scikit", "scikit-learn"), (r"\bspark\b", "Spark"), (r"\bhadoop\b", "Hadoop"),
        (r"\bkafka\b", "Kafka"), (r"\bandroid\b", "Android"), (r"\bios\b", "iOS"),
        (r"distributed systems?", "Distributed Systems"),
        (r"machine learning|\bml\b", "Machine Learning"), (r"deep learning", "Deep Learning"),
        (r"\bnlp\b|natural language", "NLP"), (r"computer vision", "Computer Vision"),
        (r"\bllms?\b|large language model", "LLM"), (r"gen ?ai|generative ai", "GenAI"),
    ]

    def _left():
        return BUDGET_S - (time.time() - T0)

    def _clean(txt):
        if not txt:
            return ""
        t = str(txt).replace("&nbsp;", "; ")
        t = re.sub(r"<\s*(br|/p|/li|/div)[^>]*>", "; ", t, flags=re.I)
        t = re.sub(r"<[^>]+>", " ", t)
        t = _html.unescape(t).replace("\xa0", " ")
        t = re.sub(r"\s*;\s*(;\s*)+", "; ", t)
        t = re.sub(r"\s+", " ", t).strip(" ;")
        return t

    def _years(text):
        t = (text or "").lower()
        if not t:
            return (None, None)

        def _near(a, b):
            c = t[max(0, a - 45):b + 45]
            return "experien" in c or "exp." in c

        for m in re.finditer(r"(\d{1,2})\s*(?:[-–]|to)\s*(\d{1,2})\s*\+?\s*years?", t):
            a, b = int(m.group(1)), int(m.group(2))
            if a <= b <= 40 and _near(m.start(), m.end()):
                return (a, b)
        for pat in (r"(\d{1,2})\s*\+\s*years?",
                    r"(?:at least|minimum(?: of)?|over|more than)\s*(\d{1,2})\s*years?",
                    r"(\d{1,2})\s*years?"):
            for m in re.finditer(pat, t):
                a = int(m.group(1))
                if a <= 40 and _near(m.start(), m.end()):
                    return (a, None)
        return (None, None)

    def _level(title, ymin, ymax):
        tl = (title or "").lower()
        if re.search(r"\b(intern|interns|internship|student|co-?op)\b", tl):
            return "student"
        if re.search(r"\b(university grad|new grad|graduate|junior|jr\.?|entry[- ]level|early career)\b", tl):
            return "junior"
        if re.search(r"\b(senior|sr\.?|staff|principal|lead|leadership|tech lead|architect|director|head of|distinguished)\b", tl):
            return "senior"
        if ymin is not None and ymin >= 5:
            return "senior"
        if ymax is not None and ymax <= 2:
            return "junior"
        return ""

    def _tech(text):
        t = (text or "").lower()
        found = []
        for pat, label in TECH_PATTERNS:
            if label not in found and re.search(pat, t):
                found.append(label)
        return found

    def _city(locs):
        for loc in locs or []:
            if IL_RE.search(loc or ""):
                parts = [p.strip() for p in str(loc).split(",") if p.strip()]
                parts = [p for p in parts if p.lower() not in ("israel", "il")]
                c = parts[0] if parts else ""
                if not c or re.search(r"remote|anywhere|multiple", c, re.I):
                    return "Israel"
                return c
        return ""

    def _parse_gql(text, key):
        """-> list of job dicts, or None if the response is not a valid result."""
        if not text:
            return None
        t = text.strip()
        if t.startswith("for (;;);"):
            t = t[9:]
        if not t.startswith("{"):
            return None                      # HTML error page (anti-bot 400 etc.)
        try:
            d = json.loads(t)
        except Exception:
            try:                             # streamed multi-part: first line is the payload
                d = json.loads(t.splitlines()[0])
            except Exception:
                return None
        node = ((d or {}).get("data") or {}).get(key)
        if not isinstance(node, dict):
            return None
        jobs = node.get("all_jobs")
        if not isinstance(jobs, list):
            return None
        return list(jobs) + [j for j in (node.get("featured_jobs") or []) if isinstance(j, dict)]

    try:
        sess = requests.Session()

        # ---- 1. bootstrap: LSD token + datr cookie ----
        page = ""
        try:
            r = sess.get(BASE + "/jobsearch/", headers=NAV, timeout=25)
            page = r.text or ""
        except Exception:
            page = ""
        m = re.search(r'"LSD",\[\],\{"token":"([^"]+)"', page)
        lsd = m.group(1) if m else "AVqbxe3J_YA"   # any value works if form field == header

        gql_headers = {
            "User-Agent": UA, "Accept": "*/*", "Accept-Language": "en-US,en;q=0.9",
            "Content-Type": "application/x-www-form-urlencoded", "x-fb-lsd": lsd,
            "Origin": BASE, "Referer": BASE + "/jobsearch/",
            "sec-fetch-dest": "empty", "sec-fetch-mode": "cors", "sec-fetch-site": "same-origin",
        }

        def _search(name, doc_id, key, offices):
            si = {"q": None, "divisions": [], "offices": offices, "roles": [],
                  "leadership_levels": [], "saved_jobs": [], "saved_searches": [],
                  "sub_teams": [], "teams": [], "is_leadership": False,
                  "is_remote_only": False, "sort_by_new": False, "results_per_page": None}
            data = {"lsd": lsd, "fb_api_caller_class": "RelayModern",
                    "fb_api_req_friendly_name": name,
                    "variables": json.dumps({"search_input": si, "isLoggedIn": False,
                                             "viewasUserID": None}),
                    "doc_id": doc_id, "server_timestamps": "true"}
            h = dict(gql_headers, **{"x-fb-friendly-name": name})
            try:
                g = sess.post(BASE + "/graphql", data=data, headers=h,
                              timeout=max(5, min(45, _left())))
                time.sleep(SLEEP)
            except Exception:
                return None
            if g.status_code != 200:
                return None
            return _parse_gql(g.text, key)

        def _discover():
            """Current doc_ids from the rsrc.php JS bundles linked by /jobsearch/."""
            found = {}
            if not page:
                return found
            srcs = re.findall(r'src="(https://static\.xx\.fbcdn\.net/rsrc\.php/[^"]+?\.js[^"]*)"', page)
            srcs += [u.replace("\\/", "/") for u in re.findall(
                r'"(https:\\/\\/static\.xx\.fbcdn\.net\\/rsrc\.php\\/[^"]+?\.js[^"]*)"', page)]
            seen_u = []
            for u in srcs:
                u = _html.unescape(u)
                if u not in seen_u:
                    seen_u.append(u)
            names = [o[0] for o in OPS]
            for u in seen_u[:40]:
                if _left() < 45 or all(n in found for n in names):
                    break
                try:
                    js = sess.get(u, headers={"User-Agent": UA, "Accept": "*/*"}, timeout=20).text
                    time.sleep(SLEEP)
                except Exception:
                    continue
                for n in names:
                    mm = re.search(r'__d\("' + n + r'_[A-Za-z_]*RelayOperation",\[\],\(function\([^)]*\)\{[^}]*?exports\s*=\s*"(\d+)"', js)
                    if mm and n not in found:
                        found[n] = mm.group(1)
            return found

        # ---- 2. search (hardcoded doc_id -> discovered doc_id -> V1 fallback) ----
        jobs_by_id = {}
        ok = False
        attempts = [(n, d, k) for (n, d, k) in OPS[:1]]
        discovered = None
        tried = set()
        while True:
            for (name, doc_id, key) in attempts:
                if (name, doc_id) in tried or _left() < 25:
                    continue
                tried.add((name, doc_id))
                res_all = _search(name, doc_id, key, [])
                res_tlv = _search(name, doc_id, key, [TLV_OFFICE])
                for res in (res_all, res_tlv):
                    if res is None:
                        continue
                    ok = True
                    for j in res:
                        jid = str(j.get("id") or "").strip()
                        if jid and jid not in jobs_by_id:
                            jobs_by_id[jid] = j
                if ok:
                    break
            if ok or discovered is not None or _left() < 30:
                break
            discovered = _discover()
            attempts = []
            for (n, d, k) in OPS:
                if n in discovered:
                    attempts.append((n, discovered[n], k))
            attempts += [(n, d, k) for (n, d, k) in OPS[1:]]   # V1 hardcoded as last resort
        if not ok:
            return out

        # ---- 3. keep Israel only ----
        il_jobs = []
        for jid, j in jobs_by_id.items():
            locs = [str(x) for x in (j.get("locations") or []) if x]
            if any(IL_RE.search(x) for x in locs):
                il_jobs.append((jid, j, locs))

        # ---- 4. JD detail via JobPosting ld+json ----
        n_detail = 0
        for jid, j, locs in il_jobs:
            title = _html.unescape(str(j.get("title") or "")).strip()
            if not title:
                continue
            city = _city(locs) or "Israel"
            desc = ""
            quals = ""
            full_text = ""
            if n_detail < MAX_DETAIL and (time.time() - T0) < DETAIL_STOP_S and _left() > 8:
                n_detail += 1
                for path in ("/profile/job_details/%s/" % jid, "/jobs/%s/" % jid):
                    try:
                        r = sess.get(BASE + path, headers=dict(NAV, **{"sec-fetch-site": "same-origin"}),
                                     timeout=max(5, min(25, _left() - 3)))
                        time.sleep(SLEEP)
                    except Exception:
                        continue
                    if r.status_code != 200:
                        continue
                    jp = None
                    for blob in re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', r.text or "", re.S):
                        try:
                            d = json.loads(blob)
                        except Exception:
                            continue
                        for cand in (d if isinstance(d, list) else [d]):
                            if isinstance(cand, dict) and cand.get("@type") == "JobPosting":
                                jp = cand
                                break
                        if jp:
                            break
                    if not jp:
                        continue
                    # Qualifications before Responsibilities so years/skills survive the
                    # 2500-char cap; Meta's intro paragraph is mostly boilerplate -> trimmed.
                    parts = []
                    dsc = _clean(jp.get("description"))
                    if dsc:
                        parts.append(dsc[:700])
                    quals = _clean(jp.get("qualifications"))
                    if quals:
                        parts.append("Qualifications: " + quals)
                    resp = _clean(jp.get("responsibilities"))
                    if resp:
                        parts.append("Responsibilities: " + resp)
                    full_text = "\n".join(parts)
                    desc = full_text[:2500]
                    # a more precise Israeli city from the structured location, if any
                    try:
                        jl = jp.get("jobLocation") or []
                        for place in (jl if isinstance(jl, list) else [jl]):
                            adr = (place or {}).get("address") or {}
                            if str(adr.get("addressCountry", "")).upper() in ("IL", "ISRAEL"):
                                loc_c = str(adr.get("addressLocality") or "").strip()
                                if loc_c and not re.search(r"remote", loc_c, re.I) and city == "Israel":
                                    city = loc_c
                                break
                    except Exception:
                        pass
                    break
            ymin, ymax = _years(quals or desc)
            out.append({
                "source": SOURCE,
                "sid": jid,
                "title": title,
                "company": COMPANY,
                "city": city,
                "url": "%s/jobs/%s/" % (BASE, jid),
                "level": _level(title, ymin, ymax),
                "years_min": ymin,
                "years_max": ymax,
                "tech": _tech(title + " " + (full_text or desc)),
                "desc": desc,
                "active": True,
            })
    except Exception:
        return out
    return out


def src_booking():
    """Booking.com careers adapter (iCIMS Jibe, jobs.booking.com).

    List:  GET https://jobs.booking.com/api/jobs?location=Israel&page=N&limit=100
           -> {"jobs": [{"data": {...}}], "totalCount": N}; page is 1-based, limit max 100
           (limit=200 -> HTTP 422). The full JD HTML is inline in data.description,
           so no per-job detail fetches are needed.
    Safety net: the unfiltered feed (/api/jobs?page=N&limit=100, ~133 jobs worldwide in
           2-3 pages) is also crawled, so a multi-location job whose Israel site is only an
           *additional* location still gets picked up.
    Israel test uses data.country / full_location / additional_locations, NOT
    country_code (the unfiltered feed returns the Tel Aviv jobs with country_code "MX").
    Public page: https://jobs.booking.com/booking/jobs/{req_id}?lang=en-us
    No auth, no cookies, no JS. Returns only Israel jobs. Never raises.
    """
    out = []
    try:
        import re
        import time
        import html as _html
        import datetime as _dt
        import requests

        # brand shown in the tracker -> Jibe tenant config. One tenant today; kept as a
        # registry so a sister brand on the same Jibe stack can be added in one line.
        REGISTRY = {
            "Booking.com": {
                "api": "https://jobs.booking.com/api/jobs",
                "job_url": "https://jobs.booking.com/booking/jobs/%s?lang=en-us",
                "source": "jibe:booking",
            },
        }

        UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
        PAGE_LIMIT = 100            # API maximum (200 -> 422)
        MAX_PAGES = 20              # 2000 jobs, far above the real global volume
        DESC_CAP = 2500
        SLEEP = 0.3
        BUDGET_S = 85.0
        t0 = time.time()

        def _time_left():
            return (time.time() - t0) < BUDGET_S

        sess = requests.Session()
        sess.headers.update({"User-Agent": UA, "Accept": "application/json",
                             "Accept-Language": "en-US,en;q=0.9"})

        def _get_json(url, params=None):
            for attempt in range(2):
                try:
                    r = sess.get(url, params=params, timeout=20)
                    if r.status_code == 200:
                        r.encoding = "utf-8"
                        return r.json()
                    if r.status_code in (429, 500, 502, 503, 504) and attempt == 0:
                        time.sleep(1.5)
                        continue
                    return None
                except Exception:
                    if attempt == 0:
                        time.sleep(1.0)
                        continue
                    return None
            return None

        def _clean(h):
            """HTML -> plain text, keeping paragraph / bullet line breaks."""
            if not h:
                return ""
            try:
                h = str(h)
                h = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", h)
                h = re.sub(r"(?i)<li[^>]*>", "\n- ", h)
                h = re.sub(r"(?i)<br\s*/?>|</(?:p|li|div|h[1-6]|ul|ol|tr|table)>", "\n", h)
                h = re.sub(r"<[^>]+>", " ", h)
                h = _html.unescape(h).replace("\xa0", " ").replace(chr(0xFFFD), " ")
                lines = []
                for ln in h.split("\n"):
                    ln = re.sub(r"[ \t\r\f\v]+", " ", ln).strip()
                    if ln and ln != "-":
                        lines.append(ln)
                return "\n".join(lines)
            except Exception:
                return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", str(h))).strip()

        def _norm_city(c):
            c = re.sub(r"\s+", " ", str(c or "")).strip(" ,")
            if not c:
                return "Israel"
            low = c.lower()
            if low in ("israel", "il", "isr"):
                return "Israel"
            if low.startswith("tel aviv") or low.startswith("tel-aviv"):
                return "Tel Aviv"       # "Tel Aviv-Yafo" -> "Tel Aviv"
            return c

        def _israel_city(d):
            """Return the Israeli city for this job, or None if it has no Israel site."""
            country = str(d.get("country") or "").strip().lower()
            ccode = str(d.get("country_code") or "").strip().upper()
            if country == "israel" or (not country and ccode == "IL"):
                return _norm_city(d.get("city"))
            full = str(d.get("full_location") or "")
            for seg in full.split(";"):
                if "israel" in seg.lower():
                    parts = [p.strip() for p in seg.split(",") if p.strip()]
                    city = parts[0] if parts and parts[0].lower() != "israel" else ""
                    return _norm_city(city)
            addl = str(d.get("additional_locations") or "")
            if "israel" in addl.lower():
                # python-repr list of dicts: "[{'city': 'Tel Aviv', ..., 'country': 'Israel', ...}]"
                for blob in re.findall(r"\{[^{}]*\}", addl):
                    if re.search(r"['\"]country['\"]\s*:\s*['\"]israel['\"]", blob, re.I):
                        m = re.search(r"['\"]city['\"]\s*:\s*['\"]([^'\"]*)['\"]", blob)
                        return _norm_city(m.group(1) if m else "")
                return "Israel"
            return None

        def _expired(d):
            try:
                s = str(d.get("posting_expiry_date") or "")[:10]
                if not re.match(r"\d{4}-\d{2}-\d{2}$", s):
                    return False
                return _dt.date.fromisoformat(s) < _dt.datetime.utcnow().date()
            except Exception:
                return False

        def _level(title):
            t = (title or "").lower()
            if re.search(r"\b(intern|internship|student)\b", t):
                return "student"
            if re.search(r"\b(senior|sr\.?|lead|principal|staff|head of|director|"
                         r"architect|manager|vp|expert|experienced)\b", t):
                return "senior"
            if re.search(r"\b(junior|jr\.?|entry[- ]level|graduate)\b", t):
                return "junior"
            return ""

        def _years(text):
            t = (text or "").lower().replace(chr(0x2013), "-").replace(chr(0x2014), "-")
            if not t:
                return (None, None)

            def _near(s, e):
                ctx = t[max(0, s - 45):min(len(t), e + 75)]
                return "experien" in ctx or "exp." in ctx

            # first experience requirement in text order wins (headline requirement first)
            rx = re.compile(r"(\d{1,2})\s*(?:(?:-|to)\s*(\d{1,2})\s*)?\+?\s*(?:years?|yrs)\b")
            for m in rx.finditer(t):
                a = int(m.group(1))
                b = int(m.group(2)) if m.group(2) else None
                if a > 40 or (b is not None and not (a <= b <= 40)):
                    continue
                explicit = (b is not None or "+" in m.group(0)) and a <= 15
                if not (explicit or _near(m.start(), m.end())):
                    continue
                return (a, b)
            return (None, None)

        TECH = [
            (r"\bpython\b|\bpyspark\b", "Python"), (r"\bjava\b", "Java"),
            (r"\bjavascript\b", "JavaScript"), (r"\btypescript\b", "TypeScript"),
            (r"c\+\+", "C++"), (r"\bc#|\.net\b", "C#/.NET"),
            (r"\bgolang\b|\bgo\s*\(golang\)"
             r"|\b(?:python|java|rust|kotlin|scala|node(?:\.?js)?|c\+\+),\s*go\b"
             r"|\bgo,\s*(?:python|java|rust|kotlin|scala|node|c\+\+)", "Go"),
            (r"\brust\b", "Rust"),
            (r"\bkotlin\b", "Kotlin"), (r"\bscala\b", "Scala"), (r"\bsql\b", "SQL"),
            (r"\bangular\b", "Angular"), (r"\bvue\b", "Vue"),
            (r"\bnode(\.?js)?\b", "Node.js"), (r"\bspring\b", "Spring"),
            (r"\bkubernetes\b|\bk8s\b", "Kubernetes"), (r"\bdocker\b", "Docker"),
            (r"\bterraform\b", "Terraform"), (r"\baws\b", "AWS"),
            (r"\bgcp\b|google cloud", "GCP"), (r"\bazure\b", "Azure"),
            (r"\blinux\b", "Linux"), (r"\bembedded\b", "Embedded"),
            (r"\bpytorch\b", "PyTorch"), (r"\btensorflow\b", "TensorFlow"),
            (r"\bspark\b|\bpyspark\b", "Spark"), (r"\bkafka\b", "Kafka"),
            (r"\bflink\b", "Flink"), (r"\bsnowflake\b", "Snowflake"),
            (r"\bairflow\b", "Airflow"), (r"\bdbt\b", "dbt"),
            (r"\bmongodb\b", "MongoDB"), (r"\bpostgres(ql)?\b", "PostgreSQL"),
            (r"\bmysql\b", "MySQL"), (r"\bredis\b", "Redis"),
            (r"\bcassandra\b", "Cassandra"), (r"\bdynamodb\b", "DynamoDB"),
            (r"\bgraphql\b", "GraphQL"), (r"\bgrpc\b", "gRPC"),
            (r"\bmicroservices?\b", "Microservices"), (r"ci/cd|ci-cd", "CI/CD"),
            (r"\bselenium\b", "Selenium"), (r"\bplaywright\b", "Playwright"),
            (r"\bcypress\b", "Cypress"), (r"\bjenkins\b", "Jenkins"),
            (r"machine learning", "Machine Learning"), (r"deep learning", "Deep Learning"),
            (r"\bnlp\b", "NLP"), (r"computer vision", "Computer Vision"),
            (r"\bllms?\b|large language model", "LLM"),
            (r"\bgen ?ai\b|generative ai", "GenAI"),
            (r"\bagentic\b|\bai agents?\b", "AI Agents"),
            (r"\bmcp\b|model context protocol", "MCP"),
        ]

        def _tech(text):
            raw = text or ""
            t = raw.lower()
            found = []
            # case-sensitive: the ML JDs mention the "ReAct" agent pattern, not React
            if re.search(r"\bReact(?:\.?js)?\b|\bREACT\b", raw):
                found.append("React")
            for rx, name in TECH:
                try:
                    if re.search(rx, t) and name not in found:
                        found.append(name)
                except Exception:
                    pass
            return found

        # Booking JD layout: "About Us:" (company blurb) -> "About the team:" /
        # "Role Description:" -> "Key Job Responsibilities and Duties:" ->
        # "Qualifications & Skills:" -> "Benefits & Perks" / DEI / "Application Process:"
        # (boilerplate). Keep role + requirements; requirements must survive the cap.
        RX_ROLE = re.compile(r"(?i)\b(about the team|leadership\s*/\s*team quote|team quote|"
                             r"role description|about the role|the role|"
                             r"key job responsibilities(?: and duties)?|responsibilities)\s*:")
        RX_QUAL = re.compile(r"(?i)\b(qualifications?\s*(?:&|and)\s*skills|qualifications|"
                             r"requirements|what you.ll (?:need|bring)|who you are|"
                             r"skills (?:&|and) experience)\s*:")
        RX_TAIL = re.compile(r"(?i)\b(benefits\s*(?:&|and)\s*perks|"
                             r"diversity,\s*equity\s*(?:&|and)\s*inclusion|"
                             r"application process\s*:|pre-employment screening|"
                             r"booking\.com is proud to be an equal opportunity|"
                             r"booking holdings is proud to be an equal opportunity)")

        RX_HEAD = re.compile(r"(?<!\n)(?:About the team|Leadership\s*/\s*Team Quote|"
                             r"Role Description|Key Job Responsibilities and Duties|"
                             r"Qualifications\s*&\s*Skills|Benefits\s*&\s*Perks[^:\n]{0,60}|"
                             r"Application Process)\s*:")

        def _cut(s, n):
            if n <= 0:
                return ""
            if len(s) <= n:
                return s
            head = s[:n - 4]
            k = head.rfind("\n")
            if k > n * 0.6:                 # end on a whole section when possible
                return head[:k].rstrip() + " ..."
            return head.rsplit(" ", 1)[0] + " ..."

        def _desc_from(d):
            text = _clean(d.get("description") or "")
            q_extra = d.get("qualifications")
            if q_extra and str(q_extra).strip().lower() not in ("none", "null", "[]", ""):
                qx = _clean(q_extra)
                if qx and qx not in text:
                    text = (text + "\nQualifications: " + qx).strip()
            if not text:
                return "", ""
            # the feed often ships the JD pre-flattened to one line: put section heads
            # on their own lines so the desc stays readable
            text = RX_HEAD.sub(lambda m: "\n" + m.group(0), text)
            text = re.sub(r"[ \t]+\n", "\n", text).strip()
            m_role = RX_ROLE.search(text)
            role_start = m_role.start() if m_role else 0
            m_qual = RX_QUAL.search(text, role_start)
            m_tail = RX_TAIL.search(text, m_qual.end() if m_qual else role_start + 1)
            tail_start = m_tail.start() if m_tail else len(text)
            if m_qual and m_qual.start() < tail_start:
                role = text[role_start:m_qual.start()].strip()
                qual = text[m_qual.start():tail_start].strip()
            else:
                role = text[role_start:tail_start].strip()
                qual = ""
            if not (role or qual):
                role = text
            core = (role + "\n" + qual).strip()     # full text for years / tech
            if len(role) + len(qual) + 1 > DESC_CAP:
                role_room = max(900, DESC_CAP - len(qual) - 1)
                role = _cut(role, role_room)
                qual = _cut(qual, DESC_CAP - len(role) - 1)
            desc = "\n".join(p for p in (role, qual) if p)
            if len(desc) > DESC_CAP:
                desc = desc[:DESC_CAP].rsplit(" ", 1)[0]
            return desc, core

        for brand, cfg in REGISTRY.items():
            if not _time_left():
                break
            try:
                api = cfg["api"]
                jobs = []

                def _crawl(extra):
                    page, got = 1, 0
                    while page <= MAX_PAGES and _time_left():
                        params = {"page": page, "limit": PAGE_LIMIT}
                        params.update(extra)
                        d = _get_json(api, params)
                        time.sleep(SLEEP)
                        if not isinstance(d, dict):
                            break
                        batch = d.get("jobs") or []
                        jobs.extend(batch)
                        got += len(batch)
                        try:
                            total = int(d.get("totalCount") or 0)
                        except Exception:
                            total = 0
                        if not batch or len(batch) < PAGE_LIMIT or got >= total:
                            break
                        page += 1

                # 1) Israel-filtered feed (the verified primary path)
                _crawl({"location": "Israel"})
                # 2) global feed as a safety net for multi-location postings
                _crawl({})

                seen = set()
                for j in jobs:
                    try:
                        d = (j or {}).get("data") or {}
                        rid = str(d.get("req_id") or d.get("slug") or "").strip()
                        if not rid or rid in seen:
                            continue
                        city = _israel_city(d)
                        if city is None:
                            continue
                        if str(d.get("searchable") or "True").lower() == "false":
                            continue
                        if str(d.get("internal") or "False").lower() == "true":
                            continue
                        if _expired(d):
                            continue
                        title = re.sub(r"\s+", " ", _html.unescape(str(d.get("title") or ""))).strip()
                        if not title:
                            continue
                        desc, core = _desc_from(d)
                        ymin, ymax = _years(core or desc)
                        seen.add(rid)
                        out.append({
                            "source": cfg["source"],
                            "sid": rid,
                            "title": title,
                            "company": brand,
                            "city": city,
                            "url": cfg["job_url"] % rid,
                            "level": _level(title),
                            "years_min": ymin,
                            "years_max": ymax,
                            "tech": _tech(title + " " + (core or desc)),
                            "desc": desc,
                            "active": True,
                        })
                    except Exception:
                        continue
            except Exception:
                continue
    except Exception:
        pass
    return out


def src_sap():
    """SAP -> Israel jobs (SAP Labs Israel, Ra'anana).

    SAP is mid-migration between two careers sites (verified live 2026-09-24, plain HTTP,
    browser UA, no cookies/JS):

      A. careers.sap.com  - legacy SuccessFactors Career Site Builder (CSB). Holds the real jobs.
         1. GET /search/?q=&optionsFacetsDD_country=IL&startrow=N   (country facet)
            GET /search/?q=&locationsearch=Israel&startrow=N        (location text; unioned
            so one broken filter can't hide jobs). Server-rendered HTML: every job is a
            <tr class="data-row"> with a.jobTitle-link (href /job/<slug>/<numeric id>/) and
            span.jobLocation "Ra'anana, IL, 4366202". 25 rows/page, total in
            span.paginationLabel "Results <b>1 - 4</b> of <b>4</b>".
            PITFALL: ", IL" is also Illinois ("Chicago, IL, US, 60606"), so the country is the
            LAST two-letter token, and must be IL.
         2. GET /services/rss/job/?locale=en_US&keywords=(israel) - RSS with the full JD HTML
            in <description>; capped at 20 items, so it only supplies descriptions (plus any
            Israel job the search missed), never the authoritative list.
         3. GET /job/<slug>/<id>/ for any job the RSS didn't describe -> span.jobdescription.
      B. jobs.sap.com - the new Next.js site. Today it lists 0 jobs for every filter
         (totalJobs 0; sitemap only has "do-not-apply" test postings). It is probed on every
         run (1 request) and its RSC payload ("jobs":[...], "totalJobs":N) is parsed
         generically, so real Israeli jobs are picked up once SAP finishes moving over.
         Titles already seen on careers.sap.com are skipped (no cross-site duplicates).

    Never raises; on any failure returns whatever was collected so far.
    """
    import re, time, html, json
    try:
        import requests
    except Exception:
        return []
    try:
        from bs4 import BeautifulSoup
    except Exception:
        BeautifulSoup = None

    # brand -> the two SAP careers hosts (CSB legacy, Next.js new). One brand today; the CSB
    # half of this code works for any SuccessFactors Career Site Builder tenant.
    REGISTRY = {
        "SAP": {"csb": "careers.sap.com", "next": "jobs.sap.com", "slug": "sap"},
    }
    PACE = 0.3
    MAX_PAGES = 40              # 40 x 25 = 1000 listings per query, hard stop
    MAX_DETAIL = 80             # JD fetches per brand
    NEXT_MAX_PAGES = 10
    DESC_MAX = 2500
    BUDGET_S = 85.0

    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
    t0 = time.time()
    rows_out = []

    def time_left():
        return BUDGET_S - (time.time() - t0)

    try:
        sess = requests.Session()
        sess.headers.update({"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9",
                             "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"})
    except Exception:
        return []

    last = [0.0]

    dead = set()    # hosts that failed to connect on every retry: don't keep waiting on them

    def get_text(url, params=None, tries=3):
        """Paced GET with 429/5xx/connection backoff. Returns response text or None."""
        host = (re.match(r"https?://([^/]+)", url or "") or [None, ""])[1]
        if host in dead:
            return None
        conn_fail = 0
        for attempt in range(tries):
            if time_left() < 3:
                return None
            gap = PACE - (time.time() - last[0])
            if gap > 0:
                time.sleep(gap)
            try:
                r = sess.get(url, params=params, timeout=25)
            except Exception:
                last[0] = time.time()
                conn_fail += 1
                if attempt < tries - 1:
                    time.sleep(min(1.5 * (attempt + 1), max(0.0, time_left() - 3)))
                continue
            last[0] = time.time()
            if r.status_code == 429 or r.status_code >= 500:
                if attempt < tries - 1:
                    time.sleep(min(2.0 * (attempt + 1), max(0.0, time_left() - 3)))
                continue
            if r.status_code != 200:
                return None
            try:
                return r.text
            except Exception:
                return None
        if conn_fail == tries and host:
            dead.add(host)
        return None

    # ---------------- location helpers ----------------
    IL_CITIES = ("tel aviv", "tel-aviv", "herzliya", "herzeliya", "ra'anana", "raanana", "haifa",
                 "jerusalem", "petah tikva", "petach tikva", "petah-tikva", "netanya", "yokneam",
                 "yoqneam", "ramat gan", "hod hasharon", "kfar saba", "rehovot", "beer sheva",
                 "be'er sheva", "caesarea", "airport city", "rosh haayin", "rosh ha'ayin",
                 "modiin", "modi'in", "or yehuda", "bnei brak", "holon", "rishon lezion", "lod")
    CITY_FIX = {
        "raanana": "Ra'anana", "ra'anana": "Ra'anana", "ra`anana": "Ra'anana",
        "tel aviv-yafo": "Tel Aviv", "tel aviv": "Tel Aviv", "tel-aviv": "Tel Aviv",
        "herzeliya": "Herzliya", "herzliya": "Herzliya", "petah-tikva": "Petah Tikva",
        "petach tikva": "Petah Tikva", "hod hasharon": "Hod HaSharon", "beer-sheva": "Beer Sheva",
        "be'er sheva": "Beer Sheva", "yoqneam": "Yokneam", "yokneam illit": "Yokneam",
    }

    def is_israel_loc(loc):
        """'Ra'anana, IL, 4366202' -> True; 'Chicago, IL, US, 60606' -> False."""
        s = html.unescape(str(loc or "")).strip()
        if not s:
            return False
        parts = [p.strip() for p in s.split(",") if p.strip()]
        low = [p.lower() for p in parts]
        if "israel" in low or re.search(r"\bisrael\b", s.lower()):
            return True
        codes = [p for p in parts if re.fullmatch(r"[A-Z]{2}", p)]
        if codes:
            return codes[-1] == "IL"
        sl = s.lower()
        return any(re.search(r"(?<![a-z])" + re.escape(c) + r"(?![a-z])", sl) for c in IL_CITIES)

    def city_of_loc(loc):
        s = html.unescape(str(loc or "")).strip()
        parts = [p.strip() for p in s.split(",") if p.strip()]
        cand = parts[0] if parts else ""
        cl = cand.lower()
        if not cand or cl in ("israel", "il") or re.fullmatch(r"[\d\-\s]+", cand):
            return "Israel"
        return CITY_FIX.get(cl, cand)

    # ---------------- text helpers ----------------
    CUT_MARKERS = [
        "bring out your best\n", "bring out your best sap innovations",
        "we win with inclusion", "sap is committed to the values of equal",
        "for sap employees: only permanent roles", "qualified applicants will receive consideration",
        "successful candidates might be required", "ai usage in the recruitment process",
    ]

    def html_to_text(raw):
        if not raw:
            return ""
        try:
            if BeautifulSoup is not None:
                txt = BeautifulSoup(raw, "html.parser").get_text("\n")
            else:
                txt = re.sub(r"<[^>]+>", "\n", raw)
        except Exception:
            txt = re.sub(r"<[^>]+>", "\n", raw)
        return html.unescape(txt).replace("\xa0", " ").replace("​", "")

    def clean_desc(raw):
        """-> (plain JD without SAP boilerplate, 'Work Area | Career Status | Employment Type')."""
        txt = html_to_text(raw)
        if not txt.strip():
            return "", ""
        meta = []
        for k in ("Work Area", "Career Status", "Employment Type"):
            m = re.search(k + r":\s*([^|\n]+)", txt)
            if m and m.group(1).strip():
                meta.append("%s: %s" % (k, m.group(1).strip()))
        txt = re.sub(r"[ \t]+", " ", txt)
        txt = re.sub(r"\s*\n\s*", "\n", txt).strip()
        low = txt.lower()
        cut = len(txt)
        for mk in CUT_MARKERS:
            i = low.find(mk)
            if 200 < i < cut:
                cut = i
        i = low.find("requisition id:")
        if 200 < i < cut:
            cut = i
        txt = txt[:cut]
        # SAP's fixed opening blurb
        for end in (r"grow and succeed\.", r"truly belong\.", r"best in you\."):
            txt2 = re.sub(r"^\s*We help the world run better.{0,1200}?" + end + r"\s*",
                          "", txt, count=1, flags=re.S | re.I)
            if txt2 != txt:
                txt = txt2
                break
        return txt.strip(), " | ".join(meta)

    def flat(txt):
        return re.sub(r"\s+", " ", txt or "").strip()

    def cap(txt, n=DESC_MAX):
        if len(txt) <= n:
            return txt
        cut = txt[:n]
        sp = cut.rfind(" ")
        return (cut[:sp] if sp > n - 200 else cut).rstrip()

    def years_of(text):
        """Years of experience, looked for only in lines that talk about experience.
        Decimals ('1.5 year left before graduation') and study-time phrases are ignored."""
        for line in re.split(r"[\n\r]+|(?<=[.;])\s+", (text or "").lower()):
            if "experien" not in line and "background in" not in line:
                continue
            m = re.search(r"(?<![\d.])(\d{1,2})\s*(?:-|–|—|to)\s*(\d{1,2})\s*\+?\s*(?:years?|yrs?)\b", line)
            if m:
                a, b = int(m.group(1)), int(m.group(2))
                if 0 <= a <= 30 and a <= b <= 30:
                    return (a, b)
            for pat in (r"(?<![\d.])(\d{1,2})\s*\+\s*(?:years?|yrs?)\b",
                        r"(?:at least|minimum(?: of)?|min\.?|over|more than)\s*(\d{1,2})(?![\d.])\s*(?:years?|yrs?)\b",
                        r"(?<![\d.])(\d{1,2})(?![\d.])\s*(?:years?|yrs?)\b"):
                m = re.search(pat, line)
                if m:
                    tail = line[m.end():m.end() + 30]
                    if re.search(r"\b(left|remaining|before graduat|of stud|of your degree)", tail):
                        continue
                    a = int(m.group(1))
                    if 0 <= a <= 30:
                        return (a, None)
        return (None, None)

    def level_of(title):
        tl = (title or "").lower()
        if re.search(r"\b(intern|interns|internship|student|working student|co-?op|apprentice|"
                     r"trainee|vocational)\b", tl):
            return "student"
        if re.search(r"\b(senior|sr\.?|staff|principal|lead|architect|chief|director|head of|"
                     r"vp|vice president|distinguished|fellow|expert)\b", tl):
            return "senior"
        if re.search(r"\b(junior|jr\.?|entry[- ]level|new grad|graduate|early[- ]career)\b", tl):
            return "junior"
        return ""

    TECH = [
        (r"\bpython\b", "Python"), (r"\bjava\b(?!\s*script)", "Java"), (r"\bjavascript\b", "JavaScript"),
        (r"\btypescript\b", "TypeScript"), (r"c\+\+", "C++"), (r"\bc#|\.net\b", "C#/.NET"),
        (r"\bgolang\b|\b(?:java|python|c\+\+|rust|kotlin|scala),?\s*(?:,|/|or|and)\s*go\b|\bgo\s*(?:,|/|or|and)\s*(?:java|python|c#|c\+\+|rust|kotlin)\b", "Go"),
        (r"\brust\b", "Rust"), (r"\bkotlin\b", "Kotlin"), (r"\bscala\b", "Scala"),
        (r"\bsql\b", "SQL"), (r"\babap\b", "ABAP"), (r"\bsap\s?ui5\b|\bui5\b", "SAPUI5"),
        (r"(?:\b|4)hana\b", "HANA"), (r"\bbtp\b", "SAP BTP"),
        (r"\breact(?:\.js|js)?\b(?!\s+to\b)", "React"), (r"\bangular\b", "Angular"),
        (r"\bnode\.?js\b", "Node.js"), (r"\bspring(?: boot)?\b", "Spring"),
        (r"\brest(?:ful)?\s+apis?\b", "REST"), (r"\bhtml5?\b", "HTML"),
        (r"\bkubernetes\b|\bk8s\b", "Kubernetes"), (r"\bdocker\b", "Docker"),
        (r"\bterraform\b", "Terraform"), (r"\baws\b", "AWS"), (r"\bgcp\b|google cloud", "GCP"),
        (r"\bazure\b", "Azure"), (r"\blinux\b", "Linux"),
        (r"\bspark\b", "Spark"), (r"\bkafka\b", "Kafka"),
        (r"\bmicroservices?\b", "Microservices"), (r"ci/cd|ci-cd", "CI/CD"), (r"\bdevops\b", "DevOps"),
        (r"\bgit\b", "Git"), (r"machine learning|\bml\b", "Machine Learning"),
        (r"deep learning", "Deep Learning"),
        (r"\bllms?\b|large language model", "LLM"), (r"gen ?ai\b|generative ai", "GenAI"),
        (r"\bai agents?\b|agentic", "AI Agents"),
    ]

    def tech_of(text):
        t = (text or "").lower()
        out = []
        for pat, label in TECH:
            try:
                if label not in out and re.search(pat, t):
                    out.append(label)
            except re.error:
                pass
        return out

    def norm_title(t):
        return re.sub(r"[^a-z0-9]+", "", (t or "").lower())

    def csb_url(host, href):
        # hrefs arrive double-escaped ("Ra&amp;apos;anana"); make them clean + clickable
        h = html.unescape(html.unescape(href or "")).strip()
        h = h.split("?")[0].split("#")[0]
        if not h.startswith("http"):
            h = "https://%s%s" % (host, h if h.startswith("/") else "/" + h)
        return h.replace("'", "%27").replace(" ", "%20")

    def id_of(href):
        m = re.search(r"/(\d{5,})/?(?:[?#]|$)", html.unescape(href or ""))
        return m.group(1) if m else ""

    ROW_RE = re.compile(r'<tr class="data-row[^"]*"[^>]*>(.*?)</tr>', re.S)
    LINK_RE = re.compile(r'<a[^>]+href="([^"]+)"[^>]*class="jobTitle-link[^"]*"[^>]*>(.*?)</a>', re.S)
    LINK_RE2 = re.compile(r'<a[^>]+class="jobTitle-link[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.S)
    LOC_RE = re.compile(r'<span class="jobLocation[^"]*">\s*(.*?)\s*</span>', re.S)
    TOTAL_RE = re.compile(r'paginationLabel[^>]*>.*?of\s*<b>\s*([\d,]+)\s*</b>', re.S)

    def parse_search(t):
        out = []
        for row in ROW_RE.findall(t or ""):
            m = LINK_RE.search(row) or LINK_RE2.search(row)
            if not m:
                continue
            l = LOC_RE.search(row)
            title = flat(html.unescape(re.sub(r"<[^>]+>", " ", m.group(2))))
            loc = flat(html.unescape(re.sub(r"<[^>]+>", " ", l.group(1)))) if l else ""
            out.append((title, loc, m.group(1)))
        tm = TOTAL_RE.search(t or "")
        total = int(tm.group(1).replace(",", "")) if tm else None
        return out, total

    for brand, cfg in REGISTRY.items():
        try:
            host, nhost, slug = cfg["csb"], cfg.get("next"), cfg.get("slug") or brand.lower()
            listings = {}       # id -> dict(title, loc, url)
            descs = {}          # id -> raw JD html

            # ---------- A1: CSB search (authoritative list) ----------
            for q in ({"q": "", "optionsFacetsDD_country": "IL"},
                      {"q": "", "locationsearch": "Israel"}):
                try:
                    startrow, total, seen_page = 0, None, set()
                    for _ in range(MAX_PAGES):
                        if time_left() < 20:
                            break
                        params = dict(q)
                        if startrow:
                            params["startrow"] = startrow
                        t = get_text("https://%s/search/" % host, params)
                        if not t:
                            break
                        rows, tot = parse_search(t)
                        if total is None:
                            total = tot
                        new = 0
                        for title, loc, href in rows:
                            jid = id_of(href)
                            if not jid or jid in seen_page:
                                continue
                            seen_page.add(jid)
                            new += 1
                            if title and is_israel_loc(loc) and jid not in listings:
                                listings[jid] = {"title": title, "loc": loc, "url": csb_url(host, href)}
                        if not rows or not new:
                            break
                        startrow += len(rows)
                        if total is not None and startrow >= total:
                            break
                except Exception:
                    continue

            # ---------- A2: RSS (descriptions + safety net) ----------
            try:
                if time_left() > 15:
                    t = get_text("https://%s/services/rss/job/" % host,
                                 {"locale": "en_US", "keywords": "(israel)"})
                    for it in re.findall(r"<item>(.*?)</item>", t or "", re.S):
                        try:
                            tm = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", it, re.S)
                            lm = re.search(r"<link>(.*?)</link>", it, re.S)
                            dm = re.search(r"<description>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</description>", it, re.S)
                            if not tm or not lm:
                                continue
                            full = flat(html.unescape(tm.group(1)))
                            pm = re.match(r"^(.*)\(([^()]*)\)\s*$", full)
                            title, loc = (flat(pm.group(1)), pm.group(2).strip()) if pm else (full, "")
                            href = html.unescape(lm.group(1).strip())
                            jid = id_of(href.split("?")[0])
                            if not jid:
                                continue
                            if jid in listings:
                                if dm:
                                    descs[jid] = dm.group(1)
                            elif title and is_israel_loc(loc):
                                listings[jid] = {"title": title, "loc": loc, "url": csb_url(host, href)}
                                if dm:
                                    descs[jid] = dm.group(1)
                        except Exception:
                            continue
            except Exception:
                pass

            # ---------- A3: JD pages for anything the RSS didn't cover ----------
            try:
                fetched = 0
                for jid, L in listings.items():
                    if jid in descs:
                        continue
                    if fetched >= MAX_DETAIL or time_left() < 12:
                        break
                    fetched += 1
                    t = get_text(L["url"])
                    if not t:
                        continue
                    raw = ""
                    if BeautifulSoup is not None:
                        try:
                            sp = BeautifulSoup(t, "html.parser").find("span", class_="jobdescription")
                            raw = str(sp) if sp else ""
                        except Exception:
                            raw = ""
                    if not raw:
                        m = re.search(r'class="jobdescription">(.*?)</span>\s*</span>\s*</div>', t, re.S)
                        raw = m.group(1) if m else ""
                    if raw:
                        descs[jid] = raw
            except Exception:
                pass

            seen_titles = set()
            for jid, L in listings.items():
                try:
                    body, meta = clean_desc(descs.get(jid, ""))
                    ymin, ymax = years_of(body)
                    desc = flat(body)
                    if meta:
                        desc = (meta + ". " + desc).strip() if desc else meta
                    seen_titles.add(norm_title(L["title"]))
                    rows_out.append({
                        "source": "successfactors:%s" % slug,
                        "sid": str(jid),
                        "title": L["title"],
                        "company": brand,
                        "city": city_of_loc(L["loc"]),
                        "url": L["url"],
                        "level": level_of(L["title"]),
                        "years_min": ymin,
                        "years_max": ymax,
                        "tech": tech_of(L["title"] + " " + body),
                        "desc": cap(desc),
                        "active": True,
                    })
                except Exception:
                    continue

            # ---------- B: new Next.js site (0 jobs today; auto-activates later) ----------
            if not nhost or time_left() < 10:
                continue
            try:
                dec = json.JSONDecoder()

                def rsc_payload(t):
                    out = []
                    for c in re.findall(r'self\.__next_f\.push\(\[1,\s*"((?:[^"\\]|\\.)*)"\]\)', t or "", re.S):
                        try:
                            out.append(json.loads('"' + c + '"'))
                        except Exception:
                            continue
                    return "\n".join(out)

                def pick(d, keys):
                    for k in keys:
                        v = d.get(k)
                        if isinstance(v, (str, int)) and str(v).strip() and not str(v).startswith("$"):
                            return str(v).strip()
                    return ""

                def loc_strings(o, depth=0, under=False):
                    acc = []
                    if depth > 4:
                        return acc
                    if isinstance(o, dict):
                        for k, v in o.items():
                            kl = str(k).lower()
                            hit = under or any(w in kl for w in ("loc", "city", "country", "address", "region", "place"))
                            acc += loc_strings(v, depth + 1, hit)
                    elif isinstance(o, list):
                        for v in o:
                            acc += loc_strings(v, depth + 1, under)
                    elif isinstance(o, str) and under:
                        acc.append(o)
                    return acc

                njobs, total_pages = [], 1
                for page in range(1, NEXT_MAX_PAGES + 1):
                    if page > total_pages or time_left() < 10:
                        break
                    params = {"country": "Israel"}
                    if page > 1:
                        params["page"] = page
                    t = get_text("https://%s/en/jobs/" % nhost, params)
                    pl = rsc_payload(t)
                    if not pl:
                        break
                    tj = [int(x) for x in re.findall(r'"totalJobs":(\d+)', pl)]
                    tp = [int(x) for x in re.findall(r'"totalPages":(\d+)', pl)]
                    if not tj or max(tj) == 0:
                        break
                    total_pages = max(tp) if tp else 1
                    got = 0
                    for m in re.finditer(r'"jobs":\[', pl):
                        try:
                            arr, _ = dec.raw_decode(pl, m.end() - 1)
                        except Exception:
                            continue
                        for j in arr:
                            if isinstance(j, dict):
                                njobs.append(j)
                                got += 1
                    if not got:
                        break

                ndone, nseen = 0, set()
                for j in njobs:
                    try:
                        jid = pick(j, ("id", "jobId", "jobID", "requisitionId", "jobReqId", "reference", "ref"))
                        title = flat(html.unescape(pick(j, ("title", "jobTitle", "name", "displayTitle"))))
                        if not jid or not title or jid in nseen:
                            continue
                        nseen.add(jid)
                        if re.search(r"do[\s\-]*not[\s\-]*apply|\btest[\s\-]*job\b|^test\b", title, re.I):
                            continue
                        if norm_title(title) in seen_titles:
                            continue            # already have it from careers.sap.com
                        locs = [flat(html.unescape(s)) for s in loc_strings(j)]
                        il_locs = [s for s in locs if is_israel_loc(s) or s.strip().lower() == "israel"]
                        if not il_locs:
                            continue
                        city = "Israel"
                        for s in il_locs:
                            c = city_of_loc(s)
                            if c != "Israel" and not re.fullmatch(r"[A-Z]{2}", c):
                                city = c
                                break
                        u = pick(j, ("url", "jobUrl", "href", "path", "link", "canonicalUrl"))
                        if u and not u.startswith("http"):
                            u = "https://%s%s" % (nhost, u if u.startswith("/") else "/" + u)
                        if not u:
                            sl = pick(j, ("slug", "urlSlug", "seoSlug")) or \
                                re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
                            u = "https://%s/en/jobs/%s/%s/" % (nhost, jid, sl)
                        raw = pick(j, ("description", "jobDescription", "summary", "teaser", "shortDescription"))
                        if not raw and ndone < MAX_DETAIL and time_left() > 8:
                            ndone += 1
                            t = get_text(u)
                            for ld in re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', t or "", re.S):
                                try:
                                    o = json.loads(ld)
                                except Exception:
                                    continue
                                for x in (o if isinstance(o, list) else [o]):
                                    if isinstance(x, dict) and x.get("description"):
                                        raw = str(x.get("description"))
                                        break
                                if raw:
                                    break
                        body, meta = clean_desc(raw)
                        ymin, ymax = years_of(body)
                        desc = flat(body)
                        if meta:
                            desc = (meta + ". " + desc).strip() if desc else meta
                        seen_titles.add(norm_title(title))
                        rows_out.append({
                            "source": "successfactors:%s" % slug,
                            "sid": str(jid),
                            "title": title,
                            "company": brand,
                            "city": city,
                            "url": u,
                            "level": level_of(title),
                            "years_min": ymin,
                            "years_max": ymax,
                            "tech": tech_of(title + " " + body),
                            "desc": cap(desc),
                            "active": True,
                        })
                    except Exception:
                        continue
            except Exception:
                pass
        except Exception:
            continue
    return rows_out
