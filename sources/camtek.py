# -*- coding: utf-8 -*-
"""Camtek careers adapter (+ best-effort bonus: PwC Israel).
"""

import re
import time

import requests
from bs4 import BeautifulSoup


def src_camtek():
    """
    Camtek careers adapter (+ best-effort bonus: PwC Israel).
    Palo Alto Networks moved to src_workday 2026-09-24 (tenant paloaltonetworks /
    panwexternalcareers, Israel location facet = every IL posting incl. CyberArk);
    the old Phenom keyword search here saw 14 of ~150 Israel rows.
    Each company has its own cap. Returns a list of normalized job dicts. Never raises.
    """
    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
    HDRS = {"User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9"}
    out = []
    CAMTEK_CAP = 120
    PWC_CAP = 120

    def _get(url, timeout=25):
        return requests.get(url, headers=HDRS, timeout=timeout, allow_redirects=True)

    def _level(title, desc=""):
        # title-driven only: JD text ("we hire students", "3 years") gives false positives.
        # Word-bound: 'intern' must not hit "Internal Audit" / "Linux Internals".
        t = title.lower()
        if re.search(r"\b(student|intern(ship)?s?)\b", t) or "סטודנט" in t:
            return "student"
        if any(w in t for w in ("senior", "sr.", "sr ", " lead", "lead ", "principal",
                                "staff", "architect", "manager", "head of", "director",
                                "team lead", "expert", " vp", "vp ", "chief")):
            return "senior"
        if any(w in t for w in ("junior", "jr.", "jr ", "entry", "graduate")):
            return "junior"
        return ""

    def _years(text):
        t = (text or "").lower().replace("–", "-").replace("—", "-")
        ymin = ymax = None
        m = re.search(r'(\d{1,2})\s*(?:-|to|up to)\s*(\d{1,2})\s*\+?\s*(?:years|yrs|year)', t)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            ymin, ymax = min(a, b), max(a, b)
        else:
            singles = [int(x) for x in re.findall(r'(\d{1,2})\s*\+?\s*(?:years|yrs|year)', t)]
            singles = [s for s in singles if s <= 30]
            if singles:
                ymin = min(singles)
        return ymin, ymax

    TECHKW = ["python", "c++", "c#", ".net", "java", "javascript", "typescript", "react",
              "angular", "vue", "node", "sql", "nosql", "mongodb", "aws", "azure", "gcp",
              "docker", "kubernetes", "k8s", "tensorrt", "onnx", "pytorch", "tensorflow",
              "keras", "opencv", "cuda", "machine learning", "deep learning", "ml", "ai",
              "llm", "nlp", "computer vision", "embedded", "firmware", "rtos", "linux",
              "go ", "golang", "rust", "matlab", "verilog", "vhdl", "fpga", "qa",
              "automation", "selenium", "cypress", "rest", "microservices", "spark",
              "kafka", "algorithms", "image processing", "devops", "ci/cd"]

    def _tech(text, extra=None):
        t = (text or "").lower()
        found = []
        for k in TECHKW:
            if k in t and k.strip() not in found:
                found.append(k.strip())
        if extra:
            for e in extra:
                e = (e or "").strip()
                if e and e.lower() not in [f.lower() for f in found]:
                    found.append(e)
        return found[:15]

    # ---------------- 1) CAMTEK (primary) ----------------
    # Single listing page: div.item.read-more-click -> h3.title / p.department /
    # p.location / a[href] (code = last URL path segment). Then enrich each role
    # from its own /open-positions/{code}/ page (small co -> only ~29 requests).
    try:
        r = _get("https://www.camtek.com/careers/open-positions/")
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "lxml")
            items = soup.select("div.item.read-more-click")
            for it in items:
                if len(out) >= CAMTEK_CAP:
                    break
                try:
                    a = it.find("a", href=True)
                    if not a:
                        continue
                    url = a["href"].strip()
                    if url.startswith("/"):
                        url = "https://www.camtek.com" + url
                    code = url.rstrip("/").rsplit("/", 1)[-1]
                    ttl = it.select_one("h3.title") or it.select_one(".title")
                    dep = it.select_one("p.department") or it.select_one(".department")
                    loc = it.select_one("p.location") or it.select_one(".location")
                    title = ttl.get_text(" ", strip=True) if ttl else ""
                    dept = dep.get_text(" ", strip=True) if dep else ""
                    city = loc.get_text(" ", strip=True) if loc else ""
                    if not title:
                        continue
                    desc = ""
                    # enrich with the individual role page (small company -> cheap)
                    try:
                        d = _get(url, timeout=20)
                        if d.status_code == 200:
                            ds = BeautifulSoup(d.text, "lxml")
                            art = ds.select_one("article") or ds.select_one("div.main")
                            if art:
                                txt = art.get_text(" ", strip=True)
                                txt = re.sub(r'^\s*Back to Careers\s*', '', txt)
                                desc = re.sub(r'\s+', ' ', txt)[:1500]
                        time.sleep(0.25)
                    except Exception:
                        pass
                    ymin, ymax = _years(desc)
                    out.append({
                        "source": "camtek", "sid": code, "title": title, "company": "Camtek",
                        "city": city, "url": url, "level": _level(title, desc),
                        "years_min": ymin, "years_max": ymax,
                        "tech": _tech(title + " " + desc, extra=[dept] if dept else None),
                        "desc": desc, "active": True,
                    })
                except Exception:
                    continue
    except Exception:
        pass
    n_camtek = len(out)

    # ---------------- 2) PwC ISRAEL (bonus, best-effort) ----------------
    # PwC Israel has no clean public JSON/HTML job board (postings live on LinkedIn / a
    # gated Hebrew ATS). We probe a couple of candidate pages; if none expose a parseable
    # list we simply return nothing for PwC. Never raises.
    pwc = []
    try:
        pwc_urls = [
            "https://www.pwc.com/il/en/careers/open-positions.html",
            "https://www.pwc.com/il/en/careers/job-openings.html",
        ]
        for u in pwc_urls:
            if len(pwc) >= PWC_CAP:
                break
            try:
                r = _get(u, timeout=20)
                if r.status_code != 200:
                    continue
                soup = BeautifulSoup(r.text, "lxml")
                cards = soup.select("a[href*='job'], li.job, div.job-item, .position")
                for c in cards:
                    if len(pwc) >= PWC_CAP:
                        break
                    title = c.get_text(" ", strip=True)
                    href = c.get("href", "")
                    if not title or len(title) < 4 or not href:
                        continue
                    if href.startswith("/"):
                        href = "https://www.pwc.com" + href
                    sid = href.rstrip("/").rsplit("/", 1)[-1][:40]
                    pwc.append({
                        "source": "pwc", "sid": sid, "title": title, "company": "PwC Israel",
                        "city": "", "url": href, "level": _level(title),
                        "years_min": None, "years_max": None, "tech": _tech(title),
                        "desc": "", "active": True,
                    })
                if pwc:
                    break
            except Exception:
                continue
    except Exception:
        pass
    out.extend(pwc)

    try:
        print("    camtek per-company: Camtek %d, PwC %d" % (n_camtek, len(pwc)))
    except Exception:
        pass
    return out
