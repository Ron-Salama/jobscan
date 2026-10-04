# -*- coding: utf-8 -*-
"""TechJob (techjob.co.il) - open FeathersJS API (titles only).

Not registered in jobscan._EXT_NAMES (disabled 2026-09-23: broken links + no JD).
"""


def src_techjob():
    """TechJob (techjob.co.il) open FeathersJS API adapter.

    Israeli tech job board. The public API (api.techjob.co.il/jobs) returns a
    very thin payload: only _id, _modified, title, and a mostly-empty
    siteMetaData object. company / city / description / seniority are NOT
    exposed by the API, and the SPA job page (jobs-lobby?job=<id>) is
    client-rendered so there is nothing to scrape server-side. We therefore
    return thin records, deriving level/tech best-effort from the title and
    city/tech from siteMetaData when (rarely) populated. The caller dedups
    across days and applies the scanner's filters.
    """
    import requests
    import re
    import time

    API = "https://api.techjob.co.il/jobs"
    JOB_URL = "https://www.techjob.co.il/jobs-lobby?job="
    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")
    headers = {"User-Agent": UA, "Accept": "application/json",
               "Referer": "https://www.techjob.co.il/"}

    TECH_KEYS = [
        "python", "java", "javascript", "typescript", "react native", "react",
        "angular", "vue", "node.js", "nodejs", "node", ".net", "c#", "c++",
        "golang", "go", "rust", "ruby", "php", "scala", "kotlin", "swift",
        "django", "flask", "fastapi", "spring", "aws", "azure", "gcp",
        "kubernetes", "k8s", "docker", "terraform", "devops", "sql", "nosql",
        "mongodb", "postgres", "mysql", "redis", "kafka", "spark", "hadoop",
        "machine learning", "deep learning", "data science", "nlp", "llm",
        "genai", "ml", "ai", "android", "ios", "flutter", "embedded", "fpga",
        "verilog", "qa", "automation", "selenium", "cypress", "salesforce",
        "sap", "elixir", "linux", "graphql", "microservices", "cyber",
        "security", "fullstack", "full stack", "frontend", "backend",
    ]

    def guess_level(title):
        t = title.lower()
        if re.search(r"(?<![a-z])(student|intern|internship)(?![a-z])", t) \
           or "סטודנט" in title \
           or "התמחות" in title:
            return "student"
        if re.search(r"(?<![a-z])(senior|sr\.?|lead|principal|staff|expert|"
                     r"architect|head\s+of|team\s+lead|tl)(?![a-z])", t):
            return "senior"
        if re.search(r"(?<![a-z])(junior|jr\.?|entry[- ]?level)(?![a-z])", t):
            return "junior"
        return ""

    def guess_tech(title):
        t = title.lower()
        found = []
        for kw in TECH_KEYS:
            pat = r"(?<![a-z0-9])" + re.escape(kw) + r"(?![a-z0-9])"
            if re.search(pat, t):
                found.append(kw)
        seen = set()
        uniq = []
        for k in found:
            if k not in seen:
                seen.add(k)
                uniq.append(k)
        return uniq

    # ---- pull only the newest ~100 listings (4 pages of 25) ----
    records = []
    for skip in (0, 25, 50, 75):
        params = {"$sort[_modified]": "-1", "$limit": "25", "$skip": str(skip)}
        try:
            r = requests.get(API, params=params, headers=headers, timeout=20)
            if r.status_code != 200:
                continue
            data = r.json().get("data", [])
        except Exception:
            data = []
        if data:
            records.extend(data)
        try:
            time.sleep(0.3)
        except Exception:
            pass
        if len(records) >= 120:
            break

    out = []
    seen_ids = set()
    for rec in records:
        try:
            sid = rec.get("_id")
            if not sid or sid in seen_ids:
                continue
            seen_ids.add(sid)
            title = (rec.get("title") or "").strip()
            if not title:
                continue

            md = rec.get("siteMetaData") or {}
            regions = md.get("regions") if isinstance(md, dict) else None
            techs_meta = md.get("techs") if isinstance(md, dict) else None

            city = ""
            if isinstance(regions, list):
                parts = [str(x).strip() for x in regions if str(x).strip()]
                city = ", ".join(parts)

            tech = guess_tech(title)
            if isinstance(techs_meta, list):
                lowered = [x.lower() for x in tech]
                for tm in techs_meta:
                    tm = str(tm).strip()
                    if tm and tm.lower() not in lowered:
                        tech.append(tm)
                        lowered.append(tm.lower())

            out.append({
                "source": "techjob",
                "sid": str(sid),
                "title": title,
                "company": "",
                "city": city,
                "url": JOB_URL + str(sid),
                "level": guess_level(title),
                "years_min": None,
                "years_max": None,
                "tech": tech,
                "desc": "",
                "active": True,
            })
        except Exception:
            continue
        if len(out) >= 120:
            break

    return out
