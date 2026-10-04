# -*- coding: utf-8 -*-
"""Booking.com careers (iCIMS Jibe, jobs.booking.com) JSON API - Israel jobs.
"""


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
