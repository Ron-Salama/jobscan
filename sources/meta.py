# -*- coding: utf-8 -*-
"""Meta careers (metacareers.com) - Relay/GraphQL search, Israel jobs.
"""


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
