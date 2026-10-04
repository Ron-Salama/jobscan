# -*- coding: utf-8 -*-
"""Built In (builtin.com) - Israel job board.

HTML scraper: every field is on the server-rendered listing card.
"""

import re
import time

import requests
from bs4 import BeautifulSoup


def src_builtin():
    """Built In (builtin.com) Israel board -> normalized job dicts.
    Newest ~4 listing pages of https://builtin.com/jobs/mena/israel?page=N .
    Everything (sid, title, url, company, city, level, tech, desc) is on the
    server-rendered listing card, so no per-job detail fetch is needed."""
    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
    BASE = "https://builtin.com"
    LIST = BASE + "/jobs/mena/israel?page=%d"
    MAX_PAGES = 4          # newest N pages only (daily run stays fast; caller dedups)
    CAP = 120

    sess = requests.Session()
    sess.headers.update({"User-Agent": UA,
                         "Accept": "text/html,application/xhtml+xml"})

    def _label(card, icon_cls):
        # BuiltIn puts the value text in the grandparent div of the fa-* icon.
        i = card.select_one("i.%s" % icon_cls)
        if not i or not i.parent or not i.parent.parent:
            return ""
        return i.parent.parent.get_text(" ", strip=True)

    def _level(txt):
        t = (txt or "").lower()
        if any(w in t for w in ("intern", "student")):        return "student"
        if any(w in t for w in ("entry", "junior", "associate")): return "junior"
        if "senior" in t or "principal" in t or "staff" in t or "lead" in t: return "senior"
        return ""   # "Mid level" / unknown -> caller decides

    def _city(txt):
        c = (txt or "").strip()
        c = re.sub(r",?\s*(ISR|Israel|IL)\s*$", "", c, flags=re.I).strip(" ,")
        if c.upper() in ("", "IL", "ISR", "ISRAEL"):
            return "Israel" if txt else ""
        return c

    out, seen_sid = [], set()
    for pg in range(1, MAX_PAGES + 1):
        try:
            r = sess.get(LIST % pg, timeout=30)
            if r.status_code != 200:
                break
            soup = BeautifulSoup(r.text, "lxml")
        except Exception:
            break
        cards = soup.select("div.job-bounded-responsive")
        if not cards:                       # ran past the last page
            break
        for c in cards:
            try:
                a = c.select_one("a[href*='/job/']")
                if not a:
                    continue
                href = a.get("href") or ""
                m = re.search(r"/job/[^/]+/(\d+)", href)
                if not m:
                    continue
                sid = m.group(1)
                if sid in seen_sid:
                    continue
                seen_sid.add(sid)
                title = a.get_text(" ", strip=True)
                url = href if href.startswith("http") else BASE + href

                company = ""
                for ca in c.select("a[href*='/company/']"):
                    t = ca.get_text(" ", strip=True)
                    if t:
                        company = t
                        break

                city = _city(_label(c, "fa-location-dot"))
                level = _level(_label(c, "fa-trophy") or title)

                tech, desc = [], ""
                drop = c.select_one("[data-job-id]")
                if drop:
                    tech = [s.get_text(strip=True) for s in drop.select("span.mx-sm")
                            if s.get_text(strip=True)]
                    tech = list(dict.fromkeys(tech))[:25]
                    d = (drop.select_one("div.fs-sm.text-gray-04")
                         or drop.select_one("div.fs-sm"))
                    if d:
                        desc = d.get_text(" ", strip=True)
                if not level:
                    level = _level(title)

                out.append({
                    "source": "builtin", "sid": sid, "title": title,
                    "company": company, "city": city, "url": url,
                    "level": level, "years_min": None, "years_max": None,
                    "tech": tech, "desc": desc, "active": True,
                })
                if len(out) >= CAP:
                    return out
            except Exception:
                continue
        time.sleep(0.3)
    return out
