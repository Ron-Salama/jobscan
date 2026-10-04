# -*- coding: utf-8 -*-
"""Google careers (own site, no third-party ATS) - Israel jobs.

The job data is parsed from the server-rendered AF_initDataCallback blob.
"""


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
