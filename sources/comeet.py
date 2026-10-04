# -*- coding: utf-8 -*-
"""Comeet public careers API - one JSON call per company board, full JD included.

Keeps Israel (country == 'IL') tech/software roles. Company boards are registered
inside src_comeet.
"""


def src_comeet():
    """
    Comeet adapter for the JobScan Israel tech-job scanner.
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
        # added 2026-10-02 (data-security company, R&D in Tel Aviv):
        ("Cyera",              "17.008", "7182A90154871823783FD838C031A802378"),
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
