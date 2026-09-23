# -*- coding: utf-8 -*-
# Auto-generated adapters (v2 scrapers + v3 + giants). Built by workflow 2026-09-17.

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
    Scrapes the newest ~2 listing pages of the software/data/qa/system categories.
    sid = positionId. company is not published on the board, so it is returned "".
    Never raises; returns whatever it managed to collect (cap ~120)."""
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
    PAGES = (1, 2)
    CAP = 120

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
        t = (title + " " + blob).lower()
        if any(w in t for w in ("student", "סטודנט",
                                "intern", "מתמחה")):
            return "student"
        if any(w in t for w in ("senior", "sr.", "lead", "principal", "staff",
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

    for cat in CATS:
        for page in PAGES:
            if len(out) >= CAP:
                break
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
                continue
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
                    if len(out) >= CAP:
                        break
                except Exception:
                    continue
            time.sleep(0.3)
        if len(out) >= CAP:
            break
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
    # (category, subcat) boards, newest-first: software core + devops/sre + qa automation.
    BOARDS = [
        ("software", "java-developer"), ("software", "python-developer"),
        ("software", "frontend-developer"), ("software", "backend-developer"),
        ("software", "full-stack-developer"), ("software", "net-developer"),
        ("software", "nodejs-developer"), ("software", "react-developer"),
        ("software", "go-developer"), ("software", "data-engineer"),
        ("software", "ai-engineer"),
        ("system", "devops-positions"), ("system", "sre"),
        ("qa", "automation-developer"),
    ]
    PAGES = 3          # newest N listing pages per board (page 1 = newest)
    CAP = 120          # global cap on returned jobs

    SR = ["senior", "sr.", "sr ", " lead", "lead ", "principal", "staff", "architect",
          "team lead", "teamlead", "team leader", "head of", "manager", "expert", "vp ",
          "director", "בכיר", "ראש צוות",
          "מנהל", "מוביל", "ארכיטקט"]
    JR = ["junior", "jr.", "jr ", "entry level", "entry-level",
          "ג'וניור", "זוטר", "מתחיל"]
    ST = ["student", "intern", "internship", "graduate",
          "סטודנט", "מתמח", "התמחות", "בוגר"]

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
        if any(m in t for m in ST): return "student"
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

    def parse_page(content, cat, subcat, seen, out):
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
    try:
        sess = requests.Session()
        sess.headers.update(HDRS)
    except Exception:
        sess = requests
    for cat, subcat in BOARDS:
        if len(out) >= CAP:
            break
        for page in range(1, PAGES + 1):
            if len(out) >= CAP:
                break
            url = "%s/jobslobby/%s/%s/" % (BASE, cat, subcat)
            if page > 1:
                url += "?page=%d" % page
            try:
                r = sess.get(url, timeout=30)
                if r.status_code != 200:
                    break
                added = parse_page(r.content, cat, subcat, seen, out)
            except Exception:
                break
            if added == 0:      # empty/last page for this board -> stop paging it
                break
            time.sleep(0.35)
    return out[:CAP]


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
    Pulls only start=0 (newest ~10 cards) per keyword to stay light and avoid blocks.
    Returns list[dict] with the scanner's normalized schema. Never raises."""
    import re, time, requests, urllib.parse
    from bs4 import BeautifulSoup

    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
    HEADERS = {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://www.linkedin.com/jobs/search",
    }
    BASE = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    KEYWORDS = ["software engineer", "backend", "full stack", ".net", "python"]
    SENIOR = ("senior", "sr.", "sr ", "lead", "principal", "staff", "architect",
              "team lead", "manager", "head of", "vp ", "director", "chief", "expert")
    STUDENT = ("student", "intern", "internship", "graduate", "trainee")
    TECHS = [".net", "c#", "c++", "python", "java", "javascript", "typescript",
             "node", "react", "angular", "vue", "go", "golang", "rust", "ruby",
             "php", "kotlin", "swift", "scala", "django", "flask", "fastapi",
             "spring", "aws", "azure", "gcp", "kubernetes", "docker", "sql",
             "postgres", "mongodb", "graphql", "devops", "backend", "frontend",
             "full stack", "fullstack"]

    def level_of(title):
        t = (title or "").lower()
        if any(w in t for w in STUDENT):
            return "student"
        if any(w in t for w in SENIOR):
            return "senior"
        return "junior"   # f_E=2 = entry-level filter; sane default hint

    def tech_of(title):
        t = (title or "").lower()
        return [k for k in TECHS if k in t]

    out, seen_sid = [], set()
    try:
        sess = requests.Session()
    except Exception:
        return out
    for kw in KEYWORDS:
        if len(out) >= 120:
            break
        url = BASE + "?" + urllib.parse.urlencode(
            {"location": "Israel", "keywords": kw, "f_E": "2", "start": "0"})
        html = ""
        for attempt in range(3):
            try:
                r = sess.get(url, headers=HEADERS, timeout=30)
                if r.status_code == 429:            # rate-limited -> back off
                    time.sleep(4 + 4 * attempt)
                    continue
                if r.status_code == 200:
                    html = r.text
                break
            except Exception:
                time.sleep(1.5 + attempt)
        if not html:
            time.sleep(1.5)
            continue
        try:
            soup = BeautifulSoup(html, "lxml")
            cards = soup.select("div.base-card") or soup.select("li")
            for d in cards:
                if len(out) >= 120:
                    break
                urn = d.get("data-entity-urn", "") or ""
                sid = ""
                m = re.search(r"jobPosting:(\d+)", urn) or re.search(r"(\d{6,})", urn)
                if m:
                    sid = m.group(1)
                a = (d.select_one("a.base-card__full-link")
                     or d.select_one("a[href*='/jobs/view/']"))
                href = (a.get("href", "") if a else "").split("?")[0]
                if not sid:                          # fall back to id inside the URL
                    m2 = re.search(r"/jobs/view/(?:[^/]*?-)?(\d{6,})", href)
                    if m2:
                        sid = m2.group(1)
                if not sid or sid in seen_sid:
                    continue
                seen_sid.add(sid)
                te = d.select_one("h3.base-search-card__title")
                title = te.get_text(strip=True) if te else ""
                ce = d.select_one("h4.base-search-card__subtitle")
                company = ce.get_text(strip=True) if ce else ""
                le = d.select_one(".job-search-card__location")
                city = le.get_text(strip=True) if le else ""
                out.append({
                    "source": "linkedin",
                    "sid": sid,
                    "title": title,
                    "company": company,
                    "city": city,
                    "url": href or ("https://www.linkedin.com/jobs/view/" + sid),
                    "level": level_of(title),
                    "years_min": None,
                    "years_max": None,
                    "tech": tech_of(title),
                    "desc": "",
                    "active": True,
                })
        except Exception:
            pass
        time.sleep(1.5)      # polite: 1-2s between guest-API calls
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
    # a few confirmed tech profession IDs + broad software freetext queries
    SEARCHES = [
        "position=2006",                 # AI Engineer
        "position=2004",                 # AI Developer
        "position=2011",                 # QA Automation
        "freetext=" + quote(u"מפתח"),  # "developer" (Hebrew)
        "freetext=Python",
        "freetext=DevOps",
        "freetext=" + quote("Full Stack"),
        "freetext=Embedded",
    ]
    MAX_PAGES = 4          # newest pages only -> keeps the daily run fast
    CAP = 120
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
    STUDENT = ["student", "intern", "internship", u"סטודנט",
               u"מתמח", u"הכשרה"]
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
        if any(w in blob for w in STUDENT):
            return "student"
        if any(w in blob for w in SENIOR):
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

    out, seen_sids = [], set()
    sess = requests.Session()
    sess.headers.update(HEADERS)
    try:
        for q in SEARCHES:
            if len(out) >= CAP:
                break
            prev_page_sids = None
            for page in range(1, MAX_PAGES + 1):
                if len(out) >= CAP:
                    break
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
                    break
                try:
                    soup = BeautifulSoup(body, "lxml")
                except Exception:
                    break
                cards = soup.select("div.job-content-top")
                if not cards:
                    break
                page_sids, new_here = [], 0
                for c in cards:
                    j = parse_card(c)
                    if not j:
                        continue
                    page_sids.append(j["sid"])
                    if j["sid"] in seen_sids:
                        continue
                    seen_sids.add(j["sid"])
                    out.append(j)
                    new_here += 1
                    if len(out) >= CAP:
                        break
                # AllJobs clamps an out-of-range page to the last page: if this page
                # repeats the previous page's ids we've reached the end -> stop.
                if prev_page_sids is not None and page_sids == prev_page_sids:
                    break
                if new_here == 0:
                    break
                prev_page_sids = page_sids
                time.sleep(0.4)   # polite pacing between pages
            time.sleep(0.5)       # polite pacing between searches
    except Exception:
        pass
    return out[:CAP]


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
    # These are public board tokens (not secrets); if one rotates that board is
    # skipped silently. Kept broad across sectors for resilience.
    REGISTRY = [
        ("Guideline",          "89.009", "98942BF98998939361C9B39361C9B2FAD989"),
        ("Samsung R&D Israel", "D4.005", "4D518291CFE13540135413544D518291CFE"),
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
        ("Fiverr",             "60.002", "62188018812631018862C4188"),
        ("Gett",               "A0.002", "A2288A232A014432A28814432A"),
        ("Allot",              "C4.009", "4C917ED1CB699217ED04C92B11217F2B11"),
        ("Moovit",             "63.007", "36711036CE11031E9F146A1B38367A356CE"),
    ]

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

    CAP = 120
    PER_COMPANY = 12
    jobs = []
    seen = set()

    for name, uid, token in REGISTRY:
        if len(jobs) >= CAP:
            break
        url = API.format(uid=uid, token=token)
        try:
            r = requests.get(url, headers=HEADERS, timeout=25)
            data = r.json()
        except Exception:
            continue
        if not isinstance(data, list):
            continue
        # Comeet returns the whole board in one call; emulate "newest few pages"
        # by sorting on time_updated (newest first) and capping per company.
        try:
            data.sort(key=lambda p: (p.get("time_updated") or ""), reverse=True)
        except Exception:
            pass

        kept = 0
        for p in data:
            if len(jobs) >= CAP or kept >= PER_COMPANY:
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

        time.sleep(0.3)

    return jobs


