# -*- coding: utf-8 -*-
"""Check Point careers (own PHP/Solr search) - Israel jobs.

Unioned with the same postings mirrored on SmartRecruiters, so a job missing from
the careers index cannot slip through.
"""


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
