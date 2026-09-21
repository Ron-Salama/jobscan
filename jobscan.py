# -*- coding: utf-8 -*-
"""
Ron's multi-source Israeli tech-job scanner.
v1 sources (open APIs): hiremetech, Experis (GraphQL), Drushim (JSON), Greenhouse boards, amazon.jobs.
Pulls -> normalizes -> seniority/lane filter -> cross-source dedup -> classify (fit/CV/flags)
-> appends to the AUTO tracker under a dated sector -> updates seen registry -> writes a summary.
Pure stdlib (urllib/json/re). Safe to run daily unattended.
"""
import json, re, io, sys, os, time, urllib.request, urllib.parse, datetime
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C
try:
    import sources_ext as X
    _EXT_FNS = [("ethosia",X.src_ethosia),("dialog",X.src_dialog),("nisha",X.src_nisha),
        ("gotfriends",X.src_gotfriends),("builtin",X.src_builtin),("linkedin",X.src_linkedin),
        ("cps",X.src_cps),("techjob",X.src_techjob),("alljobs",X.src_alljobs),
        ("comeet",X.src_comeet),("workday",X.src_workday),("apple",X.src_apple),("camtek",X.src_camtek)]
except Exception as _e:
    _EXT_FNS = []; print("sources_ext load err:", _e)

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) JobScan/1.0"
TODAY = datetime.date.today().isoformat()

# ---------------- http ----------------
def _get(url, headers=None, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent":UA, "Accept":"application/json", **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")

def get_json(url, headers=None):
    return json.loads(_get(url, headers))

def post_json(url, payload, headers=None):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST",
        headers={"User-Agent":UA,"Content-Type":"application/json","Accept":"application/json", **(headers or {})})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8","replace"))

# ---------------- model ----------------
def region_of(city):
    c = (city or "").lower()
    for k in C.SOUTH:
        if k in c: return "South"
    for k in C.JERUSALEM:
        if k in c: return "Jerusalem"
    for k in C.NORTH:
        if k in c: return "North"
    if not c or c in ("israel","ישראל"): return "Unknown"
    return "Center"

def normalize(d):
    """Ensure any adapter's dict has all keys + a computed region."""
    for k, v in (("source",""),("sid",""),("title",""),("company",""),("city",""),("url",""),
                 ("level",""),("years_min",None),("years_max",None),("tech",[]),("desc",""),("active",True)):
        d.setdefault(k, v)
    d["level"] = (d.get("level") or "").lower()
    d["sid"] = str(d.get("sid",""))
    d["title"] = d.get("title") or ""
    d["company"] = d.get("company") or ""
    d["region"] = region_of(d.get("city",""))
    return d

def job(source, sid, title, company="", city="", url="", level="", years_min=None,
        years_max=None, tech=None, desc="", active=True):
    return {"source":source,"sid":str(sid),"title":title or "","company":company or "",
            "city":city or "","url":url or "","level":(level or "").lower(),
            "years_min":years_min,"years_max":years_max,"tech":tech or [],
            "desc":desc or "","active":active,"region":region_of(city)}

# ---------------- sources (v1: open APIs) ----------------
def src_hiremetech():
    out=[]
    for page in range(1,28):
        try: d=get_json("https://hiremetech.com/api/jobs/search?"+urllib.parse.urlencode(
            {"limit":100,"page":page,"job_level":"junior","sort_by":"posted_date","sort_order":"desc"}))
        except Exception as e: print("  hiremetech pg%d err %s"%(page,e)); break
        for j in d.get("jobs",[]):
            loc=j.get("location",{}) or {}
            city=(loc.get("basic",{}) or {}).get("display_name","") if isinstance(loc,dict) else ""
            out.append(job("hiremetech",j["id"],j.get("title"),
                _co(j), city, "https://hiremetech.com/job/%s"%j["id"],
                j.get("job_level"), None, None, _tech(j),
                _txt(j.get("requirements"))+" "+_txt(j.get("description")), j.get("is_active",True)))
        if not (d.get("pagination",{}) or {}).get("has_more"): break
        time.sleep(0.15)
    return out

