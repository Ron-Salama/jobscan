# -*- coding: utf-8 -*-
"""Kaltura careers lobby (corp.kaltura.com) + each role's own page.

Not registered in jobscan._EXT_NAMES (unplugged 2026-09-28: 0 rows for 27 runs).
"""

import re
import time

import requests
from bs4 import BeautifulSoup

from ._common import _is_student_title


def src_kaltura():
    """
    Kaltura careers adapter -> corp.kaltura.com/company/careers/

    The careers "lobby" ships every open role in the static HTML as
    <a class="b-new-careers-lobby__job" data-title=.. data-department=..
    data-location=.. href="/careers/{slug}/{code}/"> (country in data-location,
    city in the .job-location text, code = last URL path segment). We keep the
    Israel rows and enrich each from its own role page. Every Kaltura JD opens
    with ~1,400 chars of identical company boilerplate ("This is us ... 15+ years
    since starting the company"), so description/tech/years are parsed only from
    the role-specific text after that preamble. Returns a list of job dicts;
    never raises.
    """
    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
    HDRS = {"User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9"}
    # full navigate-style browser headers for the retry (CI runners get 0 rows while a
    # desktop gets ~17; a bot filter keyed on the bare header set is the usual cause)
    FULL_HDRS = {
        "User-Agent": UA,
        "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
                   "image/avif,image/webp,image/apng,*/*;q=0.8"),
        "Accept-Language": "en-US,en;q=0.9,he;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Cache-Control": "max-age=0",
    }
    BASE = "https://corp.kaltura.com"
    LIST = BASE + "/company/careers/"
    CAP = 120
    out = []

    def _log(msg):
        try:
            print("    kaltura " + msg)
        except Exception:
            pass

    def _get(url, timeout=25, headers=None):
        r = requests.get(url, headers=headers or HDRS, timeout=timeout, allow_redirects=True)
        # page is UTF-8; guard against requests guessing latin-1 (would mojibake)
        if not r.encoding or r.encoding.lower() in ("iso-8859-1", "latin-1"):
            r.encoding = r.apparent_encoding or "utf-8"
        return r

    def _list_anchors(headers, label):
        """-> (anchors, status/exception text). Never raises."""
        try:
            r = _get(LIST, headers=headers)
        except Exception as e:
            return [], "%s: EXC %s" % (label, type(e).__name__)
        if r.status_code != 200:
            return [], "%s: HTTP %s (%d bytes)" % (label, r.status_code, len(r.content or b""))
        try:
            soup = BeautifulSoup(r.text, "lxml")
            anchors = soup.select("a.b-new-careers-lobby__job")
            if not anchors:
                # fallback: any anchor carrying the job data-attrs
                anchors = [a for a in soup.find_all("a", href=True) if a.get("data-title")]
        except Exception as e:
            return [], "%s: parse EXC %s" % (label, type(e).__name__)
        return anchors, "%s: HTTP 200, %d job anchors (%d bytes)" % (
            label, len(anchors), len(r.content or b""))

    def _role_text(full):
        # drop the leading identical company boilerplate; keep from the first
        # real role/section header onward.
        tl = full.lower()
        heads = ["the role", "about the role", "what you'll do", "what you will do",
                 "the opportunity", "responsibilities", "your impact", "who you are",
                 "what you'll bring", "you bring", "qualifications"]
        pos = [tl.find(h) for h in heads if tl.find(h) != -1]
        idx = min(pos) if pos else -1
        return full[idx:] if idx > 0 else full

    def _level(title):
        t = (title or "").lower()
        if _is_student_title(title):     # word-bound: 'intern' must not hit "Internal ..."
            return "student"
        if any(w in t for w in ("senior", "sr.", "sr ", " lead", "lead ", "principal",
                                "staff", "architect", "manager", "head of", "director",
                                "team lead", "expert", " vp", "vp ", "chief")):
            return "senior"
        if any(w in t for w in ("junior", "jr.", "jr ", "entry", "graduate")):
            return "junior"
        return ""

    def _years(text):
        # role text only; still guard the stock "N years since starting" phrasing.
        t = (text or "").lower().replace("–", "-").replace("—", "-")
        ymin = ymax = None
        m = re.search(r'(\d{1,2})\s*\+?\s*(?:-|to|up to)\s*(\d{1,2})\s*\+?\s*(?:years|yrs|year)', t)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if max(a, b) <= 30:
                ymin, ymax = min(a, b), max(a, b)
        got = []
        for mm in re.finditer(r'(\d{1,2})\s*\+?\s*(?:years|yrs|year)\s*(?P<after>.{0,15})', t):
            after = mm.group("after")
            if "since" in after or "ago" in after:
                continue
            n = int(mm.group(1))
            if n <= 30:
                got.append(n)
        if got and ymin is None:
            ymin = min(got)
        return ymin, ymax

    # bare "go"/"video" excluded: "go-to-market"/"go live" and Kaltura's whole
    # video domain match every role and carry no signal. "golang" catches real Go.
    TECHKW = ["python", "c++", "c#", ".net", "java", "javascript", "typescript",
              "react", "angular", "vue", "node", "sql", "nosql", "mongodb", "redis",
              "postgres", "mysql", "aws", "azure", "gcp", "docker", "kubernetes",
              "k8s", "terraform", "ansible", "pytorch", "tensorflow",
              "machine learning", "deep learning", "ml", "ai", "llm", "genai",
              "nlp", "rag", "computer vision", "linux", "golang", "rust", "php",
              "ruby", "scala", "kotlin", "swift", "graphql", "rest", "grpc",
              "microservices", "kafka", "rabbitmq", "spark", "elasticsearch",
              "algorithms", "devops", "ci/cd", "sre", "qa", "automation",
              "selenium", "cypress", "playwright", "webrtc", "streaming", "html",
              "css", "netsuite", "salesforce", "prometheus", "grafana"]

    def _tech(text):
        t = " " + (text or "").lower() + " "
        found = []
        for k in TECHKW:
            # boundary match so "ai" != "email", "go" != "google", etc.
            if re.search(r'(?<![a-z0-9])' + re.escape(k) + r'(?![a-z0-9])', t):
                if k not in found:
                    found.append(k)
        return found[:15]

    no_jd = 0
    try:
        use_hdrs = HDRS
        anchors, note = _list_anchors(HDRS, "list")
        if not anchors:
            # one retry with the full browser header set (after a short pause)
            time.sleep(2.0)
            use_hdrs = FULL_HDRS
            anchors, note2 = _list_anchors(FULL_HDRS, "retry(full headers)")
            note = note + " | " + note2
        _log(note)

        for a in anchors:
            if len(out) >= CAP:
                break
            try:
                country = (a.get("data-location") or "").strip()
                if "israel" not in country.lower():
                    continue

                href = (a.get("href") or "").strip()
                if not href:
                    continue
                if href.startswith("/"):
                    href = BASE + href
                sid = href.rstrip("/").rsplit("/", 1)[-1]

                title = (a.get("data-title") or "").strip()
                if not title:
                    tn = a.select_one(".b-new-careers-lobby__job-name")
                    title = tn.get_text(" ", strip=True) if tn else ""
                if not title:
                    continue

                loc_el = a.select_one(".b-new-careers-lobby__job-location")
                city = loc_el.get_text(" ", strip=True) if loc_el else ""
                if not city:
                    city = country  # fall back to "Israel"

                # enrich from the role page (small list -> cheap); one retry on flakiness
                full = ""
                for _attempt in range(2):
                    try:
                        d = _get(href, timeout=20, headers=use_hdrs)
                        if d.status_code == 200:
                            ds = BeautifulSoup(d.text, "lxml")
                            art = (ds.select_one("div.b-new-career-inner__content")
                                   or ds.select_one(".b-new-career-inner__content-texts")
                                   or ds.select_one("article"))
                            if art:
                                txt = art.get_text(" ", strip=True)
                                txt = re.sub(r'^\s*Back to jobs\s*', '', txt)
                                full = re.sub(r'\s+', ' ', txt)
                        time.sleep(0.3)
                        if full:
                            break
                    except Exception:
                        time.sleep(0.5)

                if not full:
                    no_jd += 1
                role = _role_text(full)
                desc = role[:2500]
                ymin, ymax = _years(role)
                out.append({
                    "source": "kaltura",
                    "sid": sid,
                    "title": title,
                    "company": "Kaltura",
                    "city": city,
                    "url": href,
                    "level": _level(title),
                    "years_min": ymin,
                    "years_max": ymax,
                    "tech": _tech(title + " " + role),
                    "desc": desc,
                    "active": True,
                })
            except Exception:
                continue
    except Exception as e:
        _log("ERROR %s" % e)

    _log("%d Israel rows (%d without JD)" % (len(out), no_jd))
    return out
