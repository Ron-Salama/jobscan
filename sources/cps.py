# -*- coding: utf-8 -*-
"""CPS (cps.co.il) - Israeli hi-tech staffing agency, read via its job sitemap.

Not registered in jobscan._EXT_NAMES (disabled 2026-09-23: broken links + no JD).
"""


def src_cps():
    """CPS (cps.co.il) - Israeli hi-tech staffing agency.
    Detail bodies are JS-rendered, but job-sitemap.xml lists every /job/{slug}/ URL + <lastmod>,
    and each job page ships the real title in its server-rendered <title>. We take the newest
    ~120 by lastmod and fetch each title. company/city/desc are JS-only -> "".
    Resilient: never raises; returns whatever it got.
    """
    import re, html, time, requests
    from bs4 import BeautifulSoup

    MAX = 120
    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")
    H = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,application/xml"}
    out = []

    # --- 1) sitemap: collect (lastmod, url, slug) ---
    entries = []
    try:
        r = requests.get("https://www.cps.co.il/job-sitemap.xml", headers=H, timeout=30)
        soup = BeautifulSoup(r.text, "lxml-xml")
        for u in soup.find_all("url"):
            loc = u.find("loc")
            if not loc:
                continue
            url = loc.text.strip()
            path = url.rstrip("/")
            if not re.search(r"/job/[^/]+$", path):   # skip the /job/ index page
                continue
            slug = path.rsplit("/", 1)[-1]
            lm = u.find("lastmod")
            entries.append(((lm.text.strip() if lm else ""), url, slug))
    except Exception as e:
        print("  cps sitemap err %s" % e)
        return out

    entries.sort(key=lambda x: x[0], reverse=True)   # newest lastmod first
    entries = entries[:MAX]

    # --- 2) fetch each job page for its server-rendered <title> ---
    for lm, url, slug in entries:
        title = ""
        try:
            jr = requests.get(url, headers=H, timeout=20)
            m = re.search(r"<title[^>]*>(.*?)</title>", jr.text, re.S | re.I)
            if m:
                title = html.unescape(m.group(1)).strip()
                # strip a trailing site-name suffix if the theme ever adds one
                title = re.sub(r"\s*[\|\-–—»]\s*CPS\b.*$", "", title, flags=re.I).strip()
        except Exception as e:
            print("  cps job err %s (%s)" % (e, slug))
            time.sleep(0.2)
            continue
        if not title:
            time.sleep(0.2)
            continue

        tl = title.lower()
        # best-effort seniority from title (EN + HE)
        if any(w in tl for w in ("student", "intern", "סטודנט", "מתמחה")):
            level = "student"
        elif any(w in tl for w in ("senior", "sr.", "sr ", "lead", "principal", "staff",
                                   "בכיר", "מנוסה",
                                   "ראש צוות", "team lead")):
            level = "senior"
        elif any(w in tl for w in ("junior", "jr.", "jr ", "entry",
                                   "ג'וניור", "גוניור",
                                   "מתחיל")):
            level = "junior"
        else:
            level = ""

        # best-effort tech tags from title
        TECH = ["python", "java", "javascript", "typescript", "c++", "c#", ".net", "golang",
                "go ", "rust", "php", "node", "react", "angular", "vue", "fullstack",
                "full stack", "full-stack", "backend", "frontend", "front end", "front-end",
                "devops", "kubernetes", "docker", "aws", "azure", "gcp", "sql", "embedded",
                "firmware", "verilog", "vlsi", "fpga", "ios", "android", "mobile", "qa",
                "automation", "data", "ml", "ai", "llm", "algorithm", "web", "cloud"]
        tech = sorted({t.strip() for t in TECH if t in tl})

        out.append({
            "source": "cps",
            "sid": slug,
            "title": title,
            "company": "",   # masked / JS-only
            "city": "",      # JS-only
            "url": url,
            "level": level,
            "years_min": None,
            "years_max": None,
            "tech": tech,
            "desc": "",      # JS-only
            "active": True,
        })
        time.sleep(0.25)

    return out
