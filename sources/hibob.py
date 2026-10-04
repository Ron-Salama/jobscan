# -*- coding: utf-8 -*-
"""HiBob careers page - a WordPress site that server-renders its Comeet board.

The whole board comes back in one HTML GET.
"""


def src_hibob():
    """
    hibob (HiBob) adapter for the JobScan Israel tech-job scanner.
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
