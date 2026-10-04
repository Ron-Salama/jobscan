# -*- coding: utf-8 -*-
"""SmartRecruiters public postings API (Wix, SanDisk) - Israel postings.
"""


def src_smartrecruiters():
    """SmartRecruiters public postings API adapter (Wix, SanDisk).

    List:   GET https://api.smartrecruiters.com/v1/companies/{cid}/postings?country=il&limit=100&offset=N
    Detail: GET https://api.smartrecruiters.com/v1/companies/{cid}/postings/{postingId}
            -> postingUrl + jobAd.sections (jobDescription / qualifications / ...)
    No auth, no cookies, no JS. Returns only Israel postings. Never raises.
    """
    out = []
    try:
        import re
        import time
        import html as _html
        import requests

        try:
            from bs4 import BeautifulSoup
        except Exception:
            BeautifulSoup = None

        # brand (as shown in the tracker) -> SmartRecruiters company identifier.
        # Verified live 2026-09-24. NOTE: Wix is "Wix2" ("Wix" returns totalFound=0).
        REGISTRY = {
            "Wix": "Wix2",
            "SanDisk": "Sandisk",
        }

        API = "https://api.smartrecruiters.com/v1/companies/%s/postings"
        UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
        PAGE_LIMIT = 100
        MAX_PAGES = 10              # 1000 postings per company, far above real IL volume
        MAX_DETAIL = 80             # JD detail fetches per company
        DESC_CAP = 2500
        SLEEP = 0.3
        BUDGET_S = 85.0             # whole-adapter wall-clock budget
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
            if not h:
                return ""
            txt = ""
            if BeautifulSoup is not None:
                try:
                    txt = BeautifulSoup(h, "html.parser").get_text(" ")
                except Exception:
                    txt = ""
            if not txt:
                txt = re.sub(r"<[^>]+>", " ", h)
            txt = _html.unescape(txt).replace(" ", " ").replace("�", " ")
            return re.sub(r"\s+", " ", txt).strip()

        def _city(loc):
            loc = loc or {}
            c = re.sub(r"\s+", " ", str(loc.get("city") or "")).strip(" ,")
            if not c:
                return "Israel"
            low = c.lower()
            if low in ("israel", "il", "isr"):
                return "Israel"
            if low.startswith("tel aviv") or low.startswith("tel-aviv"):
                return "Tel Aviv"       # "Tel Aviv-Yafo" -> "Tel Aviv"
            return c

        def _is_israel(loc):
            loc = loc or {}
            if str(loc.get("country") or "").lower() == "il":
                return True
            return "israel" in str(loc.get("fullLocation") or "").lower()

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
            t = (text or "").lower().replace("–", "-").replace("—", "-")
            if not t:
                return (None, None)

            def _near(s, e):
                # "4+ years of professional software development experience" puts
                # the word ~50 chars after the number -> wider window on the right.
                ctx = t[max(0, s - 45):min(len(t), e + 75)]
                return "experien" in ctx or "exp." in ctx

            # FIRST experience-requirement in text order wins: the headline requirement
            # comes first ("4+ years SWE ... 2-3 years as team lead" -> 4, not 2-3;
            # "5+ years testing and 2 years in API testing" -> 5).
            rx = re.compile(r"(\d{1,2})\s*(?:(?:-|to)\s*(\d{1,2})\s*)?\+?\s*(?:years?|yrs)\b")
            for m in rx.finditer(t):
                a = int(m.group(1))
                b = int(m.group(2)) if m.group(2) else None
                if a > 40 or (b is not None and not (a <= b <= 40)):
                    continue
                # "N+ years" / "N-M years" in the role/requirements text is a requirement
                # even without the word "experience" ("3+ years in data engineering");
                # a bare "N years" needs "experience" nearby (avoids "20 years of innovation").
                explicit = (b is not None or "+" in m.group(0)) and a <= 15
                if not (explicit or _near(m.start(), m.end())):
                    continue
                return (a, b)
            return (None, None)

        TECH = [
            (r"\bpython\b", "Python"), (r"\bjava\b", "Java"),
            (r"\bjavascript\b", "JavaScript"), (r"\btypescript\b", "TypeScript"),
            (r"c\+\+", "C++"), (r"\bc#|\.net\b", "C#/.NET"),
            # plain C only in unambiguous phrasings (a bare "c" is often a list letter)
            (r"\bc\s*/\s*c\+\+|\bc\s+(?:and|or|&)\s+c\+\+|\bc\s+programming|\bansi c\b"
             r"|\bembedded c\b|\b(?:in|with)\s+c\b(?![+#])", "C"),
            # "go" alone is plain English ("go live") -> only golang or "go" inside a language list
            (r"\bgolang\b|\bgo\s*\(golang\)"
             r"|\b(?:python|java|rust|kotlin|scala|node(?:\.?js)?|c\+\+),\s*go\b"
             r"|\bgo,\s*(?:python|java|rust|kotlin|scala|node|c\+\+)", "Go"),
            (r"\brust\b", "Rust"),
            (r"\bkotlin\b", "Kotlin"), (r"\bscala\b", "Scala"), (r"\bsql\b", "SQL"),
            (r"\breact\b", "React"), (r"\bangular\b", "Angular"), (r"\bvue\b", "Vue"),
            (r"\bnode(\.?js)?\b", "Node.js"), (r"\bspring\b", "Spring"),
            (r"\bkubernetes\b|\bk8s\b", "Kubernetes"), (r"\bdocker\b", "Docker"),
            (r"\bterraform\b", "Terraform"), (r"\baws\b", "AWS"),
            (r"\bgcp\b|google cloud", "GCP"), (r"\bazure\b", "Azure"),
            (r"\blinux\b", "Linux"), (r"\bembedded\b", "Embedded"), (r"\brtos\b", "RTOS"),
            (r"\bsystemverilog\b", "SystemVerilog"), (r"\bverilog\b", "Verilog"),
            (r"\buvm\b", "UVM"), (r"\bvhdl\b", "VHDL"), (r"\bfpga\b", "FPGA"),
            (r"\basic\b", "ASIC"), (r"\bpcie\b", "PCIe"), (r"\bnvme\b", "NVMe"),
            (r"\bpytorch\b", "PyTorch"), (r"\btensorflow\b", "TensorFlow"),
            (r"\bspark\b", "Spark"), (r"\bkafka\b", "Kafka"),
            (r"\bmongodb\b", "MongoDB"), (r"\bpostgres(ql)?\b", "PostgreSQL"),
            (r"\bmysql\b", "MySQL"), (r"\bredis\b", "Redis"),
            (r"\bgraphql\b", "GraphQL"), (r"\bgrpc\b", "gRPC"),
            (r"\bmicroservices?\b", "Microservices"), (r"ci/cd|ci-cd", "CI/CD"),
            (r"\bselenium\b", "Selenium"), (r"\bplaywright\b", "Playwright"),
            (r"\bcypress\b", "Cypress"), (r"\bjenkins\b", "Jenkins"),
            (r"machine learning", "Machine Learning"), (r"deep learning", "Deep Learning"),
            (r"\bnlp\b", "NLP"), (r"computer vision", "Computer Vision"),
            (r"\bllms?\b|large language model", "LLM"),
            (r"\bgen ?ai\b|generative ai", "GenAI"),
        ]

        def _tech(text):
            t = (text or "").lower()
            found = []
            for rx, name in TECH:
                try:
                    if re.search(rx, t) and name not in found:
                        found.append(name)
                except Exception:
                    pass
            return found

        def _desc_from(detail):
            """JD text: role + requirements first (company blurb last, only if room)."""
            secs = ((detail or {}).get("jobAd") or {}).get("sections") or {}

            def _sec(key):
                s = secs.get(key) or {}
                txt = _clean(s.get("text") or "")
                if not txt:
                    return ""
                label = (s.get("title") or "").strip()
                return (label + ": " + txt) if label else txt

            def _cut(s, n):
                if n <= 0:
                    return ""
                return s if len(s) <= n else s[:n].rsplit(" ", 1)[0] + " ..."

            jd, qual = _sec("jobDescription"), _sec("qualifications")
            core = (jd + " " + qual).strip()          # full text for years/tech
            # Requirements must survive the cap (the fit judge needs them): if both
            # don't fit, shrink the role description first, never below ~900 chars.
            if len(jd) + len(qual) + 2 > DESC_CAP:
                jd_room = max(900, DESC_CAP - len(qual) - 2)
                jd = _cut(jd, jd_room)
                qual = _cut(qual, DESC_CAP - len(jd) - 2)
            parts = [p for p in (jd, qual) if p]
            # boilerplate sections only if there is room left
            for key in ("additionalInformation", "companyDescription"):
                used = len("\n".join(parts))
                extra = _sec(key)
                if extra and used + 2 + len(extra) <= DESC_CAP:
                    parts.append(extra)
            desc = "\n".join(parts)
            if not desc:
                # unusual jobAd layout: fall back to any section text
                desc = " ".join(_clean((v or {}).get("text") or "")
                                for v in secs.values() if isinstance(v, dict))
                core = core or desc
            if len(desc) > DESC_CAP:
                desc = desc[:DESC_CAP].rsplit(" ", 1)[0]
            return desc, core

        seen = set()
        for brand, cid in REGISTRY.items():
            try:
                # ---- 1. list all Israel postings (paginated) ----
                postings, offset = [], 0
                for _ in range(MAX_PAGES):
                    # list pages are cheap and are the whole point -> small grace period
                    if (time.time() - t0) > BUDGET_S + 5:
                        break
                    d = _get_json(API % cid, {"country": "il", "limit": PAGE_LIMIT,
                                              "offset": offset})
                    time.sleep(SLEEP)
                    if not isinstance(d, dict):
                        break
                    content = d.get("content") or []
                    postings.extend(content)
                    total = int(d.get("totalFound") or 0)
                    offset += len(content)
                    if not content or offset >= total:
                        break

                # ---- 2. build rows, enrich the first MAX_DETAIL with JD detail ----
                n_detail, fails = 0, 0
                for p in postings:
                    try:
                        pid = str(p.get("id") or "").strip()
                        loc = p.get("location") or {}
                        if not pid or not _is_israel(loc):
                            continue
                        sid = pid           # SmartRecruiters posting ids are globally unique
                        if sid in seen:
                            continue
                        title = re.sub(r"\s+", " ", _html.unescape(p.get("name") or "")).strip()
                        if not title:
                            continue
                        url = "https://jobs.smartrecruiters.com/%s/%s" % (cid, pid)
                        desc, core = "", ""
                        # detail = JD text + canonical URL; circuit-breaker after 3 straight
                        # failures so an outage of the detail endpoint can't eat the budget
                        # (rows are still emitted with the fallback URL and empty desc).
                        if n_detail < MAX_DETAIL and fails < 3 and _time_left():
                            det = _get_json((API % cid) + "/" + pid)
                            n_detail += 1
                            time.sleep(SLEEP)
                            if isinstance(det, dict):
                                fails = 0
                                if det.get("active") is False:
                                    continue
                                url = det.get("postingUrl") or url
                                desc, core = _desc_from(det)
                            else:
                                fails += 1
                        ymin, ymax = _years(core or desc)
                        seen.add(sid)
                        out.append({
                            "source": "smartrecruiters:%s" % brand.lower(),
                            "sid": sid,
                            "title": title,
                            "company": brand,
                            "city": _city(loc),
                            "url": url,
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