def _co(j):
    c=j.get("company_name") or j.get("company") or ""
    if isinstance(c,dict): c=c.get("name","") or ""
    return c
def _tech(j):
    t=j.get("tech_stack") or j.get("skills_required") or j.get("skills") or []
    return t if isinstance(t,list) else []
def _txt(x):
    if x is None: return ""
    if isinstance(x,(list,tuple)): return " ".join(_txt(i) for i in x)
    if isinstance(x,dict): return " ".join(_txt(v) for v in x.values())
    return str(x)

def src_experis():
    out=[]; after=None
    q = ('{ allJob(first:50%s, where:{taxQuery:{taxArray:[{taxonomy:JOBEXPERIENCE,terms:["1963","1964"],field:ID,operator:IN}]}}) '
         '{ pageInfo{hasNextPage endCursor} nodes{ databaseId title uri date '
         'jobAreas{nodes{name}} jobExperiences{nodes{name}} jobScopes{nodes{name}} } } }')
    for _ in range(12):
        body={"query": q % (', after:"%s"'%after if after else "")}
        try: d=post_json("https://experiscontent.experis.co.il/graphql", body)
        except Exception as e: print("  experis err %s"%e); break
        conn=(d.get("data",{}) or {}).get("allJob",{}) or {}
        for n in conn.get("nodes",[]):
            area=", ".join(x["name"] for x in (n.get("jobAreas",{}) or {}).get("nodes",[]))
            exp =", ".join(x["name"] for x in (n.get("jobExperiences",{}) or {}).get("nodes",[]))
            scope=" ".join(x["name"] for x in (n.get("jobScopes",{}) or {}).get("nodes",[]))
            lvl = "student" if ("סטודנט" in scope or "student" in scope.lower()) else \
                  ("junior" if "ללא" in exp else "mid")
            out.append(job("experis", n.get("databaseId"), n.get("title"), "",
                area, "https://experis.co.il"+(n.get("uri") or ""), lvl, None,
                (2 if lvl=="junior" else None), [], exp+" "+scope))
        pi=conn.get("pageInfo",{}) or {}
        if not pi.get("hasNextPage"): break
        after=pi.get("endCursor"); time.sleep(0.2)
    return out

def src_drushim():
    out=[]
    for exp in ("1","2"):  # 1=no exp(junior), 2=1-2yr
        for page in range(0,10):
            try: d=get_json("https://webapi.drushim.co.il/api/jobs/search?"+urllib.parse.urlencode(
                {"searchterm":"hitech","page":page,"experience":exp}))
            except Exception as e: print("  drushim exp%s pg%d err %s"%(exp,page,e)); break
            rl=d.get("ResultList",[]) or []
            for j in rl:
                jc=j.get("JobContent",{}) or {}; co=j.get("Company",{}) or {}; ji=j.get("JobInfo",{}) or {}
                addr=jc.get("Addresses") or jc.get("Regions") or []
                city=_txt(addr[0]) if isinstance(addr,list) and addr else _txt(jc.get("Zones"))
                out.append(job("drushim", j.get("Code") or ji.get("JobCode"), jc.get("Name"),
                    co.get("CompanyDisplayName") or co.get("NameInHebrew"), city,
                    "https://www.drushim.co.il"+(ji.get("Link") or ""),
                    "junior" if exp=="1" else "junior", None, 2,
                    _catlist(jc), _txt(jc.get("Requirements"))+" "+_txt(jc.get("Description"))))
            if not d.get("NextPageNumber") or page+1>=(d.get("TotalPagesNumber") or 0): break
            time.sleep(0.2)
    return out
def _catlist(jc):
    for k in ("Categories","SubCategories"):
        v=jc.get(k)
        if isinstance(v,list) and v: return [_txt(x) for x in v]
    return []

