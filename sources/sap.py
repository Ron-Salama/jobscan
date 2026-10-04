# -*- coding: utf-8 -*-
"""SAP careers - Israel jobs (SAP Labs Israel, Ra'anana).

SAP is mid-migration between two careers sites; the legacy SuccessFactors site holds
the jobs and the new one is probed every run.
"""


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
