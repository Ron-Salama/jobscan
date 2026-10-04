# -*- coding: utf-8 -*-
"""Ashby public posting API (Moon Active, monday.com) - a whole board per call.

src_moonactive is a thin wrapper kept for the old ("moonactive", ...) registration.
"""

from ._common import _is_student_title


# ===== Ashby (open JSON posting API) - generalized from src_moonactive 2026-09-24 =====
# slug -> (company, source, tech_only). The whole board comes back in ONE call:
#   GET https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=false
# moonactive keeps source "moonactive" so rows already in seen.json keep their keys.
# monday.com moved here from Greenhouse (its GH board 404s) and is a GIANT, so every
# Israel role is returned (tech_only=False; its departments are product-area names).
ASHBY_BOARDS = {
    "moonactive": ("Moon Active", "moonactive", True),
    "monday.com": ("monday.com", "ashby:monday.com", False),
}


def src_ashby(slugs=None):
    """Ashby public posting API -> newest Israel-based roles for each registered board
    (tech/software roles only unless the board is a giant). A failed board is logged
    with its status/exception. Never raises."""
    import re, time, json
    try:
        import requests
    except Exception:
        return []
    try:
        from bs4 import BeautifulSoup
    except Exception:
        BeautifulSoup = None

    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
    headers = {"User-Agent": UA, "Accept": "application/json"}
    out = []
    per_board = {}
    try:
        slugs = list(slugs) if slugs else list(ASHBY_BOARDS.keys())
    except Exception:
        slugs = list(ASHBY_BOARDS.keys())

    # ---- helpers ---------------------------------------------------------
    def is_israel(job):
        try:
            pa = ((job.get("address") or {}).get("postalAddress") or {})
            if str(pa.get("addressCountry", "")).strip().lower() == "israel":
                return True
            blob = json.dumps(
                [job.get("location"), job.get("secondaryLocations"),
                 job.get("address")], ensure_ascii=False).lower()
            return ("israel" in blob or "tel aviv" in blob
                    or "tel-aviv" in blob or "herzliya" in blob
                    or "petah" in blob or "raanana" in blob)
        except Exception:
            return False

    TECH_DEPTS = ("r&d", "data", "analytics", "security", " it",
                  "it ", "engineering", "platform", "technology", "devops",
                  "infrastructure")
    TECH_KW = ("engineer", "developer", "devops", "sre", "backend",
               "back end", "frontend", "front end", "full stack", "fullstack",
               "full-stack", "software", "data ", "data analyst",
               "data scientist", "security", "qa ", "automation", "architect",
               "unity", "game engineer", "technical", "infrastructure",
               "cloud", "machine learning", " ml", "ml ", " ai", "ai ",
               "algorithm", "programmer", "android", "ios",
               "platform", "python", "researcher")

    def is_tech(job):
        dept = str(job.get("department") or "").lower()
        team = str(job.get("team") or "").lower()
        title = str(job.get("title") or "").lower()
        if any(d in dept or d in team for d in TECH_DEPTS):
            return True
        if any(k in title for k in TECH_KW):
            return True
        return False

    def derive_level(title):
        if _is_student_title(title):
            return "student"
        t = " " + title.lower() + " "
        if any(w in t for w in (" apprentice ",)):
            return "student"
        if any(w in t for w in (" junior ", " jr ", " jr. ", " entry ",
                                " graduate ", " grad ")):
            return "junior"
        if any(w in t for w in (" senior ", " sr ", " sr. ", " lead ",
                                " principal ", " staff ", " head ",
                                " director ", " manager ", " expert ",
                                " team lead ", " architect ")):
            return "senior"
        return ""

    def parse_years(text):
        if not text:
            return (None, None)
        t = text.lower().replace("–", "-").replace("—", "-")
        # range: "3-5 years"
        m = re.search(r"(\d{1,2})\s*-\s*(\d{1,2})\s*\+?\s*(?:years|yrs|year)",
                      t)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if 0 <= a <= 40 and 0 <= b <= 40 and a <= b:
                return (a, b)
        # "at least/minimum of N years", "N+ years", "N years"
        for pat in (r"(?:at least|minimum of|min\.?)\s*(\d{1,2})\s*\+?\s*"
                    r"(?:years|yrs|year)",
                    r"(\d{1,2})\s*\+\s*(?:years|yrs|year)",
                    r"(\d{1,2})\s*(?:years|yrs|year)s?\s+of\s+"
                    r"(?:experience|exp|relevant|hands)"):
            m = re.search(pat, t)
            if m:
                v = int(m.group(1))
                if 0 <= v <= 40:
                    return (v, None)
        return (None, None)

    TECH_TAGS = [
        ("python", r"\bpython\b"), ("java", r"\bjava\b"),
        ("javascript", r"\bjavascript\b|\bjs\b"),
        ("typescript", r"\btypescript\b|\bts\b"),
        ("node.js", r"\bnode\.?js\b|\bnode\b"), ("react", r"\breact\b"),
        ("angular", r"\bangular\b"), ("vue", r"\bvue\b"),
        ("go", r"\bgolang\b|\bgo lang\b"), ("c++", r"c\+\+"),
        ("c#", r"c#|\.net\b|\bdotnet\b"), ("ruby", r"\bruby\b"),
        ("php", r"\bphp\b"), ("kotlin", r"\bkotlin\b"),
        ("swift", r"\bswift\b"), ("scala", r"\bscala\b"),
        ("rust", r"\brust\b"), ("unity", r"\bunity\b"),
        ("unreal", r"\bunreal\b"), ("aws", r"\baws\b|amazon web services"),
        ("gcp", r"\bgcp\b|google cloud"), ("azure", r"\bazure\b"),
        ("kubernetes", r"\bkubernetes\b|\bk8s\b"), ("docker", r"\bdocker\b"),
        ("terraform", r"\bterraform\b"), ("ansible", r"\bansible\b"),
        ("jenkins", r"\bjenkins\b"), ("ci/cd", r"\bci/?cd\b"),
        ("sql", r"\bsql\b"), ("mongodb", r"\bmongo\b|\bmongodb\b"),
        ("postgresql", r"\bpostgres\b|\bpostgresql\b"),
        ("mysql", r"\bmysql\b"), ("redis", r"\bredis\b"),
        ("kafka", r"\bkafka\b"), ("spark", r"\bspark\b"),
        ("airflow", r"\bairflow\b"), ("tensorflow", r"\btensorflow\b"),
        ("pytorch", r"\bpytorch\b"),
        ("machine learning", r"machine learning|\bml\b"),
        ("graphql", r"\bgraphql\b"), ("grpc", r"\bgrpc\b"),
        ("microservices", r"\bmicroservices?\b"), ("linux", r"\blinux\b"),
        ("bash", r"\bbash\b|\bshell scripting\b"), ("git", r"\bgit\b"),
        ("elasticsearch", r"\belasticsearch\b|\belastic\b"),
        ("snowflake", r"\bsnowflake\b"), ("bigquery", r"\bbigquery\b"),
        ("tableau", r"\btableau\b"), ("looker", r"\blooker\b"),
        ("rest", r"\brest\b|\brestful\b"), ("graphite", r"\bgraphite\b"),
    ]

    def extract_tech(text):
        if not text:
            return []
        t = text.lower()
        found = []
        for name, pat in TECH_TAGS:
            try:
                if re.search(pat, t):
                    found.append(name)
            except Exception:
                pass
        return found

    def clean_text(html, plain):
        if plain:
            return plain.strip()
        if html and BeautifulSoup is not None:
            try:
                return BeautifulSoup(html, "lxml").get_text(" ", strip=True)
            except Exception:
                pass
        if html:
            return re.sub(r"<[^>]+>", " ", html).strip()
        return ""

    def pub_key(job):
        return str(job.get("publishedAt") or "")

    for slug in slugs:
        company, source, tech_only = ASHBY_BOARDS.get(slug, (slug, "ashby:" + slug, True))
        url = ("https://api.ashbyhq.com/posting-api/job-board/"
               + slug + "?includeCompensation=false")
        data = None
        try:
            r = requests.get(url, headers=headers, timeout=30)
            if r.status_code == 200:
                data = r.json()
            else:
                per_board[slug] = "FAILED HTTP %s" % r.status_code
        except Exception as e:
            per_board[slug] = "FAILED %s" % type(e).__name__
        if not isinstance(data, dict) or not data.get("jobs"):
            per_board.setdefault(slug, "FAILED empty board")
            time.sleep(0.5)
            continue

        jobs = data.get("jobs") or []
        # ---- sort newest first, then filter ------------------------------
        try:
            jobs = sorted(jobs, key=pub_key, reverse=True)
        except Exception:
            pass

        n = 0
        for job in jobs[:400]:
            try:
                if not job.get("isListed", True):
                    continue
                if not is_israel(job):
                    continue
                if tech_only and not is_tech(job):
                    continue

                title = str(job.get("title") or "").strip()
                if not title:
                    continue
                sid = str(job.get("id") or job.get("jobUrl") or title)
                jurl = (job.get("jobUrl") or job.get("applyUrl") or "")

                pa = ((job.get("address") or {}).get("postalAddress") or {})
                city = (pa.get("addressLocality")
                        or job.get("location") or "Israel")
                city = str(city).strip()
                if job.get("isRemote") and "remote" not in city.lower():
                    city = city + " (Remote)"

                desc_full = clean_text(job.get("descriptionHtml"),
                                       job.get("descriptionPlain"))
                level = derive_level(title)
                ymin, ymax = parse_years(desc_full)
                tech = extract_tech(desc_full + " " + title)
                desc = desc_full[:1500].strip()

                out.append({
                    "source": source,
                    "sid": sid,
                    "title": title,
                    "company": company,
                    "city": city,
                    "url": jurl,
                    "level": level,
                    "years_min": ymin,
                    "years_max": ymax,
                    "tech": tech,
                    "desc": desc,
                    "active": True,
                })
                n += 1
                if n >= 120:
                    break
            except Exception:
                continue
        per_board[slug] = n
        time.sleep(0.5)

    try:
        print("    ashby per-board:", per_board)
    except Exception:
        pass
    return out


def src_moonactive():
    """Moon Active (Coin Master) careers via the Ashby public posting API.
    Thin wrapper kept so an existing ("moonactive", src_moonactive) registration keeps
    working; src_ashby() covers moonactive + monday.com. Never raises."""
    return src_ashby(["moonactive"])