def src_greenhouse():
    out=[]
    for slug in C.GREENHOUSE_SLUGS:
        try: d=get_json("https://boards-api.greenhouse.io/v1/boards/%s/jobs?content=true"%slug)
        except Exception: continue
        for j in d.get("jobs",[]):
            loc=(j.get("location",{}) or {}).get("name","")
            if "israel" not in loc.lower() and not any(k in loc.lower() for k in
                ("tel aviv","haifa","herzliya","yokneam","jerusalem","ramat","netanya","petah","raanana","beer")):
                continue
            desc=re.sub("<[^>]+>"," ", __import__("html").unescape(j.get("content") or ""))
            out.append(job("greenhouse:"+slug, j.get("id"), j.get("title"),
                slug, loc, j.get("absolute_url"), "", None, None, [], desc))
        time.sleep(0.1)
    return out

def src_amazon():
    out=[]
    try:
        d=get_json("https://www.amazon.jobs/en/search.json?"+urllib.parse.urlencode(
            {"loc_query":"Israel","country":"ISR","normalized_country_code":"ISR",
             "result_limit":100,"sort":"recent","category":"software-development"}))
    except Exception as e:
        print("  amazon err %s"%e); return out
    IL = ("israel","tel aviv","haifa","herzliya","yokneam","jerusalem","ramat","netanya","petah","raanana","kiryat")
    for j in d.get("jobs",[]):
        loc=(j.get("normalized_location") or j.get("city") or j.get("location") or "").lower()
        if not any(k in loc for k in IL): continue   # amazon.jobs country filter is unreliable -> post-filter to IL
        out.append(job("amazon", j.get("id_icims") or j.get("id"), j.get("title"),
            "Amazon", j.get("normalized_location") or j.get("city"),
            "https://www.amazon.jobs"+(j.get("job_path") or ""), "",
            None, None, [], _txt(j.get("basic_qualifications"))))
    return out

SOURCES = [("hiremetech",src_hiremetech),("experis",src_experis),("drushim",src_drushim),
           ("greenhouse",src_greenhouse),("amazon",src_amazon)]

# ---------------- seniority / lane / classify ----------------
def _has(text, words):
    t=text.lower(); return any(w in t for w in words)

def parse_years(desc):
    # Return the LOWEST experience floor stated. Ranges like "0-3 years" must
    # contribute their lower bound (0), not the number touching "years" (3) —
    # otherwise grad-friendly "0-3y" roles get misread as a 3-year minimum.
    t=(desc or "").lower()
    yrs=r'(?:years|year|yrs|שנ)'
    lows=[int(a) for a,_ in re.findall(r'(\d+)\s*(?:-|–|—|to|עד)\s*(\d+)\s*'+yrs, t)]  # range low
    lows+=[int(x) for x in re.findall(r'(\d+)\s*\+?\s*'+yrs, t)]                        # singles / N+
    return min(lows) if lows else None

def is_junior(j):
    title=j["title"].lower()
    if _has(title, C.STUDENT_MARK) or j["level"] in ("student","student / intern","intern"): return False,"student"
    if _has(title, C.SENIOR_TITLE): return False,"senior-title"
    ymin = j["years_min"] if j["years_min"] is not None else parse_years(j["desc"])
    if ymin is not None and ymin>=3: return False,"%dy+"%ymin
    if j["years_max"] is not None and j["years_max"]<=2: return True,"<=2y"
    if j["level"] in ("junior","entry","entry level","junior / entry level","associate"): return True,"level"
    if ymin is not None and ymin<=2: return True,"%dy"%ymin
    return True,"unknown"   # keep, will be flagged review