# ===== workday (works=yes) =====
import re, time, json, html
import requests
from bs4 import BeautifulSoup


def src_workday():
    """Generic Workday CXS adapter for Ron's referral/giant companies.

    Hits the Workday CXS jobs API for a hardcoded registry of brands, pulls the
    newest few listing pages, and returns every tech/software role located in
    Israel (confirmed via the job-detail country field). Never raises.
    """
    SOURCE = "workday"
    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

    # Confirmed live 2026-09-17: brand -> (tenant, wd-host, site)
    REGISTRY = {
        "NVIDIA":  ("nvidia",  "wd5", "NVIDIAExternalCareerSite"),
        "Intel":   ("intel",   "wd1", "External"),
        "Philips": ("philips", "wd3", "jobs-and-careers"),
        "Unity":   ("unitytech", "wd1", "Unity"),      # added 2026-09-23
        "Snyk":    ("snyk", "wd103", "External"),       # added 2026-09-23
        # Palo Alto Networks is NOT on Workday (uses SmartRecruiters) -> omitted.
    }

    SEARCH_TERMS = ["software"]   # contract default; add "engineer" etc. to broaden
    PAGES = 4                     # newest/top pages only (offset 0,20,40,60)
    LIMIT = 20
    MAX_MULTI_PROBE = 12          # per-brand cap on detail probes of multi-location posts
    MAX_DETAIL = 90               # global cap on detail fetches (runtime guard)
    MAX_TOTAL = 120

    # Distinctive Israeli location tokens (for list-level locationsText matching;
    # authoritative confirmation is the detail country field).
    IL_TOKENS = [
        "israel", "tel aviv", "tel-aviv", "telaviv", "haifa", "yokneam", "yoqneam",
        "jerusalem", "herzliya", "herzeliya", "hertzeliya", "raanana", "ra'anana",
        "raananna", "ra'ananna", "petah tikva", "petach tikva", "petah-tikva",
        "petah tiqwa", "rehovot", "rechovot", "netanya", "nethanya", "beer sheva",
        "be'er sheva", "beersheba", "kfar saba", "kefar sava", "hod hasharon",
        "ramat gan", "caesarea", "qesarya", "karmiel", "carmiel", "migdal haemek",
        "or yehuda", "airport city", "modiin", "modi'in", "holon", "ashdod",
        "nazareth", "kiryat gat", "kiryat", "tefen", "misgav", "yavne", "lod",
        "rosh haayin", "rosh ha'ayin",
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

    sess = requests.Session()
    sess.headers.update({
        "User-Agent": UA,
        "Accept": "application/json",
        "Content-Type": "application/json",
    })

    state = {"detail_calls": 0}

    def _looks_israeli(text):
        t = (text or "").lower()
        return any(tok in t for tok in IL_TOKENS)

    def _is_multi(loc_text):
        return bool(re.search(r"\d+\s+location", (loc_text or "").lower()))

    def _city_from(loc):
        if not loc:
            return ""
        loc = re.sub(r"\s+", " ", str(loc)).strip()
        if re.search(r"\d+\s+location", loc.lower()):
            return ""
        parts = [p.strip() for p in loc.split(",") if p.strip()]
        if not parts:
            return ""
        cand = parts[-1]
        if cand.lower() in ("israel",) and len(parts) >= 2:
            cand = parts[-2]
        return cand

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

    def _fetch_detail(tenant, wd, site, ext):
        if state["detail_calls"] >= MAX_DETAIL:
            return None
        state["detail_calls"] += 1
        url = f"https://{tenant}.{wd}.myworkdayjobs.com/wday/cxs/{tenant}/{site}{ext}"
        try:
            r = sess.get(url, timeout=20)
            time.sleep(0.3)
            if r.status_code == 200 and "json" in r.headers.get("content-type", ""):
                return r.json().get("jobPostingInfo", {}) or {}
        except Exception:
            return None
        return None

    results = {}   # sid -> dict (dedupe)

    for brand, (tenant, wd, site) in REGISTRY.items():
        base = f"https://{tenant}.{wd}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"
        pub_base = f"https://{tenant}.{wd}.myworkdayjobs.com/en-US/{site}"
        seen_paths = set()
        multi_probes = 0
        try:
            for term in SEARCH_TERMS:
                for page in range(PAGES):
                    if len(results) >= MAX_TOTAL:
                        break
                    body = {"appliedFacets": {}, "limit": LIMIT,
                            "offset": page * LIMIT, "searchText": term}
                    try:
                        r = sess.post(base, data=json.dumps(body), timeout=20)
                        time.sleep(0.3)
                    except Exception:
                        break
                    if r.status_code != 200 or "json" not in r.headers.get("content-type", ""):
                        break
                    try:
                        postings = r.json().get("jobPostings", []) or []
                    except Exception:
                        break
                    if not postings:
                        break

                    for p in postings:
                        ext = p.get("externalPath") or ""
                        if not ext or ext in seen_paths:
                            continue
                        seen_paths.add(ext)
                        title = (p.get("title") or "").strip()
                        loc_text = (p.get("locationsText") or "").strip()

                        israeli = _looks_israeli(loc_text)
                        detail = None

                        if not israeli:
                            # multi-location postings can hide an Israel site
                            if _is_multi(loc_text) and multi_probes < MAX_MULTI_PROBE:
                                multi_probes += 1
                                detail = _fetch_detail(tenant, wd, site, ext)
                                if detail:
                                    c = (detail.get("country") or {})
                                    cdesc = c.get("descriptor", "") if isinstance(c, dict) else str(c)
                                    if cdesc.lower() == "israel" or _looks_israeli(
                                        (detail.get("location") or "") + " " +
                                        " ".join(detail.get("additionalLocations") or [])
                                    ):
                                        israeli = True
                            if not israeli:
                                continue

                        # Enrich + authoritatively confirm via detail
                        if detail is None:
                            detail = _fetch_detail(tenant, wd, site, ext)

                        city = ""
                        desc = ""
                        url_final = f"{pub_base}{ext}"
                        if detail:
                            c = (detail.get("country") or {})
                            cdesc = c.get("descriptor", "") if isinstance(c, dict) else str(c)
                            det_loc = detail.get("location") or ""
                            det_add = " ".join(detail.get("additionalLocations") or [])
                            # authoritative filter: drop false positives
                            if cdesc:
                                if cdesc.lower() != "israel" and not _looks_israeli(det_loc + " " + det_add):
                                    continue
                            city = _city_from(det_loc) or _city_from(loc_text)
                            desc = _clean_text(detail.get("jobDescription"))
                            if detail.get("externalUrl"):
                                url_final = detail["externalUrl"]
                        else:
                            # no detail (cap/err): trust the list hint, best-effort
                            city = _city_from(loc_text)

                        years_min, years_max = _extract_years(desc) if desc else (None, None)
                        level = _extract_level(title, desc, years_min, years_max)
                        tech = _extract_tech((title + " " + desc) if desc else title)

                        results[ext] = {
                            "source": SOURCE,
                            "sid": ext,
                            "title": title,
                            "company": brand,
                            "city": city,
                            "url": url_final,
                            "level": level,
                            "years_min": years_min,
                            "years_max": years_max,
                            "tech": tech,
                            "desc": desc[:2500],
                            "active": True,
                        }
                        if len(results) >= MAX_TOTAL:
                            break
                    if len(results) >= MAX_TOTAL:
                        break
                if len(results) >= MAX_TOTAL:
                    break
        except Exception:
            # never raise: keep whatever we already collected
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
    MAX_PAGES = 5          # newest ~5 pages (20/page) -- caller dedups across days
    CAP = 120

    SENIOR = ("senior", "sr.", "sr ", " lead", "lead ", "principal", "staff",
              "architect", "manager", "head of", "director", "chief", " vp", "expert")
    JUNIOR = ("junior", "jr.", "jr ", "entry", "associate", "new grad",
              "new-grad", "graduate")
    STUDENT = ("intern", "internship", "student", "co-op", "co op", "working student")
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
        if any(w in t for w in STUDENT):
            return "student"
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
        m = re.search(r'window\.__staticRouterHydrationData\s*=\s*JSON\.parse\("(.*?)"\);',
                      page_html, re.S)
        if not m:
            return None
        try:
            data = json.loads(json.loads('"' + m.group(1) + '"'))
        except Exception:
            return None
        try:
            return data["loaderData"]["search"]["searchResults"]
        except Exception:
            return None

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

    jobs = []
    seen_ids = set()
    for pg in range(1, MAX_PAGES + 1):
        try:
            r = s.get(SEARCH % pg, timeout=30)
            r.encoding = "utf-8"
            page_html = r.text
        except Exception:
            break
        recs = parse_hydration(page_html)
        page_jobs = []
        if recs:
            for rec in recs:
                j = rec_to_job(rec)
                if j:
                    page_jobs.append(j)
        else:
            page_jobs = scrape_cards(page_html)
        new = 0
        for j in page_jobs:
            if j["sid"] in seen_ids:
                continue
            seen_ids.add(j["sid"])
            jobs.append(j)
            new += 1
        if new == 0:          # empty / repeated page -> stop early
            break
        if len(jobs) >= CAP:
            jobs = jobs[:CAP]
            break
        time.sleep(0.35)
    return jobs


# ===== Camtek careers adapter (+ Palo Alto Networks IL bonus) (works=yes) =====
# -*- coding: utf-8 -*-
import re, time, requests
from bs4 import BeautifulSoup

def src_camtek():
    """
    Camtek careers adapter (+ best-effort bonus: Palo Alto Networks IL, PwC Israel).
    Returns a list of normalized job dicts. Never raises.
    """
    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
    HDRS = {"User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9"}
    out = []
    CAP = 120

    def _get(url, timeout=25):
        return requests.get(url, headers=HDRS, timeout=timeout, allow_redirects=True)

    def _level(title, desc=""):
        # title-driven only: JD text ("we hire students", "3 years") gives false positives
        t = title.lower()
        if any(w in t for w in ("student", "intern", "internship", "סטודנט")):
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
                if len(out) >= CAP:
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

    # ---------------- 2) PALO ALTO NETWORKS IL (bonus) ----------------
    # Phenom site. /en/search-jobs/Israel is a KEYWORD search (returns global rows that
    # merely mention "Israel"), paginated with ?p=N. We take the newest ~5 pages and keep
    # only rows whose location span contains "Israel".
    try:
        for p in range(1, 6):
            if len(out) >= CAP:
                break
            try:
                r = _get("https://jobs.paloaltonetworks.com/en/search-jobs/Israel?p=%d" % p)
                if r.status_code != 200:
                    break
                soup = BeautifulSoup(r.text, "lxml")
                sec = soup.select_one("#search-results-list")
                lis = sec.select("li") if sec else []
                if not lis:
                    break
                for li in lis:
                    if len(out) >= CAP:
                        break
                    a = li.select_one("a.section29__search-results-link") or li.find("a", href=True)
                    if not a:
                        continue
                    loc_el = li.select_one(".section29__result-location") or li.select_one(".job-location")
                    city = loc_el.get_text(" ", strip=True) if loc_el else ""
                    if "israel" not in city.lower():
                        continue
                    ttl = li.select_one("h2") or a
                    title = ttl.get_text(" ", strip=True)
                    cat = li.select_one(".section29__result-category")
                    cat_txt = cat.get_text(" ", strip=True) if cat else ""
                    href = a["href"].strip()
                    if href.startswith("/"):
                        href = "https://jobs.paloaltonetworks.com" + href
                    sid = a.get("data-job-id") or href.rstrip("/").rsplit("/", 1)[-1]
                    city_clean = city.split(",")[0].strip()
                    out.append({
                        "source": "paloalto", "sid": str(sid), "title": title,
                        "company": "Palo Alto Networks", "city": city_clean, "url": href,
                        "level": _level(title), "years_min": None, "years_max": None,
                        "tech": _tech(title + " " + cat_txt),
                        "desc": cat_txt, "active": True,
                    })
                time.sleep(0.3)
            except Exception:
                break
    except Exception:
        pass

    # ---------------- 3) PwC ISRAEL (bonus, best-effort) ----------------
    # PwC Israel has no clean public JSON/HTML job board (postings live on LinkedIn / a
    # gated Hebrew ATS). We probe a couple of candidate pages; if none expose a parseable
    # list we simply return nothing for PwC. Never raises.
    try:
        pwc_urls = [
            "https://www.pwc.com/il/en/careers/open-positions.html",
            "https://www.pwc.com/il/en/careers/job-openings.html",
        ]
        for u in pwc_urls:
            if len(out) >= CAP:
                break
            try:
                r = _get(u, timeout=20)
                if r.status_code != 200:
                    continue
                soup = BeautifulSoup(r.text, "lxml")
                cards = soup.select("a[href*='job'], li.job, div.job-item, .position")
                for c in cards:
                    if len(out) >= CAP:
                        break
                    title = c.get_text(" ", strip=True)
                    href = c.get("href", "")
                    if not title or len(title) < 4 or not href:
                        continue
                    if href.startswith("/"):
                        href = "https://www.pwc.com" + href
                    sid = href.rstrip("/").rsplit("/", 1)[-1][:40]
                    out.append({
                        "source": "pwc", "sid": sid, "title": title, "company": "PwC Israel",
                        "city": "", "url": href, "level": _level(title),
                        "years_min": None, "years_max": None, "tech": _tech(title),
                        "desc": "", "active": True,
                    })
                if any(j["source"] == "pwc" for j in out):
                    break
            except Exception:
                continue
    except Exception:
        pass

    return out[:CAP]



# ===== Lever (open JSON API) — added 2026-09-23 =====
def src_lever():
    """Lever public postings API: GET api.lever.co/v0/postings/{slug}?mode=json -> JSON array.
    Registry of Israeli-employer Lever slugs; filter to Israel by categories.location."""
    import json, re, time, urllib.request
    UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    SLUGS = ["walkme"]   # grows as more Israeli Lever boards are confirmed
    ILC = ("israel", "tel aviv", "herzliya", "haifa", "yokneam", "ramat", "netanya",
           "petah", "raanana", "kfar", "jerusalem", "beer", "hod hasharon", "caesarea")
    out = []
    for slug in SLUGS:
        try:
            req = urllib.request.Request("https://api.lever.co/v0/postings/%s?mode=json" % slug,
                                         headers={"User-Agent": UA, "Accept": "application/json"})
            arr = json.loads(urllib.request.urlopen(req, timeout=20).read().decode("utf-8"))
        except Exception:
            continue
        for p in arr:
            cats = p.get("categories", {}) or {}
            loc = cats.get("location") or ""
            if not any(k in loc.lower() for k in ILC):
                continue
            desc = re.sub("<[^>]+>", " ", (p.get("descriptionPlain") or p.get("description") or ""))
            out.append({"source": "lever:" + slug, "sid": p.get("id", ""), "title": p.get("text", ""),
                        "company": slug, "city": loc, "url": p.get("hostedUrl", ""),
                        "level": "", "years_min": None, "years_max": None, "tech": [],
                        "desc": desc[:1500], "active": True})
        time.sleep(0.2)
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
        if any(k in t for k in ("intern", "internship", "student", "working student",
                                "graduate", "apprentice")):
            return "student"
        if any(k in t for k in ("senior", "sr.", "sr ", " staff", "staff ", "principal",
                                "lead", "director", "head of", "vp ", "chief", "manager",
                                "architect")):
            return "senior"
        if any(k in t for k in ("junior", "jr.", "jr ", "entry level", "entry-level")):
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

def src_moonactive():
    """Moon Active (Coin Master) careers via the Ashby public posting API.
    Returns newest Israel-based tech/software roles. Never raises."""
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

    # Ashby posting API serves the whole board in one JSON call (no real paging).
    slugs = ["moonactive", "moon-active", "moon_active"]
    data = None
    for slug in slugs:
        url = ("https://api.ashbyhq.com/posting-api/job-board/"
               + slug + "?includeCompensation=false")
        try:
            r = requests.get(url, headers=headers, timeout=30)
            if r.status_code == 200:
                j = r.json()
                if isinstance(j, dict) and j.get("jobs"):
                    data = j
                    break
        except Exception:
            pass
        time.sleep(1.0)  # polite between slug attempts
    if not data:
        return []

    jobs = data.get("jobs") or []

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
        t = " " + title.lower() + " "
        if any(w in t for w in (" intern ", " internship ", " student ",
                                " trainee ", " apprentice ")):
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

    # ---- sort newest first, then filter ----------------------------------
    def pub_key(job):
        return str(job.get("publishedAt") or "")
    try:
        jobs = sorted(jobs, key=pub_key, reverse=True)
    except Exception:
        pass

    for job in jobs[:400]:
        try:
            if not job.get("isListed", True):
                continue
            if not is_israel(job):
                continue
            if not is_tech(job):
                continue

            title = str(job.get("title") or "").strip()
            if not title:
                continue
            sid = str(job.get("id") or job.get("jobUrl") or title)
            url = (job.get("jobUrl") or job.get("applyUrl") or "")

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
                "source": "moonactive",
                "sid": sid,
                "title": title,
                "company": "Moon Active",
                "city": city,
                "url": url,
                "level": level,
                "years_min": ymin,
                "years_max": ymax,
                "tech": tech,
                "desc": desc,
                "active": True,
            })
            if len(out) >= 120:
                break
        except Exception:
            continue

    return out

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
    BASE = "https://corp.kaltura.com"
    LIST = BASE + "/company/careers/"
    CAP = 120
    out = []

    def _get(url, timeout=25):
        r = requests.get(url, headers=HDRS, timeout=timeout, allow_redirects=True)
        # page is UTF-8; guard against requests guessing latin-1 (would mojibake)
        if not r.encoding or r.encoding.lower() in ("iso-8859-1", "latin-1"):
            r.encoding = r.apparent_encoding or "utf-8"
        return r

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
        if any(w in t for w in ("student", "intern", "internship", "סטודנט")):
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

    try:
        r = _get(LIST)
        if r.status_code != 200:
            return out
        soup = BeautifulSoup(r.text, "lxml")
        anchors = soup.select("a.b-new-careers-lobby__job")
        if not anchors:
            # fallback: any anchor carrying the job data-attrs
            anchors = [a for a in soup.find_all("a", href=True) if a.get("data-title")]

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
                        d = _get(href, timeout=20)
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
    except Exception:
        pass

    return out

