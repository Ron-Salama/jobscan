# -*- coding: utf-8 -*-
"""Lever public postings API - a registry of Israeli-employer boards.

Each board has its own API host (Lever's EU instance hosts e.g. Mobileye).
"""


def src_lever():
    """Lever public postings API: GET {host}/v0/postings/{slug}?mode=json -> JSON array.
    Registry of Israeli-employer Lever boards, each with its own API host (Lever's EU
    instance api.eu.lever.co hosts e.g. Mobileye; the US api.lever.co 404s for it).
    Filter to Israel by country / categories.location / allLocations. A failed board is
    logged (slug + status/exception), never silently skipped. Never raises."""
    import json, re, time, urllib.request, urllib.error
    UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    # slug -> (API host, company name). Grows as more Israeli Lever boards are confirmed.
    BOARDS = {
        "walkme":   ("api.lever.co", "walkme"),
        "mobileye": ("api.eu.lever.co", "Mobileye"),    # giant; added 2026-09-24 (~147 IL roles)
    }
    ILC = ("israel", "tel aviv", "tel-aviv", "herzliya", "haifa", "yokneam", "ramat", "netanya",
           "petah", "raanana", "kfar", "jerusalem", "beer", "hod hasharon", "caesarea")
    out = []
    per_board = {}
    for slug, (host, company) in BOARDS.items():
        try:
            req = urllib.request.Request("https://%s/v0/postings/%s?mode=json" % (host, slug),
                                         headers={"User-Agent": UA, "Accept": "application/json"})
            arr = json.loads(urllib.request.urlopen(req, timeout=30).read().decode("utf-8"))
            if not isinstance(arr, list):
                raise ValueError("non-list response")
        except urllib.error.HTTPError as e:
            per_board[slug] = "FAILED HTTP %s" % e.code
            continue
        except Exception as e:
            per_board[slug] = "FAILED %s" % (type(e).__name__)
            continue
        n = 0
        for p in arr:
            try:
                cats = p.get("categories", {}) or {}
                loc = cats.get("location") or ""
                all_locs = " | ".join(cats.get("allLocations") or [])
                if not ((p.get("country") or "").upper() == "IL"
                        or any(k in (loc + " | " + all_locs).lower() for k in ILC)):
                    continue
                if not any(k in loc.lower() for k in ILC):
                    # primary site abroad, Israel only in allLocations -> show the IL site
                    loc = next((l for l in (cats.get("allLocations") or [])
                                if any(k in l.lower() for k in ILC)), loc)
                desc = re.sub("<[^>]+>", " ", (p.get("descriptionPlain") or p.get("description") or ""))
                # requirements (the years) live in `lists`, not in the description
                for lst in (p.get("lists") or []):
                    body = re.sub("<[^>]+>", " ", (lst.get("content") or ""))
                    desc += "\n" + (lst.get("text") or "") + ": " + body
                desc = re.sub(r"[ \t]+", " ", desc).strip()
                out.append({"source": "lever:" + slug, "sid": p.get("id", ""), "title": p.get("text", ""),
                            "company": company, "city": loc, "url": p.get("hostedUrl", ""),
                            "level": "", "years_min": None, "years_max": None, "tech": [],
                            "desc": desc[:3000], "active": True})
                n += 1
            except Exception:
                continue
        per_board[slug] = n
        time.sleep(0.2)
    try:
        print("    lever per-board:", per_board)
    except Exception:
        pass
    return out
