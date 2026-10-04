# -*- coding: utf-8 -*-
"""Oracle Recruiting Cloud tenants (Oracle, Dell) - Israel roles over the public REST API.
"""


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