import re
import time
import requests
from bs4 import BeautifulSoup


def src_verbit():
    """Verbit (verbit.ai) careers -> WordPress REST 'job' post type.
    Returns Israel-based tech/software jobs as normalized dicts. Never raises."""
    out = []
    base = "https://verbit.ai/wp-json/wp/v2/job"
    headers = {
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/124.0.0.0 Safari/537.36"),
        "Accept": "application/json",
    }

    # --- Israel / tech detection helpers ---------------------------------
    il_cities = ("tel aviv", "tel-aviv", "telaviv", "jerusalem", "haifa",
                 "herzliya", "hertzliya", "ra'anana", "raanana", "netanya",
                 "petah tikva", "petach tikva", "beer sheva", "be'er sheva",
                 "rehovot", "ramat gan", "yokneam", "caesarea", "kfar saba",
                 "hod hasharon", "modiin", "ashdod", "israel")

    def is_israel(loc_name, loc_slug):
        n = (loc_name or "").lower()
        s = (loc_slug or "").lower()
        if n.endswith(", il") or n == "il" or " il" in (" " + n):
            if re.search(r"\bil\b", n):
                return True
        if s.endswith("-il") or s == "il":
            return True
        for c in il_cities:
            if c in n or c.replace(" ", "-") in s or c.replace(" ", "") in s.replace("-", ""):
                return True
        return False

    tech_kw = ("engineer", "developer", "devops", "software", "backend",
               "frontend", "front-end", "back-end", "full stack", "fullstack",
               "full-stack", "data", "machine learning", "ml", "ai ", "ai/",
               "/ai", "nlp", "algorithm", "qa ", "qa/", "automation", "sre",
               "architect", "programmer", "python", "java", "infrastructure",
               "cloud", "security", "platform", "r&d", "research", "scientist",
               "analytics", "bi ", "database", "mobile", "ios", "android",
               "web ", "tech lead", "cto")

    def is_tech(title, dept_names):
        t = (title or "").lower()
        d = " ".join(dept_names or []).lower()
        blob = t + " || " + d
        # obvious non-tech exclusions
        if any(x in t for x in ("transcriber", "captioner", "scoper",
                                "proofreader", "editor - ", "sales",
                                "account executive", "recruiter",
                                "customer success", "marketing", "hr ",
                                "people ", "finance", "legal counsel",
                                "office manager", "receptionist")):
            # allow if it also clearly names an engineering/data function
            if not any(k in t for k in ("engineer", "developer", "data",
                                        "software", "devops", "qa",
                                        "architect", "scientist")):
                return False
        if "r&d" in d or "engineering" in d or "research" in d or "product" in d or "data" in d:
            return True
        return any(k in blob for k in tech_kw)

    def level_of(title):
        t = (title or "").lower()
        if any(k in t for k in ("intern", "internship", "student", "graduate", "working student")):
            return "student"
        if any(k in t for k in ("senior", "sr.", "sr ", "lead", "principal",
                                "staff", "director", "head of", "head ",
                                "manager", "architect", "vp ")):
            return "senior"
        if any(k in t for k in ("junior", "jr.", "jr ", "entry", "associate")):
            return "junior"
        return ""

    def parse_years(text):
        if not text:
            return (None, None)
        t = text.lower()
        # ranges: "3-5 years", "3 to 5 years"
        m = re.search(r"(\d{1,2})\s*(?:-|to|–|—)\s*(\d{1,2})\s*\+?\s*years", t)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if a <= b <= 40:
                return (a, b)
        # "4+ years" / "at least 4 years" / "minimum of 3 years"
        m = re.search(r"(?:at least|minimum of|min\.?\s*of|min\.?)?\s*(\d{1,2})\s*\+?\s*years", t)
        if m:
            a = int(m.group(1))
            if 0 <= a <= 40:
                return (a, None)
        return (None, None)

    tech_terms = [
        "python", "java", "javascript", "typescript", "node.js", "nodejs",
        "node", "react", "angular", "vue", "go", "golang", "rust", "c++",
        "c#", ".net", "ruby", "php", "kotlin", "swift", "scala",
        "pytorch", "tensorflow", "keras", "scikit-learn", "sklearn",
        "pandas", "numpy", "spark", "hadoop", "kafka", "airflow",
        "aws", "azure", "gcp", "google cloud", "kubernetes", "k8s",
        "docker", "terraform", "ansible", "jenkins", "gitlab", "ci/cd",
        "linux", "bash", "sql", "postgresql", "postgres", "mysql",
        "mongodb", "redis", "elasticsearch", "graphql", "rest", "grpc",
        "microservices", "llm", "nlp", "asr", "genai", "generative ai",
        "machine learning", "deep learning", "computer vision",
        "selenium", "cypress", "playwright", "django", "flask", "fastapi",
        "spring", "rabbitmq", "snowflake", "databricks", "dbt",
    ]

    def extract_tech(text):
        if not text:
            return []
        t = text.lower()
        found = []
        for term in tech_terms:
            if term in t and term not in found:
                found.append(term)
        return found[:25]

    # --- fetch (paginated, resilient) ------------------------------------
    seen = set()
    for page in range(1, 6):  # newest ~5 pages
        if len(out) >= 120:
            break
        params = {
            "per_page": 100,
            "page": page,
            "orderby": "date",
            "order": "desc",
            "_embed": "wp:term",
        }
        try:
            resp = requests.get(base, params=params, headers=headers, timeout=30)
        except Exception:
            break
        if resp.status_code != 200:
            break
        try:
            resp.encoding = "utf-8"
            jobs = resp.json()
        except Exception:
            break
        if not isinstance(jobs, list) or not jobs:
            break

        for j in jobs:
            try:
                jid = j.get("id")
                if jid in seen:
                    continue
                seen.add(jid)

                title = (j.get("title") or {}).get("rendered", "") or ""
                title = BeautifulSoup(title, "lxml").get_text(" ", strip=True)
                url = j.get("link", "") or ""

                # resolve department + location from embedded terms
                dept_names, loc_name, loc_slug = [], "", ""
                emb = (j.get("_embedded") or {}).get("wp:term") or []
                for group in emb:
                    for term in (group or []):
                        tax = term.get("taxonomy")
                        name = BeautifulSoup(term.get("name", "") or "",
                                             "lxml").get_text(" ", strip=True)
                        if tax == "department" and name:
                            dept_names.append(name)
                        elif tax == "location" and name and not loc_name:
                            loc_name = name
                            loc_slug = term.get("slug", "") or ""
                # fallback to class_list slugs if embed missing
                if not loc_slug:
                    for c in (j.get("class_list") or []):
                        if isinstance(c, str) and c.startswith("location-"):
                            loc_slug = c[len("location-"):]
                            break

                if not is_israel(loc_name, loc_slug):
                    continue
                if not is_tech(title, dept_names):
                    continue

                # description text
                html = (j.get("content") or {}).get("rendered", "") or ""
                desc = ""
                if html:
                    desc = BeautifulSoup(html, "lxml").get_text(" ", strip=True)
                    desc = re.sub(r"\s+", " ", desc).strip()
                    if len(desc) > 5000:
                        desc = desc[:5000]

                # city best-effort
                city = ""
                if loc_name:
                    city = loc_name.split(",")[0].strip()
                elif loc_slug:
                    city = loc_slug.replace("-il", "").replace("-", " ").strip().title()

                ymin, ymax = parse_years(desc)
                tech = extract_tech(title + " " + desc)

                out.append({
                    "source": "verbit",
                    "sid": str(jid),
                    "title": title,
                    "company": "Verbit",
                    "city": city,
                    "url": url,
                    "level": level_of(title),
                    "years_min": ymin,
                    "years_max": ymax,
                    "tech": tech,
                    "desc": desc,
                    "active": True,
                })
                if len(out) >= 120:
                    break
            except Exception:
                continue

        # small board: stop early if this page was not full
        if len(jobs) < 100:
            break
        time.sleep(1.0)

    return out
