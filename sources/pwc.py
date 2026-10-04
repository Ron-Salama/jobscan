# -*- coding: utf-8 -*-
"""PwC Israel career site (HunterHRMS JSON backend).

PwC NEXT jobs (employerName 'DT&CS') are all kept; other PwC Israel jobs only when the
title reads as tech.
"""


def src_pwc():
    """PwC Israel's official career site (HunterHRMS, pwc-careersite.hunterhrms.com). Its
    vendor backend answers POST {"cmd":"get-jobs"} with every open PwC Israel job as JSON
    (no auth). PwC NEXT - PwC Israel's tech subsidiary - files its
    jobs under employerName 'DT&CS'; those are labelled 'PwC NEXT' (all kept). Other PwC Israel
    jobs (audit/tax/advisory/HQ) are kept only when the title reads as tech, as 'PwC Israel'.
    Researched + re-tested 2026-09-24 (51 jobs, 12 NEXT). Never raises."""
    import re, html as _html
    try:
        import requests
    except Exception:
        return []
    URL = "https://niloo-server.herokuapp.com/actions-pwc-career"
    JOB = "https://pwc-careersite.hunterhrms.com/job?jid=%s"
    AREA = {"1": "Tel Aviv", "2": "Haifa", "3": "Jerusalem", "4": "Beer Sheva"}
    TECH = re.compile(r"engineer|develop|software|technolog|tech\b|data|\bai\b|automation|cyber|cloud|devops"
                      r"|python|full.?stack|innovation|\bit\b|טכנולוג|מפתח|פיתוח|תוכנה|דאטה|בינה|חדשנות|מערכות מידע")
    def text(s):
        s = _html.unescape(_html.unescape(s or ""))          # the API escapes its HTML twice
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s)).strip()
    arr = None
    for attempt in range(2):                                  # a sleeping Heroku dyno may time out once
        try:
            r = requests.post(URL, json={"cmd": "get-jobs"}, timeout=45,
                              headers={"User-Agent": "Mozilla/5.0 JobScan/1.0"})
            if r.status_code in (200, 201):
                arr = r.json(); break
            print("    pwc: HTTP %s" % r.status_code)
        except Exception as e:
            print("    pwc: %s" % type(e).__name__)
    if not isinstance(arr, list):
        return []
    out = []; n_next = 0
    for p in arr:
        try:
            title = (p.get("jobTitle") or "").strip()
            nxt = (p.get("employerName") or "").strip().upper() == "DT&CS"
            if not title or not (nxt or TECH.search(title.lower())):
                continue
            n_next += nxt
            city = AREA.get(str(p.get("jobArea") or ""), "Tel Aviv" if nxt else "Israel")
            desc = " \n".join(x for x in (text(p.get("description")), text(p.get("requirements")),
                                          text(p.get("skills") if isinstance(p.get("skills"), str) else ""))
                              if x)
            code = (p.get("jobCode") or "").strip()
            out.append({"source": "pwc", "sid": str(p.get("jobId") or code), "title": title + (" - " + code if code and code not in title else ""),
                        "company": "PwC NEXT" if nxt else "PwC Israel", "city": city,
                        "url": JOB % p.get("jobId"), "level": "", "years_min": None, "years_max": None,
                        "tech": [], "desc": desc[:3000], "active": True})
        except Exception:
            continue
    print("    pwc: %d open, kept %d (%d PwC NEXT)" % (len(arr), len(out), n_next))
    return out
