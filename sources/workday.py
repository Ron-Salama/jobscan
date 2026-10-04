# -*- coding: utf-8 -*-
"""Workday CXS adapter for the giant companies.

Per brand: discover every Israel location facet, then page each facet to the end
(every row is Israel by construction).
"""

import html
import json
import re
import time

import requests
from bs4 import BeautifulSoup


def src_workday():
    """Generic Workday CXS adapter for the giant companies.

    Per brand (audit 2026-09-24, BUG 5 - the old adapter paged a GLOBAL keyword
    search and saw ~34% of NVIDIA's Israel postings):
      1. POST {searchText:'', limit:1} unfiltered and read `facets` (walking the nested
         locationMainGroup) -> every location facet value whose descriptor names Israel
         ('Israel', 'Israel, Yokneam', 'Tel Aviv-Yafo, Israel', 'Office - Israel - ...',
         'ISR-Tel Aviv ...'), grouped by facet parameter (locationHierarchy1,
         locations, Location_Country, Country, ...).
      2. For each such parameter, page {appliedFacets:{param:[ids]}, searchText:'',
         limit:20, offset} until offset >= total (total is only returned on page 1),
         union by externalPath. Every row is Israel by construction, so there is no
         multi-location probing and no country re-check.
      3. Fetch each posting's detail (JD, real city) with a per-brand budget; a row that
         misses the budget is kept with an empty desc.
    Prints "facet total vs fetched" per brand. Never raises.
    """
    import threading
    from concurrent.futures import ThreadPoolExecutor

    SOURCE = "workday"
    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

    # brand -> (tenant, wd-host, site). All confirmed live (Israel facet present).
    REGISTRY = {
        "NVIDIA":  ("nvidia",  "wd5", "NVIDIAExternalCareerSite"),
        "Intel":   ("intel",   "wd1", "External"),
        "Philips": ("philips", "wd3", "jobs-and-careers"),
        "Unity":   ("unitytech", "wd1", "Unity"),      # added 2026-09-23
        "Snyk":    ("snyk", "wd103", "External"),       # added 2026-09-23 (no IL facet today)
        # added 2026-09-24 (live-verified Israel facet rows):
        "Palo Alto Networks": ("paloaltonetworks", "wd5", "panwexternalcareers"),  # incl. CyberArk
        "Cisco":      ("cisco", "wd5", "Cisco_Careers"),
        "HP Inc":     ("hp", "wd5", "ExternalCareerSite"),
        "HPE":        ("hpe", "wd5", "Jobsathpe"),
        "Salesforce": ("salesforce", "wd12", "External_Career_Site"),
        "Marvell":    ("marvell", "wd1", "MarvellCareers"),
        "Broadcom":   ("broadcom", "wd1", "External_Career"),
    }

    LIMIT = 20                    # Workday CXS page size (max 20)
    MAX_TOTAL = 400               # per-brand row cap (runtime guard)
    MAX_DETAIL = 400              # per-brand detail-fetch cap
    BRAND_MAX = {"NVIDIA": 800}   # per-brand override of both (NVIDIA alone: ~425 IL postings)
    DETAIL_WORKERS = 4            # parallel detail GETs per brand (each paced 0.3s)

    # facet descriptor names Israel: "Israel", "Israel, Haifa", "Office - Israel - X",
    # or the ISO-3 prefix "ISR-Tel Aviv University" (Broadcom)
    IL_FACET_RX = re.compile(r"\bisrael\b|^\s*isr\b", re.I)

    # Distinctive Israeli location tokens (to pick the Israeli site of a
    # multi-location posting for the city field).
    IL_TOKENS = [
        "israel", "tel aviv", "tel-aviv", "telaviv", "haifa", "yokneam", "yoqneam",
        "jerusalem", "herzliya", "herzeliya", "hertzeliya", "raanana", "ra'anana",
        "raananna", "ra'ananna", "petah tikva", "petach tikva", "petah-tikva",
        "petah tiqwa", "rehovot", "rechovot", "netanya", "nethanya", "beer sheva",
        "be'er sheva", "beersheba", "kfar saba", "kefar sava", "hod hasharon",
        "ramat gan", "caesarea", "qesarya", "karmiel", "carmiel", "migdal haemek",
        "or yehuda", "airport city", "modiin", "modi'in", "holon", "ashdod",
        "nazareth", "kiryat gat", "kiryat", "tefen", "misgav", "yavne", "lod",
        "rosh haayin", "rosh ha'ayin", "ness ziona", "tel hai",
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

    HDRS = {"User-Agent": UA, "Accept": "application/json",
            "Content-Type": "application/json"}
    sess = requests.Session()
    sess.headers.update(HDRS)
    _tl = threading.local()

    def _tsess():
        # one Session per detail worker thread (Session is not guaranteed thread-safe)
        s = getattr(_tl, "s", None)
        if s is None:
            s = requests.Session()
            s.headers.update(HDRS)
            _tl.s = s
        return s

    def _log(msg):
        try:
            print("    workday " + msg)
        except Exception:
            pass

    def _looks_israeli(text):
        t = (text or "").lower()
        return any(tok in t for tok in IL_TOKENS)

    def _is_multi(loc_text):
        return bool(re.search(r"\d+\s+location", (loc_text or "").lower()))

    def _city_from(loc):
        # "Israel, Yokneam" -> Yokneam; "Tel Aviv-Yafo, Israel" -> Tel Aviv-Yafo;
        # "Ness Ziona, Center District, Israel" -> Ness Ziona, Center District;
        # "Office - Israel - Tel Aviv" -> Tel Aviv; "ISR-Tel Aviv University" ->
        # Tel Aviv University; "IL - Petah Tikva" -> Petah Tikva.
        if not loc:
            return ""
        loc = re.sub(r"\s+", " ", str(loc)).strip()
        if _is_multi(loc):
            return ""
        stripped = re.sub(r"^(?:\s*(?:office|israel|isr|il)\s*-\s*)+", "", loc, flags=re.I).strip()
        if stripped and stripped.lower() not in ("home based", "remote"):
            loc = stripped
        parts = [p.strip() for p in loc.split(",") if p.strip()]
        keep = [p for p in parts if p.lower() != "israel"]
        return ", ".join(keep) if keep else loc

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

    def _walk_facets(facets):
        # yields (facetParameter, id, descriptor, count) for every leaf value, descending
        # into nested groups such as locationMainGroup -> locationHierarchy1/locations
        # (count = the value's posting count, 0 when the tenant doesn't report it)
        for f in facets or []:
            if not isinstance(f, dict):
                continue
            param = f.get("facetParameter") or ""
            for v in f.get("values") or []:
                if not isinstance(v, dict):
                    continue
                if "values" in v and "facetParameter" in v:
                    for x in _walk_facets([v]):
                        yield x
                    continue
                try:
                    cnt = int(v.get("count") or 0)
                except Exception:
                    cnt = 0
                yield param, v.get("id"), (v.get("descriptor") or ""), cnt

    def _post(base, facets, offset, limit):
        body = {"appliedFacets": facets, "limit": limit, "offset": offset, "searchText": ""}
        for attempt in range(2):
            try:
                r = sess.post(base, data=json.dumps(body), timeout=25)
                time.sleep(0.3)
                if r.status_code == 200 and "json" in r.headers.get("content-type", ""):
                    return r.json()
            except Exception:
                pass
            time.sleep(1.0 + attempt)
        return None

    def _fetch_detail(tenant, wd, site, ext):
        url = f"https://{tenant}.{wd}.myworkdayjobs.com/wday/cxs/{tenant}/{site}{ext}"
        for attempt in range(2):
            try:
                r = _tsess().get(url, timeout=20)
                time.sleep(0.3)
                if r.status_code == 200 and "json" in r.headers.get("content-type", ""):
                    return r.json().get("jobPostingInfo", {}) or {}
            except Exception:
                pass
            time.sleep(0.8)
        return None

    results = {}   # externalPath -> row dict (dedupe)

    for brand, (tenant, wd, site) in REGISTRY.items():
        try:
            base = f"https://{tenant}.{wd}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"
            pub_base = f"https://{tenant}.{wd}.myworkdayjobs.com/en-US/{site}"
            cap = BRAND_MAX.get(brand, MAX_TOTAL)
            det_cap = BRAND_MAX.get(brand, MAX_DETAIL)

            # 1) discover this tenant's Israel location facet ids
            j0 = _post(base, {}, 0, 1)
            if not j0:
                _log("%s: facet discovery request FAILED -> 0" % brand)
                continue
            global_total = j0.get("total") or 0
            cands = {}   # facetParameter -> [(id, descriptor, count)]
            for param, fid, desc, cnt in _walk_facets(j0.get("facets")):
                if param and fid and IL_FACET_RX.search(desc):
                    cands.setdefault(param, []).append((fid, desc, cnt))
            if not cands:
                _log("%s: no Israel location facet (global %d) -> 0" % (brand, global_total))
                continue
            il_descs = [d for vals in cands.values() for _, d, _ in vals]

            # 2) page every Israel facet parameter until offset >= total
            listed = {}          # ext -> posting (dedupe across parameters)
            facet_total = 0
            for param, vals in cands.items():
                facets = {param: [fid for fid, _, _ in vals]}
                il_count = sum(c for _, _, c in vals)   # what the Israel values say they hold
                offset, total = 0, None
                while len(listed) < cap:
                    jj = _post(base, facets, offset, LIMIT)
                    if jj is None:
                        _log("%s: page offset %d of %s FAILED" % (brand, offset, param))
                        break
                    if total is None:
                        total = jj.get("total") or 0     # only page 1 carries the total
                        # the server ignored the facet (returned the whole tenant) only when the
                        # Israel values themselves hold fewer postings than the tenant: an
                        # Israel-only tenant legitimately has total == global and is kept
                        if total >= global_total and (0 < il_count < global_total
                                                      or (il_count == 0 and global_total > 50)):   # tenant reports no facet counts
                            _log("%s: facet %s ignored by server (total %d = global, Israel %d) -> skipped"
                                 % (brand, param, total, il_count))
                            total = 0
                            break
                    postings = jj.get("jobPostings") or []
                    if not postings:
                        break
                    for p in postings:
                        ext = p.get("externalPath") or ""
                        if ext and ext not in listed:
                            listed[ext] = p
                    offset += LIMIT
                    if total and offset >= total:
                        break
                    if (not total and len(postings) < LIMIT) or offset > 5000:
                        break
                facet_total = max(facet_total, total or 0)

            # 3) detail fetch (JD + real city) within the per-brand budget
            exts = list(listed.keys())[:cap]
            to_detail = exts[:det_cap]
            details = {}
            if to_detail:
                with ThreadPoolExecutor(max_workers=DETAIL_WORKERS) as ex:
                    for ext, det in zip(to_detail, ex.map(
                            lambda e: _fetch_detail(tenant, wd, site, e), to_detail)):
                        details[ext] = det

            n_desc = 0
            for ext in exts:
                p = listed[ext]
                title = (p.get("title") or "").strip()
                if not title:
                    continue
                loc_text = (p.get("locationsText") or "").strip()
                detail = details.get(ext)
                locs = []
                desc = ""
                url_final = f"{pub_base}{ext}"
                if detail:
                    locs = [detail.get("location") or ""] + list(detail.get("additionalLocations") or [])
                    desc = _clean_text(detail.get("jobDescription"))
                    if detail.get("externalUrl"):
                        url_final = detail["externalUrl"]
                locs.append(loc_text)
                # the Israeli site of a (possibly multi-location) posting
                il_loc = (next((l for l in locs if l and IL_FACET_RX.search(l)), "")
                          or next((l for l in locs if l and not _is_multi(l) and _looks_israeli(l)), ""))
                if not il_loc:
                    il_loc = il_descs[0] if len(il_descs) == 1 else "Israel"
                city = _city_from(il_loc) or "Israel"
                if desc:
                    n_desc += 1

                company = brand
                if brand == "Palo Alto Networks" and any("cyberark" in (l or "").lower() for l in locs):
                    company = "Palo Alto Networks (CyberArk)"

                years_min, years_max = _extract_years(desc) if desc else (None, None)
                level = _extract_level(title, desc, years_min, years_max)
                tech = _extract_tech((title + " " + desc) if desc else title)

                results[ext] = {
                    "source": SOURCE,
                    "sid": ext,
                    "title": title,
                    "company": company,
                    "city": city,
                    "url": url_final,
                    "level": level,
                    "years_min": years_min,
                    "years_max": years_max,
                    "tech": tech,
                    "desc": desc[:2500],
                    "active": True,
                }
            _log("%s: facet total %d vs fetched %d (with JD %d)%s"
                 % (brand, facet_total, len(exts), n_desc,
                    "  CAP HIT" if len(listed) >= cap else ""))
        except Exception as e:
            # never raise: keep whatever we already collected
            _log("%s: ERROR %s" % (brand, e))
            continue

    return list(results.values())
