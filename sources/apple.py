# -*- coding: utf-8 -*-
"""Apple careers (jobs.apple.com) - Israel tech/software roles.

Reads the job records from the server-rendered hydration JSON; a bs4 card scraper is
the fallback.
"""

from ._common import _is_student_title


def src_apple():
    """Apple careers -> Israel tech/software roles (jobs.apple.com).

    Israel is selected via the public search route ?location=israel-ISR (the
    /en-il/ prefix is only display locale, NOT a country filter). Apple's site is
    a React app that server-renders each page with the full result set embedded in
    `window.__staticRouterHydrationData = JSON.parse("...")`; we pull the newest few
    pages, extract that JSON, and read the job records straight out of it (no CSRF /
    POST needed). bs4 fallback scrapes the rendered cards if the blob ever moves.
    """
    import re, json, time, html as _html
    import requests
    from bs4 import BeautifulSoup

    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
    BASE = "https://jobs.apple.com"
    SEARCH = BASE + "/en-il/search?location=israel-ISR&sort=newest&page=%d"
    PAGE_SIZE = 20
    MAX_PAGES = 15         # hard ceiling; the real page count is ceil(totalRecords/20)+1
    FALLBACK_PAGES = 6     # used only if page 1 carries no totalRecords
    CAP = 300

    SENIOR = ("senior", "sr.", "sr ", " lead", "lead ", "principal", "staff",
              "architect", "manager", "head of", "director", "chief", " vp", "expert")
    JUNIOR = ("junior", "jr.", "jr ", "entry", "associate", "new grad",
              "new-grad", "graduate")
    TECH_KW = ["python", "java", "javascript", "typescript", "c++", "c#", "swift",
               "objective-c", "kotlin", "go ", "golang", "rust", "scala", "ruby",
               ".net", "node", "react", "angular", "vue", "django", "flask",
               "spring", "kubernetes", "docker", "aws", "gcp", "azure", "sql",
               "nosql", "spark", "kafka", "linux", "embedded", "firmware", "rtos",
               "verilog", "systemverilog", "machine learning", "deep learning",
               "pytorch", "tensorflow", "llm", "genai", "nlp", "computer vision",
               "devops", "ci/cd", "graphql", "rest", "microservices", "wifi",
               "bluetooth", "silicon", "soc", "fpga", "matlab"]

    s = requests.Session()
    s.headers.update({"User-Agent": UA,
                      "Accept": "text/html,application/xhtml+xml",
                      "Accept-Language": "en-US,en;q=0.9"})

    def level_of(title):
        t = " " + (title or "").lower() + " "
        if _is_student_title(title) or any(w in t for w in ("working student", "co op")):
            return "student"     # word-bound: 'intern' must not hit "Internal ..."
        if any(w in t for w in SENIOR):
            return "senior"
        if any(w in t for w in JUNIOR):
            return "junior"
        return ""

    def years_of(text):
        t = (text or "").lower()
        mn = mx = None
        m = re.search(r'(\d{1,2})\s*(?:-|to|–)\s*(\d{1,2})\s*\+?\s*years?', t)
        if m:
            mn, mx = int(m.group(1)), int(m.group(2))
        else:
            m = re.search(r'(\d{1,2})\s*\+\s*years?', t)
            if m:
                mn = int(m.group(1))
            else:
                m = re.search(r'(\d{1,2})\s*years?', t)
                if m:
                    mn = int(m.group(1))
        if mn is not None and mn > 30:
            mn = None
        if mx is not None and mx > 40:
            mx = None
        return mn, mx

    def tech_of(text):
        t = (text or "").lower()
        seen = set(); out = []
        for kw in TECH_KW:
            k = kw.strip()
            if k in seen:
                continue
            if re.fullmatch(r'[a-z0-9 ]+', k):     # wordy kw -> word-boundary match
                hit = re.search(r'(?<![a-z0-9])' + re.escape(k) + r'(?![a-z0-9])', t)
            else:                                   # symbol kw (c++, c#, .net) -> substring
                hit = k in t
            if hit:
                seen.add(k); out.append(k)
        return out[:12]

    def parse_hydration(page_html):
        """-> (searchResults list or None, totalRecords int or None)"""
        m = re.search(r'window\.__staticRouterHydrationData\s*=\s*JSON\.parse\("(.*?)"\);',
                      page_html, re.S)
        if not m:
            return None, None
        try:
            data = json.loads(json.loads('"' + m.group(1) + '"'))
        except Exception:
            return None, None
        try:
            srch = data["loaderData"]["search"]
        except Exception:
            return None, None
        total = srch.get("totalRecords") if isinstance(srch, dict) else None
        try:
            total = int(total) if total is not None else None
        except Exception:
            total = None
        try:
            return srch["searchResults"], total
        except Exception:
            return None, total

    def rec_to_job(rec):
        try:
            pid = str(rec.get("positionId") or rec.get("id") or "")
            if not pid:
                return None
            title = (rec.get("postingTitle") or rec.get("transformedPostingTitle") or "").strip()
            locs = rec.get("locations") or []
            city = ""
            for l in locs:
                if not isinstance(l, dict):
                    continue
                c = (l.get("city") or "").strip()
                if not c:
                    nm = (l.get("name") or "").strip()
                    # skip bare country names, keep city-like names
                    c = "" if nm.lower() in ("israel", "") else nm
                if c:
                    city = c
                    break
            slug = rec.get("transformedPostingTitle") or ""
            url = "%s/en-il/details/%s%s" % (BASE, pid, ("/" + slug if slug else ""))
            desc = _html.unescape((rec.get("jobSummary") or "").strip())
            team = ((rec.get("team") or {}).get("teamName") or "").strip()
            blob = title + " \n " + desc + " \n " + team
            ymin, ymax = years_of(desc)
            return {
                "source": "apple",
                "sid": pid,
                "title": title,
                "company": "Apple",
                "city": city,
                "url": url,
                "level": level_of(title),
                "years_min": ymin,
                "years_max": ymax,
                "tech": tech_of(blob),
                "desc": desc,
                "active": True,
            }
        except Exception:
            return None

    def scrape_cards(page_html):
        """bs4 fallback: read visible result cards if the hydration blob is gone."""
        out = []
        try:
            soup = BeautifulSoup(page_html, "lxml")
        except Exception:
            return out
        for a in soup.select('a[href*="/details/"]'):
            href = a.get("href") or ""
            m = re.search(r'/details/(\d+)(?:/([^/?#]+))?', href)
            if not m:
                continue
            pid, slug = m.group(1), (m.group(2) or "")
            title = a.get_text(" ", strip=True)
            if not title:
                continue
            url = href if href.startswith("http") else BASE + href
            out.append({
                "source": "apple", "sid": pid, "title": title, "company": "Apple",
                "city": "", "url": url, "level": level_of(title),
                "years_min": None, "years_max": None, "tech": tech_of(title),
                "desc": "", "active": True,
            })
        return out

    def fetch_page(pg):
        """-> (page_jobs, totalRecords or None). Never raises."""
        try:
            r = s.get(SEARCH % pg, timeout=30)
            r.encoding = "utf-8"
            page_html = r.text
        except Exception:
            return [], None
        recs, total = parse_hydration(page_html)
        page_jobs = []
        if recs:
            for rec in recs:
                j = rec_to_job(rec)
                if j:
                    page_jobs.append(j)
        else:
            page_jobs = scrape_cards(page_html)
        return page_jobs, total

    # Page count comes from page 1's totalRecords (Israel had 110 = 6 pages when the old
    # fixed MAX_PAGES=5 cut it). Apple randomly serves ~25-40% of page loads EMPTY
    # (totalRecords=0; measured live 2026-09-24, any page, any session). Such a page is
    # retried with backoff, skipped if it stays empty, and retried again after the main
    # pass - it no longer ends the whole run at ~15 roles (audit BUG 21).
    RETRIES = 4
    jobs = []
    seen_ids = set()

    def add(page_jobs):
        new = 0
        for j in page_jobs:
            if j["sid"] in seen_ids:
                continue
            seen_ids.add(j["sid"])
            jobs.append(j)
            new += 1
        return new

    total_records = None
    last_page = FALLBACK_PAGES
    pg = 1
    empty_pages = []
    while pg <= min(last_page, MAX_PAGES) and len(jobs) < CAP:
        expected = pg == 1 or pg < last_page   # the +1 page past the end may be empty
        page_jobs, total = fetch_page(pg)
        tries = 0
        while not page_jobs and expected and tries < RETRIES:
            tries += 1
            time.sleep(1.0 * tries)
            page_jobs, total = fetch_page(pg)
        if total_records is None and total:
            total_records = total
            last_page = min(MAX_PAGES, -(-total_records // PAGE_SIZE) + 1)
        if not page_jobs:
            if pg == 1:                 # page 1 empty after retries -> site down/blocked
                break
            if pg < last_page:
                empty_pages.append(pg)
        new = add(page_jobs)
        # no totalRecords known and nothing new -> past the end
        if total_records is None and new == 0 and pg > 1:
            break
        pg += 1
        time.sleep(0.35)
    # second pass over pages that stayed empty
    still_empty = []
    for epg in empty_pages:
        page_jobs = []
        for tries in range(3):
            time.sleep(2.0)
            page_jobs, _ = fetch_page(epg)
            if page_jobs:
                break
        if page_jobs:
            add(page_jobs)
        else:
            still_empty.append(epg)
    jobs = jobs[:CAP]
    try:
        print("    apple: totalRecords %s, pages %d, fetched %d%s"
              % (total_records, min(last_page, MAX_PAGES), len(jobs),
                 (", pages still EMPTY after retries %s" % still_empty) if still_empty else ""))
    except Exception:
        pass
    return jobs