MANUAL_QA = ["qa engineer","qa tester","manual test","בודק","בדיקות תוכנה"]
def classify(j):
    title=j["title"]; tl=title.lower(); blob=(title+" "+" ".join(j["tech"])+" "+j["desc"])
    referral = _has(j["company"].lower(), C.REFERRAL_COMPANIES)  # company only
    giant    = _has(j["company"].lower(), C.GIANTS)
    if not _has(tl, C.TITLE_DEV): return None                    # dev role by TITLE only
    # A hardware discipline in the TITLE = genuinely not his lane -> skip.
    # The same term only in the JD BODY (e.g. a SW-tools role that supports a
    # post-silicon team) is the team's domain, not a missing qualification -> review.
    hw_in_title = _has(" "+tl+" ", C.FOUNDATION_SKIP)
    hw_in_body  = _has((" ".join(j["tech"])+" "+(j["desc"] or "")).lower(), C.FOUNDATION_SKIP)

    tailor = False
    ymin = j["years_min"] if j["years_min"] is not None else parse_years(j["desc"])
    senior_title = _has(tl, C.SENIOR_TITLE)
    senior = senior_title or (ymin is not None and ymin >= 3)
    student = _has(tl, C.STUDENT_MARK) or j["level"] in ("student","student / intern","intern")
    is_jr = (_has(tl, C.JUNIOR_MARK)                              # junior/grad word in the title (EN+HE)
             or j["level"] in ("junior","entry","entry level","junior / entry level","associate")
             or (ymin is not None and ymin <= 2))

    if _has(tl, MANUAL_QA) and "automation" not in tl:
        lane, why = "skip", "manual-QA"
    elif hw_in_title:
        lane, why = "skip", "foundation-gap"          # hardware discipline in the TITLE itself
    elif student:
        lane, why = "skip", "student"
    elif referral or giant:
        # a referral broadens quals to junior-mid, but NOT to senior/4y+ (not a reach even with a referral)
        if senior_title or (ymin is not None and ymin >= 4):
            lane, why = "skip", "too-senior-even-w-referral"
        elif ymin == 3:
            lane, why, tailor = "reach", "3y-referral-tailor", True
        elif is_jr:
            lane, why = "apply", "junior"
        else:
            lane, why, tailor = "reach", "unclear-referral", True
    else:
        if is_jr and not senior:
            lane, why = "apply", "junior"
        elif senior_title or (ymin is not None and ymin >= 4):
            lane, why = "skip", "senior"
        elif ymin == 3:
            lane, why, tailor = "reach", "3y-worth-tailoring", True   # almost a match
        else:
            lane, why = "review", "unclear"      # seniority unknown, non-giant -> kept North-only
    # SW-title role that only mentions a hardware domain in the JD body: don't hide it,
    # surface it for a look (the domain is the team's, not a qualification he's missing).
    if hw_in_body and lane != "skip":
        lane, why, tailor = "review", "silicon-in-jd", False
    # CV pick
    t=blob.lower()
    if _has(t,["ai ","llm","genai","ai engineer","ai developer"]): cv=C.CV["ai"]
    elif _has(t,["embedded","firmware","rtos","real-time","real time","microcontroller"]): cv=C.CV["embedded"]
    elif _has(t,["automation","validation","verification","sdet","test"]): cv=C.CV["test"]
    elif "c++" in t or "c/c++" in t: cv=C.CV["clow"]
    elif _has(t,["backend","full stack","fullstack","full-stack",".net","c#","java","react","angular","node","developer"]): cv=C.CV["backend"]
    else: cv=C.CV["backend"]
    # fit
    if lane == "apply": fit = 5 if j["region"] == "North" else 4
    elif lane in ("reach","review"): fit = 4 if (referral or giant) else 3
    else: fit = 1
    if referral and lane != "skip": fit = 5
    # honesty gate: only claim "worth tailoring" if we actually READ enough of the JD to judge it
    verified = len((j.get("desc") or "").strip()) > 60
    tailor = tailor and verified
    return {"lane":lane,"why":why,"cv":cv,"fit":fit,"referral":referral,"giant":giant,
            "tailor":tailor,"verified":verified}

# ---------------- dedup ----------------
def norm(s):
    s=(s or "").lower(); s=re.sub(r"\(.*?\)"," ",s); s=re.sub(r"[^a-z0-9֐-׿ ]"," ",s)
    for w in ("senior","junior","jr","the","for","a ","ltd","israel","system","systems"):
        s=re.sub(r"\b"+re.escape(w)+r"\b"," ",s)
    return re.sub(r"\s+"," ",s).strip()

