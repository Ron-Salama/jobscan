# -*- coding: utf-8 -*-
"""Dialog (dialog.co.il) - Israeli high-tech job board.

HTML scraper: newest listing pages of each software/data/QA/system category, each
category with its own page budget.
"""

from ._common import _is_student_title


def src_dialog():
    """Dialog (dialog.co.il) Israeli high-tech job board. Server-rendered HTML.
    Scrapes the newest MAX_PAGES listing pages of EACH software/data/qa/system category
    (per-category budget; no global cap, so the later categories are always requested).
    sid = positionId. company is not published on the board, so it is returned "".
    Never raises; returns whatever it managed to collect."""
    import re, time
    import requests
    from bs4 import BeautifulSoup

    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
    HEADERS = {"User-Agent": UA,
               "Accept": "text/html,application/xhtml+xml",
               "Accept-Language": "he-IL,he;q=0.9,en;q=0.8"}
    BASE = "https://www.dialog.co.il"
    CATS = ("software", "data", "qa", "system")
    MAX_PAGES = 3      # per category (newest first); stops early on an empty/repeated page

    TECH_KW = [
        "python", "java", "javascript", "typescript", "react", "angular", "vue",
        "node", "node.js", "c++", "c#", ".net", "go", "golang", "rust", "kotlin",
        "swift", "php", "ruby", "scala", "sql", "nosql", "mongodb", "postgres",
        "mysql", "redis", "kafka", "spark", "hadoop", "aws", "azure", "gcp",
        "docker", "kubernetes", "k8s", "terraform", "jenkins", "ci/cd", "linux",
        "embedded", "firmware", "rtos", "verilog", "vhdl", "matlab", "django",
        "flask", "fastapi", "spring", "graphql", "rest", "microservices",
        "selenium", "cypress", "playwright", "pytest", "appium", "jmeter",
        "tensorflow", "pytorch", "llm", "genai", "nlp", "airflow", "snowflake",
        "databricks", "elasticsearch", "devops", "ansible", "bash", "powershell",
    ]

    def txt(el):
        return re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip() if el else ""

    def parse_years(s):
        s = (s or "").lower()
        nums = re.findall(r'(\d+)\s*\+?\s*(?:years?|yrs?|שנ)', s)  # שנ = "shan" (year)
        nums = [int(x) for x in nums if int(x) <= 25]
        if not nums:
            return None, None
        rng = re.search(r'(\d+)\s*[-–]\s*(\d+)\s*(?:years?|yrs?|שנ)', s)
        if rng:
            a, b = int(rng.group(1)), int(rng.group(2))
            return min(a, b), max(a, b)
        return min(nums), (max(nums) if len(nums) > 1 else None)

    def level_of(title, blob):
        # student: TITLE only, word-bound (the company blurb "המתמחה בפיתוח" means
        # "that specializes in development" and made 14/18 false 'student' labels)
        if _is_student_title(title):
            return "student"
        # SENIOR from the TITLE only: on the JD/blurb 'lead' hit 'leading', 'architect' hit
        # 'architectures', 'expert' hit 'expertise' (review 2026-09-24); the blurb still
        # counts for junior
        tl = (title or "").lower()
        t = (title + " " + blob).lower()
        if any(w in tl for w in ("senior", "sr.", "lead", "principal", "staff",
                                 "architect", "בכיר",
                                 "team lead", "expert", "מנוסה")):
            return "senior"
        if any(w in t for w in ("junior", "jr.", "entry level", "entry-level", "גוניור",   # not bare 'entry' (Sentry, data entry)
                                "זוטר",
                                "ללא ניסיון")):
            return "junior"
        return ""

    def tech_of(skills_ul, blob):
        found = []
        if skills_ul:
            for li in skills_ul.select("li"):
                s = txt(li)
                if s:
                    found.append(s)
        if not found:
            low = blob.lower()
            for kw in TECH_KW:
                if re.search(r'(?<![a-z0-9])' + re.escape(kw) + r'(?![a-z0-9+#.])', low) \
                   or (kw in ("c++", "c#", ".net", "node.js", "ci/cd", "k8s") and kw in low):
                    found.append(kw)
        seen = set(); uniq = []
        for x in found:
            k = x.lower()
            if k not in seen:
                seen.add(k); uniq.append(x)
        return uniq[:15]

    out = []
    seen_ids = set()
    try:
        sess = requests.Session()
        sess.headers.update(HEADERS)
    except Exception:
        sess = None

    per_cat = {}
    for cat in CATS:
        n_cat = 0
        prev_pids = None
        for page in range(1, MAX_PAGES + 1):
            url = "%s/high-tech/jobs/%s/?page=%d" % (BASE, cat, page)
            try:
                if sess is not None:
                    r = sess.get(url, timeout=30)
                else:
                    r = requests.get(url, headers=HEADERS, timeout=30)
                if r.status_code != 200:
                    continue
                r.encoding = "utf-8"
                soup = BeautifulSoup(r.text, "lxml")
            except Exception:
                continue

            cards = soup.select("div.item_job")
            if not cards:
                break
            n_before = len(out)
            page_pids = []
            for card in cards:
                try:
                    a = card.select_one("h3.title_job a")
                    title = txt(card.select_one("h3.title_job")) or txt(a)
                    href = a.get("href", "") if a else ""

                    pid = ""
                    m = re.search(r'positionId=(\d+)', href)
                    if m:
                        pid = m.group(1)
                    if not pid:
                        btn = card.select_one("[data-positionid]")
                        if btn and btn.get("data-positionid"):
                            pid = re.sub(r"\D", "", btn["data-positionid"])
                    if not pid:
                        sp = card.select_one("span.positionId")
                        if sp:
                            dm = re.search(r'(\d+)', txt(sp))
                            if dm:
                                pid = dm.group(1)
                    if pid:
                        page_pids.append(pid)
                    if not pid or pid in seen_ids:
                        continue
                    seen_ids.add(pid)

                    link = "%s/high-tech/jobs/jobpage?positionId=%s" % (BASE, pid)

                    city = ""
                    loc_icon = card.select_one("span.icon-location")
                    if loc_icon and loc_icon.parent:
                        city = txt(loc_icon.parent)
                    if not city:
                        li_loc = card.select_one("ul.job_info li a")
                        if li_loc:
                            city = txt(li_loc)

                    desc_top = txt(card.select_one("div.right div.top div.desc"))
                    reqs = txt(card.select_one("div.req_list"))
                    reqs = re.sub(r'^מה צריך:\s*', '', reqs)  # strip "ma tsarich:" label
                    on_comp = txt(card.select_one("div.on_comp"))
                    full_desc = " | ".join(x for x in (desc_top, reqs) if x)
                    blob = " ".join(x for x in (title, desc_top, reqs, on_comp) if x)

                    ymin, ymax = parse_years(reqs + " " + desc_top)
                    lvl = level_of(title, blob)
                    if lvl == "junior" and ymin is None:
                        ymax = 2
                    tech = tech_of(card.select_one("ul.skills_list"), blob)

                    out.append({
                        "source": "dialog",
                        "sid": pid,
                        "title": title,
                        "company": "",
                        "city": city,
                        "url": link,
                        "level": lvl,
                        "years_min": ymin,
                        "years_max": ymax,
                        "tech": tech,
                        "desc": full_desc[:1200],
                        "active": True,
                    })
                except Exception:
                    continue
            n_cat += len(out) - n_before
            time.sleep(0.3)
            # past the last page (empty, or a repeat of the previous one) -> next category.
            # A page whose ids were all seen in an earlier category keeps paging.
            if not page_pids or page_pids == prev_pids:
                break
            prev_pids = page_pids
        per_cat[cat] = n_cat
    try:
        print("    dialog per-category:", per_cat)
    except Exception:
        pass
    return out
