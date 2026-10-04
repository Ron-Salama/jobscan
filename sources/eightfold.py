# -*- coding: utf-8 -*-
"""Eightfold "PCSX" careers sites (Qualcomm, Microsoft) - Israel jobs.

Brands run in parallel, one thread + one session per host.
"""


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