SUPPRESS_DAYS = 30   # a company+title stays deduped for this long, then may resurface (new req)
def _key_is_fresh(seen, key):
    """True = this company|title may be admitted. Exact-URL/sid dedup is permanent
    (handled separately); this softer company|title key EXPIRES so a genuinely new
    opening at a known company isn't hidden forever."""
    v = seen.get(key)
    if not v: return True
    d = v.get("seen") if isinstance(v, dict) else None
    if not d: return False
    try:
        return (datetime.date.today() - datetime.date.fromisoformat(d)).days > SUPPRESS_DAYS
    except Exception:
        return False

def dedup(jobs):
    by={}
    for j in jobs:
        k=(norm(j["company"]), norm(j["title"])[:40], j["region"])
        if k in by: by[k]["_sources"].add(j["source"])
        else: j["_sources"]={j["source"]}; by[k]=j
    return list(by.values())

# ---------------- registry ----------------
def load_reg(path=None):
    path = path or C.REGISTRY
    try:
        with open(path,encoding="utf-8") as f: return json.load(f)
    except Exception: return {"seen":{}}
def atomic_write(path, text):
    """Write via a temp file + os.replace so a crash mid-write can never leave a
    truncated/corrupt tracker or registry behind."""
    tmp = "%s.tmp.%d" % (path, os.getpid())
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text); f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)

def save_reg(r, path=None):
    path = path or C.REGISTRY
    atomic_write(path, json.dumps(r, ensure_ascii=False, indent=0))

# ---------------- tracker writer ----------------
def append_tracker(rows):
    with open(C.AUTO_TRACKER,encoding="utf-8") as f: lines=f.readlines()
    line=lines[140]; start=line.index("[")
    depth=0;end=None;instr=False;esc=False
    for i in range(start,len(line)):
        c=line[i]
        if instr:
            if esc:esc=False
            elif c=="\\":esc=True
            elif c=='"':instr=False
            continue
        if c=='"':instr=True
        elif c=="[":depth+=1
        elif c=="]":
            depth-=1
            if depth==0:end=i+1;break
    arr=json.loads(line[start:end])
    arr.extend(rows)
    lines[140]=line[:start]+json.dumps(arr,ensure_ascii=False,separators=(", ",": "))+line[end:]
    with open(C.AUTO_TRACKER,"w",encoding="utf-8") as f: f.writelines(lines)
    return len(arr)

# ---------------- pipeline (shared by local + cloud) ----------------
def collect(counts=None):
    """counts (optional dict) is filled name->rows, or -1 when the source errored,
    so the caller can spot a source that silently went dark."""
    raw=[]
    for name,fn in (SOURCES + _EXT_FNS):
        try:
            got=fn() or []
            got=[normalize(dict(x)) for x in got if isinstance(x,dict)]
            raw+=got; n=len(got); print("  %-12s %d" % (name,n))
        except Exception as e:
            n=-1; print("  %-12s ERROR %s"%(name,e))
        if counts is not None: counts[name]=n
    print("raw total:", len(raw))
    return raw

def _bucket(j, reason):
    """A filtered/uncertain role kept aside (with its JD text) for later manual/AI
    review, so the keyword rules never silently bury a real fit."""
    return {"reason":reason,"company":j.get("company",""),"role":j.get("title",""),
            "url":j.get("url",""),"region":j.get("region",""),"loc":j.get("city",""),
            "src":j.get("source",""),"desc":(j.get("desc") or "")[:700]}

