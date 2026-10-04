# -*- coding: utf-8 -*-
"""Lemonade careers (makers.lemonade.com).

The whole roster is read from the Next.js __NEXT_DATA__ JSON blob on one page.
"""

from ._common import _is_student_title


def src_lemonade():
    """Lemonade careers (makers.lemonade.com) -> Israel tech/software roles.
    Jobs are embedded in the Next.js __NEXT_DATA__ JSON blob on the careers page
    (props.pageProps.allRecipes). No pagination; the whole roster ships in one page."""
    import json, re, time, random
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
    HEADERS = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9",
               "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}

    # ---- helpers -----------------------------------------------------------
    def _html_to_text(html):
        if not html:
            return ""
        try:
            if BeautifulSoup is not None:
                return BeautifulSoup(html, "lxml").get_text("\n", strip=True)
        except Exception:
            pass
        # stdlib fallback
        txt = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
        txt = re.sub(r"(?is)<br\s*/?>", "\n", txt)
        txt = re.sub(r"(?is)</p>", "\n", txt)
        txt = re.sub(r"(?s)<[^>]+>", " ", txt)
        import html as _h
        txt = _h.unescape(txt)
        return re.sub(r"[ \t]+", " ", txt).strip()

    def _level(title):
        t = (title or "").lower()
        # student: word-bound title test ('intern' no longer hits "Internal ...");
        # 'graduate' is a junior signal, never student
        if _is_student_title(title) or re.search(r"\bapprentice", t):
            return "student"
        if any(k in t for k in ("senior", "sr.", "sr ", " staff", "staff ", "principal",
                                "lead", "director", "head of", "vp ", "chief", "manager",
                                "architect")):
            return "senior"
        if any(k in t for k in ("junior", "jr.", "jr ", "entry level", "entry-level",
                                "graduate")):
            return "junior"
        return ""

    def _years(text):
        if not text:
            return (None, None)
        low = text.lower()
        # range: "3-5 years"
        m = re.search(r"(\d{1,2})\s*[-–to]{1,4}\s*(\d{1,2})\s*\+?\s*years?", low)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if a <= b <= 40:
                return (a, b)
        # "3+ years" / "at least 3 years" / "3 years of experience"
        m = re.search(r"(?:at least|minimum(?: of)?|min\.?)\s*(\d{1,2})\s*\+?\s*years?", low)
        if not m:
            m = re.search(r"(\d{1,2})\s*\+\s*years?", low)
        if not m:
            m = re.search(r"(\d{1,2})\s*years?\s+of\s+(?:experience|software|hands|professional|relevant|industry|backend|back-end)", low)
        if m:
            a = int(m.group(1))
            if 0 <= a <= 40:
                return (a, None)
        return (None, None)

    # canonical label -> list of patterns to look for (matched with boundaries)
    TECH_TERMS = [
        "python", "java", "javascript", "typescript", "node.js", "react native",
        "react", "angular", "vue", "ruby on rails", "ruby", "rails", "golang",
        "rust", "c++", "c#", ".net", "scala", "kotlin", "swift", "php", "elixir",
        "kubernetes", "docker", "terraform", "aws", "azure", "gcp", "google cloud",
        "graphql", "grpc", "kafka", "spark", "airflow", "snowflake",
        "postgresql", "postgres", "mysql", "mongodb", "redis", "dynamodb", "nosql",
        "sql", "elasticsearch", "microservices", "ci/cd", "machine learning",
        "genai", "llm", "llms", "pytorch", "tensorflow", "data warehouse", "etl",
        "dbt", "sagemaker", "linux", "bigquery", "hadoop", "pandas", "numpy",
        "infrastructure-as-code", "devops", "sre", "observability", "ml platform",
        "kubernetes", "rest api", "restful",
    ]

    def _tech(text):
        if not text:
            return []
        low = text.lower()
        found = []
        for term in TECH_TERMS:
            # boundary that treats +, #, . as part of the token (not word chars)
            pat = r"(?<![a-z0-9+#.])" + re.escape(term) + r"(?![a-z0-9+#])"
            try:
                if re.search(pat, low):
                    label = term
                    if label not in found:
                        found.append(label)
            except Exception:
                continue
        return found[:25]

    # department/title based gate for "tech / software only"
    TECH_DEPTS = {"tech development", "product", "it", "data", "engineering",
                  "r&d", "research & development"}
    TECH_TITLE_HINTS = ("engineer", "developer", "software", "devops", "sre",
                        "data ", "data scientist", "machine learning", "ml ",
                        " ai", "ai ", "backend", "back-end", "frontend", "front-end",
                        "full stack", "full-stack", "fullstack", "architect",
                        "infrastructure", "platform", "security", "qa ",
                        "product manager", "product designer", "technical",
                        "analytics", "database", "cloud")
    NON_TECH_TITLE = ("marketing", "brand", "sales", "recruit", "people ops",
                      "finance", "legal", "counsel", "actuar", "compliance",
                      "insurance pricing", "biz ", "bizops")

    def _is_tech(dept, title):
        d = (dept or "").strip().lower()
        t = (title or "").strip().lower()
        strong = ("engineer", "developer", "software", "data ", "machine learning",
                  "platform", "devops", "sre", "architect")
        if any(h in t for h in NON_TECH_TITLE) and not any(h in t for h in strong):
            return False
        if d in TECH_DEPTS:
            return True
        if any(h in t for h in TECH_TITLE_HINTS):
            return True
        return False

    def _fetch(url):
        try:
            r = requests.get(url, headers=HEADERS, timeout=25)
            if r.status_code == 200 and r.content:
                r.encoding = "utf-8"  # page is utf-8; header omits charset
                return r.text
        except Exception:
            return None
        return None

    def _extract_recipes(html):
        if not html:
            return []
        blob = None
        # 1) proper parse of the __NEXT_DATA__ script via bs4
        try:
            if BeautifulSoup is not None:
                soup = BeautifulSoup(html, "lxml")
                tag = soup.find("script", id="__NEXT_DATA__")
                if tag and tag.string:
                    blob = tag.string
        except Exception:
            blob = None
        # 2) regex fallback
        if not blob:
            try:
                m = re.search(
                    r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>',
                    html, re.S)
                if m:
                    blob = m.group(1)
            except Exception:
                blob = None
        if not blob:
            return []
        try:
            data = json.loads(blob)
        except Exception:
            return []
        try:
            rec = data.get("props", {}).get("pageProps", {}).get("allRecipes")
            if isinstance(rec, list):
                return rec
        except Exception:
            pass
        # deep fallback: hunt for a list of dicts that look like roles
        found = []
        def walk(o):
            if found:
                return
            if isinstance(o, list):
                if o and isinstance(o[0], dict) and "link" in o[0] and (
                        "location" in o[0] or "department" in o[0]):
                    found.append(o)
                    return
                for v in o:
                    walk(v)
            elif isinstance(o, dict):
                for v in o.values():
                    walk(v)
        try:
            walk(data)
        except Exception:
            pass
        return found[0] if found else []

    # ---- main --------------------------------------------------------------
    results = []
    try:
        recipes = []
        for url in ("https://makers.lemonade.com/careers",
                    "https://makers.lemonade.com/"):
            html = _fetch(url)
            recipes = _extract_recipes(html)
            if recipes:
                break
            time.sleep(random.uniform(0.6, 1.2))

        # newest / display order first when an order key exists
        try:
            recipes = sorted(recipes, key=lambda x: x.get("order", 1e9))
        except Exception:
            pass

        seen = set()
        for j in recipes:
            try:
                loc = str(j.get("location") or "")
                low_loc = loc.lower()
                if "israel" not in low_loc and "tel aviv" not in low_loc:
                    continue
                title = (j.get("title") or "").strip()
                dept = (j.get("department") or "").strip()
                if not title:
                    continue
                if not _is_tech(dept, title):
                    continue

                sid = str(j.get("postingId") or j.get("id") or j.get("slug") or "").strip()
                if sid and sid in seen:
                    continue
                if sid:
                    seen.add(sid)

                url = (j.get("link") or "").strip()
                if not url and j.get("slug"):
                    url = "https://makers.lemonade.com/role/" + str(j["slug"])

                desc = _html_to_text(j.get("content") or "")
                city = loc.split(",")[0].strip() if loc else ""
                ymin, ymax = _years(desc)

                results.append({
                    "source": "lemonade",
                    "sid": sid,
                    "title": title,
                    "company": "Lemonade",
                    "city": city or "Tel Aviv",
                    "url": url,
                    "level": _level(title),
                    "years_min": ymin,
                    "years_max": ymax,
                    "tech": _tech(desc),
                    "desc": desc[:4000],
                    "active": True,
                })
                if len(results) >= 120:
                    break
            except Exception:
                continue
    except Exception:
        return results
    return results