def select(raw, reg, filtered=None):
    """Region-drop + classify + dedup vs registry -> NEW rows. Mutates reg['seen'].
    If `filtered` is a list, roles the rules set aside (skip / review / a giant whose
    title missed the dev gate) are appended to it with their JD text for later review."""
    raw=[j for j in raw if j["region"] not in C.DROP_REGIONS and j.get("active",True)]
    keep=[]
    for j in raw:
        c=classify(j)
        if not c:
            # non-dev TITLE: only worth a second look when it's a giant/referral company
            if filtered is not None and _has(j["company"].lower(), C.GIANTS+C.REFERRAL_COMPANIES):
                filtered.append(_bucket(j,"not-dev-title"))
            continue
        # Location filter is Jerusalem+South EXCLUSION only (done above via DROP_REGIONS).
        # "Israel"/no-city -> Unknown is kept: it's Israel and not positively Jer/South.
        if c["lane"]=="skip":
            if filtered is not None: filtered.append(_bucket(j,c["why"]))  # senior/foundation/student/...
            continue
        if c["lane"]=="review":
            if filtered is not None: filtered.append(_bucket(j,"review:"+c["why"]))
            if j["region"] not in ("North","Unknown"): continue  # Center unclear-seniority: off page, but in bucket
        j["_c"]=c; keep.append(j)
    print("after filter:", len(keep), "| bucket:", len(filtered) if filtered is not None else 0)
    keep=dedup(keep); print("after dedup:", len(keep))
    seen=reg.setdefault("seen",{})
    fresh=[j for j in keep if ("%s:%s"%(j["source"],j["sid"])) not in seen
           and _key_is_fresh(seen, norm(j["company"])+"|"+norm(j["title"]))]
    print("fresh (new):", len(fresh))
    rows=[]
    for i,j in enumerate(fresh):
        c=j["_c"]
        # alert ONLY on read-and-judged roles: referral/giant that are apply, or verified-tailor
        alertok = (c["referral"] or c["giant"]) and (c["lane"]=="apply" or c.get("tailor"))
        unread = "" if c.get("verified") else "·unread "
        flag=("🔔REFERRAL " if c["referral"] else "")+("★giant " if c["giant"] else "")+("✎TAILOR " if c.get("tailor") else "")+unread
        srcs="+".join(sorted(j["_sources"]))
        rows.append({
            "id":"auto-%s-%s-%d"%(TODAY,j["source"].split(":")[0],i),
            "company":j["company"] or "(masked)","role":j["title"],"url":j["url"],
            "sector":"auto %s"%TODAY,"region":j["region"],
            "fit":c["fit"],"cv":c["cv"],"desc":j["title"],"location":j["city"],
            "blurb":"%s[%s%s · via %s] %s"%(flag,c["lane"].upper(),(" "+c["why"]) if c["why"] else "",srcs,(j["desc"][:180])),
            "careers":j["url"],
            "openings":{"status":"live","roles":[{"title":j["title"],"url":j["url"]}],
                "note":"auto-scan %s | sources:%s | lane:%s | %s%s%s%s"%(TODAY,srcs,c["lane"],
                    "REFERRAL " if c["referral"] else "","GIANT " if c["giant"] else "","TAILOR " if c.get("tailor") else "","ALERT" if alertok else "")}
        })
        seen["%s:%s"%(j["source"],j["sid"])]={"t":j["title"][:60],"lane":c["lane"],"tailor":bool(c.get("tailor")),"seen":TODAY}
        seen[norm(j["company"])+"|"+norm(j["title"])]={"seen":TODAY}
    return rows

def alerts_for(rows):
    return [r for r in rows if "ALERT" in r["openings"]["note"]]

ALERT_BATCH_MAX = 25   # above this = backfill/re-scan, not real new-openings -> don't spam
def send_alerts(rows):
    if os.environ.get("JOBSCAN_NO_ALERT"):
        print("(alerts suppressed via JOBSCAN_NO_ALERT)"); return []
    a=alerts_for(rows)
    if len(a) > ALERT_BATCH_MAX:
        print("large batch (%d giant/referral) — per-role alerts suppressed (backfill)"%len(a))
        try:   # still send ONE nudge so a big real burst is never fully silent
            import notify; notify.notify_text("🔔 JobScan: %d new giant/referral roles this run (large batch — see the tracker)"%len(a))
        except Exception as e: print("notify err", e)
        return []
    if a:
        try:
            import notify; notify.notify_jobs(a); print("alerted %d giant/referral roles"%len(a))
        except Exception as e: print("notify err", e)
    return a

# ---------------- main (LOCAL: writes Desktop tracker) ----------------
def main():
    print("JobScan run %s" % TODAY)
    reg=load_reg()
    rows=select(collect(), reg)
    if rows:
        total=append_tracker(rows); print("appended %d rows -> tracker now %d"%(len(rows),total))
    save_reg(reg)
    send_alerts(rows)
    return rows

if __name__=="__main__":
    main()
