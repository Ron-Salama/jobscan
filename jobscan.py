# -*- coding: utf-8 -*-
"""
Ron's multi-source Israeli tech-job scanner.
v1 sources (open APIs): hiremetech, Experis (GraphQL), Drushim (JSON), Greenhouse boards, amazon.jobs.
Pulls -> normalizes -> seniority/lane filter -> cross-source dedup -> classify (fit/CV/flags)
-> appends to the AUTO tracker under a dated sector -> updates seen registry -> writes a summary.
Pure stdlib (urllib/json/re). Safe to run daily unattended.
"""
import json, re, io, sys, os, time, math, hashlib, urllib.request, urllib.parse, datetime
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C
try:
    import sources_ext as X
    # (name, function) - looked up one by one, so a single missing/renamed adapter is skipped
    # with a warning instead of an AttributeError that silently disabled EVERY external source.
    _EXT_NAMES = [("ethosia","src_ethosia"),("dialog","src_dialog"),("nisha","src_nisha"),
        ("gotfriends","src_gotfriends"),("builtin","src_builtin"),("linkedin","src_linkedin"),
        ("alljobs","src_alljobs"),   # cps+techjob disabled 2026-09-23: broken links + no JD
        ("comeet","src_comeet"),("workday","src_workday"),("apple","src_apple"),("camtek","src_camtek"),
        ("lever","src_lever"),       # incl. Mobileye on Lever's EU host
        # career-site scrapers (2026-09-23); verbit retired 2026-09-24 (no Israel jobs)
        ("qualityai","src_qualityai"),("lemonade","src_lemonade"),("hibob","src_hibob"),("kaltura","src_kaltura"),
        ("ashby","src_ashby"),       # Moon Active + monday.com (replaces src_moonactive)
        # giant company sites (2026-09-24, audit): Qualcomm+Microsoft, Oracle+Dell, Wix+SanDisk, ...
        ("eightfold","src_eightfold"),("oracle_hcm","src_oracle_hcm"),("smartrecruiters","src_smartrecruiters"),
        ("google","src_google"),("checkpoint","src_checkpoint"),("meta","src_meta"),
        ("booking","src_booking"),("sap","src_sap"),
        ("pwc","src_pwc")]          # PwC Israel career site; PwC NEXT = referral (2026-09-24)
    _EXT_FNS = []
    for _n, _f in _EXT_NAMES:
        _fn = getattr(X, _f, None)
        if _fn is None:
            print("sources_ext: adapter %s missing - skipped" % _f)
        else:
            _EXT_FNS.append((_n, _fn))
except Exception as _e:
    _EXT_FNS = []; print("sources_ext load err:", _e)

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) JobScan/1.0"

def _today():
    """Today's date in ISRAEL time. The cloud runner's clock is UTC, so a scan at 21:00-23:59Z
    used to stamp rows with the previous Israeli date (Pull column + date filter off by one)."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.datetime.now(ZoneInfo("Asia/Jerusalem")).date()
    except Exception:
        return datetime.date.today()
TODAY = _today().isoformat()

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
_HEB = "א-ת"   # Hebrew letters א-ת

def _loc_norm(s):
    """lowercase, one apostrophe code point, hyphen/maqaf -> space ('beer-sheva' == 'beer sheva')."""
    s = (s or "").lower()
    s = re.sub("[’׳`´]", "'", s)
    s = re.sub("[-־–—]", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def _loc_re(tokens):
    """One regex matching any token as a WHOLE token. English: not inside a longer word.
    Hebrew: not inside a longer word, but allowing the 1-2 letter prefixes ו/ה/ב/ל/מ/ש/כ
    ('והצפון', 'בחיפה') — never a bare `in` test, because 'עכו'/'ערד' are short."""
    eng, heb = set(), set()
    for t in tokens:
        t = _loc_norm(t)
        if t: (heb if re.search("[%s]" % _HEB, t) else eng).add(re.escape(t))
    alts = []
    if eng:
        alts.append(r"(?<![a-z0-9'])(?:%s)(?![a-z0-9])" % "|".join(sorted(eng, key=len, reverse=True)))
    if heb:
        alts.append(r"(?<![%s])(?:[ובלמשהכ]{0,2})(?:%s)(?![%s])"
                    % (_HEB, "|".join(sorted(heb, key=len, reverse=True)), _HEB))
    return re.compile("|".join(alts)) if alts else re.compile(r"(?!x)x")

_RX_NORTH  = _loc_re(C.NORTH)
_RX_SOUTH  = _loc_re(C.SOUTH)
_RX_JER    = _loc_re(C.JERUSALEM)
_RX_ABROAD = _loc_re(getattr(C, "ABROAD", ()))
_REGION_GENERIC = {_loc_norm(x) for x in getattr(C, "REGION_GENERIC", ("israel", "ישראל"))}
_LOC_SPLIT = re.compile(r"\s*(?:[,/|;•·\n]|\band\b|&)\s*")
_LOC_NOISE = re.compile(r"\(.*?\)|\b(?:hybrid|remote|on ?site|onsite)\b|היברידי|מהבית")

def _part_region(p):
    """Region of ONE location fragment, or None when it names no place ('Israel', 'Remote')."""
    bare = re.sub(r"\s+", " ", _LOC_NOISE.sub(" ", p)).strip(" .")
    if not bare or bare in _REGION_GENERIC or re.fullmatch(r"(?:(?:israel|il|ישראל) )?\d+\+? (?:more )?(?:locations?|מיקומים)", bare):
        return None     # a board's '2 Locations' placeholder names no place (was read as Center)
    if _RX_NORTH.search(p):  return "North"
    if _RX_SOUTH.search(p):  return "South"
    if _RX_JER.search(p):    return "Jerusalem"
    if _RX_ABROAD.search(p): return "Abroad"
    return "Center"

def region_of(city):
    """North / Center / South / Jerusalem / Abroad / Unknown for a location string (EN + HE).
    Splits multi-place strings on , / | ; — North if ANY place is North (the preferred region);
    South / Jerusalem / Abroad only if EVERY recognised place is (an agency listing
    'Tel Aviv & Center, Shfela, Beer Sheva & South' is kept as Center). Never raises."""
    try:
        s = _loc_norm(city)
        if not s:
            return "Unknown"
        regs = [r for r in (_part_region(p) for p in _LOC_SPLIT.split(s) if p) if r]
        if not regs:
            return "Unknown"
        if "North" in regs:
            return "North"
        known = set(regs)
        if known == {"Jerusalem"}:
            return "Jerusalem"
        if known <= {"South", "Jerusalem"}:
            return "South"
        if known == {"Abroad"}:
            return "Unknown" if ("israel" in s or "ישראל" in s) else "Abroad"
        if known <= {"Abroad", "South", "Jerusalem"}:
            return "Jerusalem" if "Jerusalem" in known and "South" not in known else "South"
        return "Center"
    except Exception:
        return "Unknown"

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
HMT_ABROAD_RECHECK = 40   # max per-run detail lookups for rows the search feed places abroad

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
    # hiremetech's SEARCH feed mis-geocodes some Israeli jobs (2026-09-25: a Shfela 'Junior Software
    # Developer' as "Gurugram, India", ERGO NEXT's Kfar Saba grad roles as "Munich, Germany"), and the
    # region filter then dropped them as abroad. The job's own record (/api/jobs/{id}) has the right
    # place, so every would-be-abroad row (a handful per run) is re-checked there before it's dropped.
    rechecked=0
    for r in out:
        if region_of(r["city"])!="Abroad" or rechecked>=HMT_ABROAD_RECHECK: continue
        rechecked+=1
        try: d=(get_json("https://hiremetech.com/api/jobs/%s"%r["sid"]) or {}).get("job") or {}
        except Exception: continue
        b=(d.get("location") or {}).get("basic") if isinstance(d.get("location"),dict) else None
        if isinstance(b,dict) and "israel" in ("%s %s"%(b.get("country") or "",b.get("display_name") or "")).lower():
            r["city"]=b.get("display_name") or "Israel"; r["region"]=region_of(r["city"])
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

DRUSHIM_PASSES = [{"catdir":6},            # the software category (~120 rows over exp 1+2)
                  {"searchterm":"QA"}, {"searchterm":"אוטומציה"}]   # test/automation outside catdir 6
DRUSHIM_MAX_PAGES = 30
def src_drushim():
    """Drushim software category + QA/automation keyword passes, experience 1 (none) and
    2 (1-2 yrs), deduped by Code. (The old searchterm='hitech' matched 'for a hi-tech company'
    ads - guards, cleaners - and yielded ~1 dev title in 142.) Level is left '' so
    classify()/parse_years decide from the title + JD instead of a forced 'junior'."""
    out=[]; codes=set()
    for base in DRUSHIM_PASSES:
        for exp in ("1","2"):  # 1=no exp, 2=1-2yr
            page=0
            while page < DRUSHIM_MAX_PAGES:
                try: d=get_json("https://webapi.drushim.co.il/api/jobs/search?"+urllib.parse.urlencode(
                    dict(base, experience=exp, page=page)))
                except Exception as e: print("  drushim %s exp%s pg%d err %s"%(base,exp,page,e)); break
                for j in d.get("ResultList",[]) or []:
                    jc=j.get("JobContent",{}) or {}; co=j.get("Company",{}) or {}; ji=j.get("JobInfo",{}) or {}
                    code=j.get("Code") or ji.get("JobCode")
                    if code in codes: continue
                    codes.add(code)
                    addr=jc.get("Addresses") or jc.get("Regions") or []
                    city=_txt(addr[0]) if isinstance(addr,list) and addr else _txt(jc.get("Zones"))
                    # '21936 - DevOps Engineer' -> 'DevOps Engineer' (agency req-number prefix)
                    title=re.sub(r"^\s*\d{3,}\s*[-–]\s*", "", jc.get("Name") or "")
                    out.append(job("drushim", code, title,
                        co.get("CompanyDisplayName") or co.get("NameInHebrew"), city,
                        "https://www.drushim.co.il"+(ji.get("Link") or ""),
                        "", None, None,
                        _catlist(jc), _txt(jc.get("Requirements"))+" "+_txt(jc.get("Description"))))
                if page+1 >= (d.get("TotalPagesNumber") or 0): break
                page+=1; time.sleep(0.2)
    return out
def _catlist(jc):
    for k in ("Categories","SubCategories"):
        v=jc.get(k)
        if isinstance(v,list) and v: return [_txt(x) for x in v]
    return []

SOURCE_FAILS = {}   # source -> [sub-boards that failed this run] (e.g. dead Greenhouse slugs)
def src_greenhouse():
    out=[]; failed=[]
    names=getattr(C, "GREENHOUSE_NAMES", {}) or {}
    for slug in C.GREENHOUSE_SLUGS:
        try: d=get_json("https://boards-api.greenhouse.io/v1/boards/%s/jobs?content=true"%slug)
        except Exception as e:
            # a renamed/moved board (gong->gongio, monday->Ashby) used to vanish silently
            failed.append(slug); print("  greenhouse %s FAILED: %s"%(slug, getattr(e,"code","") or e)); continue
        for j in d.get("jobs",[]):
            loc=(j.get("location",{}) or {}).get("name","")
            if "israel" not in loc.lower() and not any(k in loc.lower() for k in
                ("tel aviv","haifa","herzliya","yokneam","jerusalem","ramat","netanya","petah","raanana","beer")):
                continue
            desc=re.sub("<[^>]+>"," ", __import__("html").unescape(j.get("content") or ""))
            out.append(job("greenhouse:"+slug, j.get("id"), j.get("title"),
                names.get(slug, slug), loc, j.get("absolute_url"), "", None, None, [], desc))
        time.sleep(0.1)
    SOURCE_FAILS["greenhouse"]=failed
    if failed:
        print("  greenhouse: %d/%d boards failed: %s"%(len(failed), len(C.GREENHOUSE_SLUGS), ", ".join(failed)))
    return out

AMAZON_MAX = 1000   # safety ceiling for the offset loop (Israel has ~170 postings)
def src_amazon():
    """amazon.jobs Israel search, paged by `offset` until `hits` (the old single request with
    result_limit=100 never saw postings 101+; 'category' was ignored by the site - removed)."""
    out=[]; offset=0; hits=None
    IL = ("israel","tel aviv","haifa","herzliya","yokneam","jerusalem","ramat","netanya","petah","raanana","kiryat")
    while offset < AMAZON_MAX:
        try:
            d=get_json("https://www.amazon.jobs/en/search.json?"+urllib.parse.urlencode(
                {"loc_query":"Israel","country":"ISR","normalized_country_code":"ISR",
                 "result_limit":100,"offset":offset,"sort":"recent"}))
        except Exception as e:
            print("  amazon offset %d err %s"%(offset,e)); break
        jobs=d.get("jobs",[]) or []
        if hits is None:
            try: hits=int(d.get("hits") or 0)
            except Exception: hits=0
        for j in jobs:
            loc=(j.get("normalized_location") or j.get("city") or j.get("location") or "").lower()
            if not any(k in loc for k in IL): continue   # amazon.jobs country filter is unreliable -> post-filter to IL
            out.append(job("amazon", j.get("id_icims") or j.get("id"), j.get("title"),
                "Amazon", j.get("normalized_location") or j.get("city"),
                "https://www.amazon.jobs"+(j.get("job_path") or ""), "",
                None, None, [], _txt(j.get("basic_qualifications"))))
        offset+=100
        if not jobs or offset >= (hits or 0): break
        time.sleep(0.2)
    return out

SOURCES = [("hiremetech",src_hiremetech),("experis",src_experis),("drushim",src_drushim),
           ("greenhouse",src_greenhouse),("amazon",src_amazon)]

# ---------------- seniority / lane / classify ----------------
def _has(text, words):
    t=text.lower(); return any(w in t for w in words)

def _has_word(text, words):
    """Word-boundary match, so short terms like 'asic' don't match 'basic',
    'soc' doesn't match 'associate', etc. Used for the hardware/foundation skip list."""
    t=text.lower()
    for w in words:
        w=w.strip().strip("/-")
        if w and re.search(r"\b"+re.escape(w)+r"\b", t): return True
    return False

_YRS = r"(?:years?\b|yrs?\b|שנ(?:ים|ות|ה)(?![א-ת]))"
_YNUM = r"(?<![\d.])(\d{1,2}(?:\.\d)?)"
_YRANGE = re.compile(_YNUM + r"\s*\+?\s*(?:-|to\b|עד)\s*(\d{1,2}(?:\.\d)?)\s*\+?\s*" + _YRS)
_YSINGLE = re.compile(_YNUM + r"\s*\+?\s*" + _YRS)
# a number right after these is a ceiling / timeline / company history, not a requirement
# (parse_years takes the MAX, so a missed 'operating for 12 years' would out-rank the real '1-2 years')
_YBLOCK_BEFORE = re.compile(r"(?:\bup\s+to|\bwithin|(?<![א-ת])עד|\bfor\s+over|\bover\s+the\s+(?:past|last)"
                            r"|\bin\s+the\s+(?:past|last)|\bfounded|\bestablished|(?<![א-ת])מזה"
                            r"|(?<![א-ת])לפני"
                            r"|\b(?:operating|existing|active|business|market|around)\s+for)[^\d]{0,12}$")
_YBLOCK_AFTER = re.compile(r"^\s*(?:ago\b|old\b|history\b|warranty\b|since\b|degree\b|of stud|remaining\b"
                           r"|left\b|לימוד"
                           r"|of (?:operation|growth|success)\b)")
# NOTE: deliberately no 'in the industry/market' blocker - "5+ years in the industry" is a real (senior)
# requirement and must count; company-history phrasing is caught by _YBLOCK_BEFORE ('operating for ...').
_YBLOCK_AFTER_WIN = 24   # chars after 'N years' fed to _YBLOCK_AFTER (' of operation' needs > 12)
# nice-to-have statements are not requirements (taking the MAX would promote them):
# '3 שנות ניסיון ב-Python - יתרון', '5+ years preferred', or anything under an 'Advantages:' header
_YPREF = re.compile(r"\bpreferred\b|advantage|\ba plus\b|nice to have|\bbonus\b|יתרון|רצוי")
# an 'Advantages:' header needs its colon (strict: it DROPS statements); any later mention of
# requirements/qualifications resets to 'required' (loose: it only keeps statements counted)
_YPREF_HDR = re.compile(r"(?:advantages?|preferred(?: qualifications| skills| requirements)?|nice to have"
                        r"|bonus points?|יתרונות|יתרון)\)?\s*[:\n]")
_YREQ_HDR = re.compile(r"requirements?|qualifications|must have|required|what you.{0,6}need|דרישות|כישורים")
YEARS_MAX_SANE = 15   # '30 שנות ניסיון' is a mentor's / company's boast, not a requirement

_YSTMT = re.compile(r"[\n;•()]|\.(?!\d)|</?(?:br|li|p|ul|div)\b")   # statement boundaries (text or HTML)
_YDASH = re.compile(r"\s[-–]\s")                                     # ' - ' bullets / '– יתרון' markers
def _years_nice_to_have(txt, m):
    """The 'N years' at match m is a nice-to-have: marked in the requirement's OWN statement
    (outside any parenthetical: '(Go is a plus)' is about Go), or it sits under an
    'Advantages:' / 'Preferred Qualifications' header (the later header wins).
    The statement is cut at statement separators AND at ' - ' bullets, so on a flattened JD
    another bullet's '- advantage' / '- יתרון' can't attach to a real requirement; the next
    dash part is joined only when the requirement's own part is short (<= 5 words), which is
    the '1-2 שנות ניסיון בבדיקות – יתרון' / '3 years - a plus' shape."""
    parts = _YDASH.split(_YSTMT.split(txt[m.end():m.end()+80])[0])
    tail = parts[0]
    if len(parts) > 1 and len(tail.split()) <= 5:
        tail += " - " + parts[1]
    head = _YDASH.split(_YSTMT.split(txt[max(0, m.start()-40):m.start()])[-1])[-1]
    if _YPREF.search(tail) or _YPREF.search(head):
        return True
    back = txt[max(0, m.start()-600):m.start()]
    p = [x.end() for x in _YPREF_HDR.finditer(back)]; r = [x.end() for x in _YREQ_HDR.finditer(back)]
    return bool(p) and (not r or p[-1] > r[-1])

def parse_years(desc):
    """Minimum years of experience the JD asks for, or None.
    - separate 'N+ years' statements are separate requirements -> the MAX of them
      ('5+ years Python ... 1+ years AWS' = 5, not 1);
    - only a true range 'A-B years' (also 'A-B+') contributes its LOWER bound ('0-3 years' = 0);
    - 'up to N' / 'within N' / 'עד N' and company-history phrases are ignored;
    - nice-to-haves ('... - יתרון', 'preferred', an 'Advantages:' section) are ignored;
    - decimals round up ('1.5 years' = 2, never 5); values above 15 are ignored."""
    try:
        t=(desc or "").lower().replace("–","-").replace("—","-")
        floors=[]
        def _ok(txt, m):
            return not (_YBLOCK_BEFORE.search(txt[max(0, m.start()-40):m.start()])
                        or _YBLOCK_AFTER.search(txt[m.end():m.end()+_YBLOCK_AFTER_WIN])
                        or _years_nice_to_have(txt, m))
        for m in _YRANGE.finditer(t):
            if _ok(t, m):
                a=math.ceil(float(m.group(1)))
                if a <= YEARS_MAX_SANE: floors.append(a)
        t2=_YRANGE.sub(" ~ ", t)          # a range's upper bound must not also count as a single
        for m in _YSINGLE.finditer(t2):
            if _ok(t2, m):
                a=math.ceil(float(m.group(1)))
                if a <= YEARS_MAX_SANE: floors.append(a)
        return max(floors) if floors else None
    except Exception:
        return None

# what may follow a name glued into a slug ('paloalto'+'networks', 'nvidia'+'israel')
_CO_SUFFIX = re.compile(r"(?:israel|inc|ltd|corp|co|com|networks|technologies|systems|group|il|labs)*")
def company_is(company, names):
    """True when `company` names one of `names` as WHOLE word(s). A raw substring test made
    'sap' hit 'Sapiens', 'meta' hit 'Metalab', 'intel' hit 'Intelligo', and 'hp ' never
    matched a plain 'HP'. Names of 6+ letters also match a glued slug at the start, but only
    when the rest is nothing or corporate suffix(es) ('paloaltonetworks', 'nvidiaisrael';
    NOT 'Bookingjini' for booking or 'Marvellous Ltd' for marvell). Never raises."""
    try:
        c=re.sub(r"\s+"," ", re.sub(r"[^a-z0-9֐-׿]+"," ", (company or "").lower())).strip()
        if not c: return False
        glued=c.replace(" ","")
        for n in names:
            n=re.sub(r"\s+"," ", re.sub(r"[^a-z0-9֐-׿]+"," ", (n or "").lower())).strip()
            if not n: continue
            if re.search(r"(?<![a-z0-9])"+re.escape(n)+r"(?![a-z0-9])", c): return True
            ng=n.replace(" ","")
            if len(ng) >= 6 and glued.startswith(ng) and _CO_SUFFIX.fullmatch(glued[len(ng):]):
                return True
        return False
    except Exception:
        return False

def is_dev_title(tl):
    """The strict TITLE gate: a dev/integration word as a substring (TITLE_DEV), or a short
    stem (sw/fw/ate/s/w) / test phrase ('test engineer', 'test product'...) as whole words
    (TITLE_DEV_WORDS - so 'Swift', 'Private', 'Sales/Web', 'Pentest Product' don't pass)."""
    tl=(tl or "").lower()
    return _has(tl, C.TITLE_DEV) or _has_word(tl, getattr(C, "TITLE_DEV_WORDS", []))

_STUDENT_RE = re.compile(r"\b(?:students?|interns?|internships?|co-?op|trainees?)\b", re.I)
def is_student_title(t):
    """Student / intern role, judged from the TITLE only (never the JD or company blurb:
    'המתמחה בפיתוח' = 'that specializes in development', 'internal tools', 'international').
    'graduate' / 'new grad' / 'בוגר' are junior, not student."""
    t=t or ""
    return bool(_STUDENT_RE.search(t)) or "סטודנט" in t or t.strip().startswith("מתמח")

def is_senior_title(tl):
    """Senior title: SENIOR_TITLE as substrings ('lead' still catches 'Team Leader'; Hebrew
    inflections) + SENIOR_TITLE_WORDS word-bound ('architect' but not 'Platform Architecture',
    'staff' but not 'Staffing', 'vp' but not 'MVP', 'expert' but not 'Expertise')."""
    tl=(tl or "").lower()
    return _has(tl, C.SENIOR_TITLE) or _has_word(tl, getattr(C, "SENIOR_TITLE_WORDS", []))

MANUAL_QA = ["qa engineer","qa tester","manual test","בודק","בדיקות תוכנה"]
_QA_AUTO_TITLE = re.compile(r"automation|אוטומציה|אוטומטי|sdet")
QA_JD_AUTO = ["automation","אוטומציה","selenium","playwright","pytest","appium","cypress",
              "framework","python","c#"]
def is_manual_qa(tl, desc=""):
    """Manual-QA title -> skip lane (QA-bucket). Exempt when the title says automation
    (EN/HE) or, for a plain 'QA engineer'/'QA tester' title, when the JD names >= 2
    automation tools ('Software QA Engineer' whose JD is Pytest/C# frameworks)."""
    tl=(tl or "").lower()
    if _QA_AUTO_TITLE.search(tl):
        return False
    if re.search(r"\bmanual\b|ידני", tl) and (is_qa(tl) or "test" in tl):
        return True                      # 'Manual SW Tester' (now past the gate via 'sw')
    if not _has(tl, MANUAL_QA):
        return False
    if ("qa engineer" in tl or "qa tester" in tl) and not re.search(r"manual|ידני", tl):
        d=(desc or "").lower()
        if sum(1 for w in QA_JD_AUTO if w in d) >= 2:
            return False
    return True

_INDUSTRIAL = re.compile(r"\bplc\b|scada|בקרה|control engineer|מהנדס/ת בקרה")
def is_industrial_control(tl):
    """PLC / SCADA / industrial control & automation titles: not Ron's lane (RON_PROFILE)."""
    return bool(_INDUSTRIAL.search((tl or "").lower()))

# titles that pass the gate on a test/automation word but are not software test work:
# 'Mechanical Test Engineer', 'Penetration Tester', 'Pentest Automation', 'עורך/ת ...'
_NOT_SW_TEST = re.compile(r"mechanical|penetration|pentest|עור[כך]")   # עורך/עורכת = editor (final kaf too)
def is_not_sw_test(tl):
    return bool(_NOT_SW_TEST.search((tl or "").lower()))

# paid-course / 'training + placement' ads dressed as jobs (Drushim: 'AI software engineer -
# הכשרה והשמה'). Used to be caught by 'הכשרה' in the old STUDENT_MARK title test.
_TRAINING_AD = re.compile(r"הכשרה|bootcamp|בוטקמפ|קורס")
def is_training_ad(tl):
    return bool(_TRAINING_AD.search((tl or "").lower()))

# CV pick: TITLE first (word-bound), in this order; JD keyword counts only for generic titles.
_CV_TITLE = [
    ("test", r"\bqa\b|\btest|\bautomation|\bvalidation|\bverification|\bintegrat|\bate\b|labview"
             r"|teststand|sdet|בדיקות|בודק|אוטומציה|ולידציה|ואלידציה|אינטגרציה|אינטגרטור|שילובים"
             r"|מבדקים|וריפיקציה|צב[\"״]ד"),
    ("gametech", r"\bunity\b|\bunreal\b|\bgames?\b|\bgameplay\b|\bgame ?dev"),
    ("embedded", r"embedded|firmware|\bfw\b|\brtos\b|\bbsp\b|משובצ|קושחה"),
    ("ai", r"\bai\b|\bllm|genai|gen ai|\bagent|\bml\b|machine learning|\bprompt|בינה מלאכותית"),
    ("backend", r"full.?stack|back.?end|front.?end|\breact|\bjava|\bnode|\.net\b|\bc#"
                r"|פול.?סטא?ק|בק.?אנד|פרונט|צד שרת"),
    ("clow", r"(?<![\w+#])c(?![\w+#])|low.?level|\bkernel\b"),
]
_CV_JD = [
    ("test", [r"automation", r"validation", r"verification", r"test equipment", r"labview", r"teststand",
              r"\bscpi\b", r"\bate\b", r"sdet", r"selenium", r"pytest", r"hardware.in.the.loop", r"\bqa\b"]),
    ("embedded", [r"embedded", r"firmware", r"\brtos\b", r"microcontroller", r"bare.?metal", r"\bbsp\b",
                  r"device driver", r"\bstm32\b", r"cortex.?m"]),
    ("ai", [r"\bai\b", r"\bllms?\b", r"genai", r"machine learning", r"\brag\b", r"\bprompt", r"langchain",
            r"openai", r"agentic", r"\bnlp\b"]),
    ("backend", [r"back.?end", r"full.?stack", r"\breact\b", r"node\.?js", r"rest(?:ful)? api", r"microservice",
                 r"\bjava\b", r"\bspring\b", r"django", r"flask", r"fastapi", r"\.net\b", r"\bsql\b"]),
    ("clow", [r"\bc\s*/\s*c\+\+", r"\bc programming", r"\bc language", r"\bin c\b", r"\bansi c\b",
              r"low.?level", r"\bkernel\b", r"memory management"]),
    ("gametech", [r"\bunity\b", r"\bunreal\b", r"game engine", r"gameplay", r"shader"]),
]
def pick_cv(title, desc=""):
    """Which of Ron's CVs to send (a config.CV value). The TITLE decides first; the JD is
    only consulted for generic titles ('Software Engineer'): the category with the most
    distinct keyword hits (>= 2) wins, else the general CV. Never raises."""
    try:
        tl=(title or "").lower()
        for key, rx in _CV_TITLE:     # clow: a standalone 'C' ('C Developer', 'C/C++'), never C++-only/C#
            if re.search(rx, tl):
                return C.CV[key]
        d=(desc or "").lower(); best, score = "general", 1
        for key, pats in _CV_JD:
            n=sum(1 for p in pats if re.search(p, d))
            if n > score: best, score = key, n
        return C.CV[best]
    except Exception:
        return C.CV.get("general", "")

def is_qa(tl):
    """QA-ish title -> route to the QA-bucket for review (real test-eng vs manual-QA)."""
    return _has_word(tl, ["qa"]) or any(w in tl for w in ("quality assurance","tester","בדיקות","בודק"))

# gate-miss titles worth a look when the source gave no JD to read (review bucket 'no-jd-title')
_NO_JD_TITLE = re.compile(r"engineer|developer|מהנדס|מפתח|מתכנת")

def _term_rx(words):
    """Whole-term regex for English title terms that also matches right after a Hebrew letter
    ('הDevOps' = 'the DevOps') and around '&' / '/' - _has_word's word-boundary misses those."""
    ws = sorted({w.strip().lower() for w in words if w and w.strip() and re.search(r"[a-z]", w)}, key=len, reverse=True)
    return re.compile(r"(?<![a-z0-9])(?:" + "|".join(re.escape(w) for w in ws) + r")(?![a-z0-9])") if ws else None

_GAP_RX = _term_rx(getattr(C, "PROFILE_GAP_TITLE", []))
_CORE_SW_HEAD = ["software","developer","programmer","backend","back end","back-end","full stack","fullstack",
                 "full-stack","frontend","front end","front-end","qa","test","automation","python","java","c++","sw"]
def is_profile_gap_title(tl):
    """DevOps / SRE / cloud / ML-engineering title (Ron's call #7), judged on the title's HEAD (the
    role noun before the first ', ' / ' - ' / '(' qualifier): 'Software Engineer, DevOps Tools' and
    'Python Developer - SRE team' are software roles; 'DevOps Engineer', 'Backend & DevOps Engineer'
    and 'מהנדס/ת לצוות הDevOps' are profile-gap."""
    tl = (tl or "").lower()
    if not (_GAP_RX and _GAP_RX.search(tl)):
        return False
    head = re.split(r",|\s[-–—|:]\s|\(", tl, 1)[0]
    return bool(_GAP_RX.search(head)) or not _has_word(head, _CORE_SW_HEAD)

_EXP_HE = re.compile(r"(?<![א-ת])[הו]?מנוס(?:ה|ים|ות|/ה|\.ה|/ת)?(?![א-ת])")
def is_experienced_title(tl):
    """'Experienced ...' / 'מנוסה' (also מנוס/ה, מנוס.ה, המנוסה, מנוסים) - Ron's call #8. Not 'מנוסח'."""
    tl = (tl or "").lower()
    return bool(re.search(r"(?<![a-z0-9])experienced(?![a-z0-9])", tl) or _EXP_HE.search(tl))

STUDENT_LEVELS = ("student","student / intern","intern")
# sources whose 'student' level is a structured field (not a keyword guess over free text)
STRUCTURED_LEVEL_SOURCES = ("hiremetech","experis","comeet")

def classify(j):
    title=j["title"]; tl=title.lower(); desc=j.get("desc") or ""
    company=j.get("company") or ""
    referral = company_is(company, C.REFERRAL_COMPANIES)  # company only, whole words
    giant    = company_is(company, C.GIANTS)
    if not is_dev_title(tl): return None                  # dev role by TITLE only
    # A hardware discipline in the TITLE = genuinely not his lane -> skip.
    # (word-boundary match so "asic" != "basic", "soc" != "associate", etc.)
    hw_in_title = _has_word(tl, C.FOUNDATION_SKIP)
    # a *verification* title whose JD is chip DV (UVM/SystemVerilog/RTL) is the same gap
    if not hw_in_title and re.search(r"verification|v&v|וריפיקציה", tl) and _has_word(desc, getattr(C, "DV_JD", [])):
        hw_in_title = True

    tailor = False
    ymin = j["years_min"] if j["years_min"] is not None else parse_years(desc)
    senior_title = is_senior_title(tl)
    senior = senior_title or (ymin is not None and ymin >= 3)
    # student: from the TITLE; a source's 'student' level only when it's a structured field
    # (free-text adapters guessed it from JD/blurb words -> junior roles were skipped)
    student = is_student_title(title) or (
        j["level"] in STUDENT_LEVELS and (j.get("source") or "").split(":")[0] in STRUCTURED_LEVEL_SOURCES)
    jr_title = _has(tl, C.JUNIOR_MARK)                            # junior/grad word in the title (EN+HE)
    jr_level = j["level"] in ("junior","entry","entry level","junior / entry level","associate")
    is_jr = jr_title or jr_level or (ymin is not None and ymin <= 2)
    experienced = is_experienced_title(tl)

    if is_not_sw_test(tl):
        lane, why = "skip", "not-sw-test"             # mechanical / pentest / editor past the gate
    elif is_manual_qa(tl, desc):
        lane, why = "skip", "manual-QA"
    elif is_industrial_control(tl):
        lane, why = "skip", "industrial-control"      # PLC/SCADA/control: not his lane
    elif is_training_ad(tl):
        lane, why = "skip", "training-ad"             # course/placement ad, not a job
    elif hw_in_title:
        lane, why = "skip", "foundation-gap"          # hardware discipline in the TITLE itself
    elif student:
        lane, why = "skip", "student"
    elif jr_title and not senior_title and ymin is not None and ymin >= 4:
        # 'Junior X' whose JD asks 4y+: a contradictory posting (or a years misread) -> the review
        # bucket for a human/Claude read, never a silent drop (Ron's call #9, 2026-09-24)
        lane, why = "review", "junior-title-vs-years"
    elif experienced and not senior_title and not (ymin is not None and ymin >= 4):
        # 'Experienced ...' / 'מנוסה': some ask only 1-3 years -> REACH, not senior (call #8)
        # (4y+/senior already excluded above) a giant/referral one keeps its tailor flag + ping, like
        # the referral branch would have given it; only profile-gap (#7) roles are ping-free
        lane, why, tailor = "reach", "experienced-title", ymin == 3 or referral or giant
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
    # DevOps / SRE / cloud / ML-engineering titles are outside Ron's profile (call #7): REACH,
    # unless it's a pure learn-on-the-job opening - no experience asked (0y) or a junior/grad
    # title/level with no years stated - which stays apply (= YES). No ping for these reaches.
    if lane in ("apply", "reach") and is_profile_gap_title(tl):
        pure_junior = ymin == 0 or (ymin is None and (jr_title or jr_level))
        if lane == "apply" and pure_junior:
            why = "junior-learn-on-job"
        else:
            lane, why, tailor = "reach", "profile-gap", False
    # (Removed the "silicon-in-JD-body -> review" demotion: it was diverting apply-worthy
    #  software roles off the tracker whenever their JD merely mentioned a hardware word.
    #  Hardware *titles* are still skipped above; a software title stays on its seniority lane.)
    # CV pick: from the TITLE first (a JD substring like 'adopting ai tooling'/'latest'
    # used to pick Software & AI for QA titles); JD keywords only for generic titles
    cv = pick_cv(title, desc+" "+_txt(j.get("tech")))
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
    s=(s or "").lower()
    # before punctuation is stripped, so 'C# Developer' / 'C++ Developer' / 'C Developer' differ
    s=s.replace("c#"," csharp ").replace("c++"," cpp ").replace(".net"," dotnet ")
    s=re.sub(r"\(.*?\)"," ",s); s=re.sub(r"[^a-z0-9֐-׿ ]"," ",s)
    for w in ("senior","junior","jr","the","for","a ","ltd","israel","system","systems"):
        s=re.sub(r"\b"+re.escape(w)+r"\b"," ",s)
    return re.sub(r"\s+"," ",s).strip()

def _jd_fp(desc):
    """Short fingerprint of the JD's opening (normalized), or '' when there's too little
    text to tell two postings apart (e.g. Experis metadata-only rows)."""
    d=re.sub(r"[^a-z0-9א-ת]+"," ", (desc or "").lower()).strip()
    return hashlib.sha1(d[:400].encode("utf-8")).hexdigest()[:12] if len(d) >= 80 else ""

def soft_key(j):
    """The 30-day repost-suppression key.
    Named employer: company|title|region. Masked/empty employer (aggregators): the old
    '|title' key merged every 'Junior Software Engineer' at DIFFERENT hidden employers, so it
    is '|title|city|JD-fingerprint' - only a real repost of the same JD matches. With no JD
    to fingerprint there's no key (the permanent source:sid check still applies)."""
    co=norm(j.get("company")); ti=norm(j.get("title"))
    if not co:
        fp=_jd_fp(j.get("desc"))
        return "|%s|%s|%s"%(ti, norm(j.get("city")), fp) if fp else None
    return "%s|%s|%s"%(co, ti, j.get("region") or "")

def _legacy_key(j):
    """Pre-2026-09-24 named-employer key (company|title), still honoured until it expires so the
    key-format change doesn't re-admit reposts. Legacy '|title' (empty employer) keys are NOT."""
    co=norm(j.get("company"))
    return co+"|"+norm(j.get("title")) if co else None

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
        return (_today() - datetime.date.fromisoformat(d)).days > SUPPRESS_DAYS
    except Exception:
        return False

def _soft_value(j, day=None):
    """The seen[] value stored under a soft key: when + which row owns it (its URL, source and
    normalized city), so _soft_block can tell a repost from a second req at the same source."""
    return {"seen":day or TODAY, "u":j.get("url",""), "src":j.get("source",""), "city":norm(j.get("city"))}

def _soft_block(seen, j, retired=()):
    """None when the row may be admitted; otherwise the URL of the row that owns the
    blocking soft key ('' when unknown, e.g. a legacy key). `retired` = legacy keys whose
    owner is live this run (so its precise new-format key decides instead).
    A key owned by the SAME source in a DIFFERENT city does not block: that is two genuine
    reqs (e.g. Haifa + Yokneam, both 'North'), not a repost."""
    lk=_legacy_key(j)
    for key in (soft_key(j), None if lk in retired else lk):
        if key and not _key_is_fresh(seen, key):
            v=seen.get(key)
            if (isinstance(v, dict) and v.get("src") and v.get("src") == j.get("source")
                    and "city" in v and v.get("city") != norm(j.get("city"))):
                continue
            return (v.get("u") if isinstance(v, dict) else "") or ""
    return None

def dedup(jobs):
    """Merge one role seen on several boards into a single row (with _sources/_urls/_members).
    Named employer: same company+title+region from DIFFERENT sources. Two rows from the same
    source are never merged (distinct postings), and masked/empty-employer rows are never
    merged on title alone (different hidden employers) - only the same source:sid collapses."""
    by={}; out=[]
    for j in jobs:
        co=norm(j["company"])
        k=(co, norm(j["title"])[:40], j["region"]) if co else ("", j["source"], j["sid"])
        tgt=None; dupe=False
        for kept in by.get(k, []):
            if any(m["source"]==j["source"] and m["sid"]==j["sid"] for m in kept["_members"]):
                dupe=True; break                     # the very same posting twice (e.g. two pages)
            if j["source"] not in kept["_sources"]:
                tgt=kept; break
        if dupe: continue
        m={"source":j["source"], "sid":j["sid"], "url":j.get("url",""), "title":j.get("title","")}
        if tgt is not None:
            tgt["_sources"].add(j["source"]); tgt["_members"].append(m)
            if m["url"] and m["url"] not in tgt["_urls"]: tgt["_urls"].append(m["url"])
        else:
            j["_sources"]={j["source"]}; j["_members"]=[m]; j["_urls"]=[m["url"]]
            by.setdefault(k, []).append(j); out.append(j)
    return out

# ---------------- registry ----------------
_LAST_REG = {}   # the registry most recently loaded/saved (+ its path): send_alerts' retry queue lives there
def load_reg(path=None):
    path = path or C.REGISTRY
    try:
        with open(path,encoding="utf-8") as f: r=json.load(f)
    except Exception: r={"seen":{}}
    _LAST_REG.update(reg=r, path=path)
    return r
def atomic_write(path, text):
    """Write via a temp file + os.replace so a crash mid-write can never leave a
    truncated/corrupt tracker or registry behind."""
    tmp = "%s.tmp.%d" % (path, os.getpid())
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text); f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)

def save_reg(r, path=None):
    path = path or C.REGISTRY
    _LAST_REG.update(reg=r, path=path)
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

# the digest needs a real engineering/test ROLE noun ('Engineering Coordinator', 'Business Development
# Representative' used to pass on the substrings 'engineer' / 'develop'), and never a sales/HR/admin
# 'development' title or a Hebrew hardware discipline (review 2026-09-24)
_DIGEST_ROLE = re.compile(r"\bengineers?\b|\bdevelopers?\b|programmer|\bqa\b|\btest|integrat|validation"
                          r"|verification|v&v|automation|מהנדס|מפתח|מתכנת|בודק|בדיקות|אינטגר|ולידציה|וריפיקציה")
_DIGEST_NOT = re.compile(r"business develop|organi[sz]ational develop|talent develop|market develop"
                         r"|coordinator|administrat|assistant|electrical engineer|electronics? engineer"
                         r"|חומרה|חשמל|אלקטרוני|אופטי|מכונות|מכני")
def ref_digest_ok(tl, desc=""):
    """A referral-company title that MISSED the dev gate but may still be worth a referral:
    an engineering/test ROLE (_DIGEST_ROLE) that isn't senior, student, clearly non-dev (sales,
    manager, technician...), chip-design/foundation, a hardware discipline (REF_DIGEST_SKIP /
    _DIGEST_NOT), industrial control, pentest, or a verification title whose JD is chip DV."""
    tl=(tl or "").lower()
    if not _DIGEST_ROLE.search(tl) or _DIGEST_NOT.search(tl):
        return False
    if re.search(r"verification|v&v|וריפיקציה", tl) and _has_word(desc or "", getattr(C, "DV_JD", [])):
        return False
    # 'Technical Product Engineer' (Palo Alto) is a software role; other '... product engineer' are HW/NPI
    skip_tl = tl.replace("technical product engineer", "technical product role")
    return not (is_senior_title(tl) or is_student_title(tl) or _has(tl, C.DEVSIG_NONDEV)
                or _has_word(tl, C.FOUNDATION_SKIP) or _has_word(skip_tl, getattr(C, "REF_DIGEST_SKIP", []))
                or is_industrial_control(tl) or is_not_sw_test(tl))

def digest_title_key(company, role):
    """company|title for the digest: punctuation-insensitive but, unlike norm(), keeps parenthesised
    qualifiers ('QA Engineer (Cortex XDR)' != 'QA Engineer (Prisma Cloud)') and C#/C++/.NET."""
    def _tk(x):
        x = (x or "").lower().replace("c#", " csharp ").replace("c++", " cpp ").replace(".net", " dotnet ")
        return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9֐-׿]+", " ", x)).strip()
    return "%s|%s" % (_tk(company), _tk(role))

def select(raw, reg, filtered=None, qa=None, giant=None, refdigest=None):
    """Region-drop + classify + dedup vs registry -> NEW rows. Mutates reg['seen'].
    `filtered` = review-bucket (skip/review/oddly-titled). `qa` = QA-bucket: QA-ish roles
    the rules set aside, kept separately for review (real test-eng vs manual-QA).
    `giant` = Giant-bucket: EVERY giant-company role (senior/QA/any level), captured
    regardless of the filters below, so a referral-worthy giant role is never silently
    dropped (Ron's peace-of-mind safety net; reviewed manually like the other buckets).
    `refdigest` = referral-company roles that missed the title gate but look relevant
    (ref_digest_ok) - e.g. 'Nvlink QA Engineer' - for the Telegram referral digest."""
    raw=[j for j in raw if j["region"] not in C.DROP_REGIONS and j.get("active",True)]
    keep=[]
    for j in raw:
        if giant is not None and company_is(j.get("company"), C.GIANTS):
            tl=(j.get("title") or "").lower()
            lvl=("senior" if is_senior_title(tl) else
                 "student" if is_student_title(tl) else "open")
            giant.append(_bucket(j, "giant:"+lvl))
        c=classify(j)
        if not c:
            tl=(j.get("title") or "").lower()
            if (refdigest is not None and company_is(j.get("company"), C.REFERRAL_COMPANIES)
                    and ref_digest_ok(tl, j.get("desc") or "")):
                refdigest.append(_bucket(j, "ref-digest"))   # still bucketed below as before
            # QA-ish titles miss the dev gate -> send to the QA-bucket (not the review-bucket).
            if qa is not None and is_qa(tl):
                qa.append(_bucket(j,"qa:not-dev-title")); continue
            # Otherwise bucket it (for review, NOT the tracker) when it's a giant/referral OR
            # its JD content reads like a real dev role (typos/unusual/Hebrew the gate misses).
            if filtered is not None:
                desc=(j.get("desc") or "").lower()
                nondev=_has(tl, C.DEVSIG_NONDEV) or is_student_title(tl)
                if company_is(j.get("company"), C.GIANTS+C.REFERRAL_COMPANIES):
                    filtered.append(_bucket(j,"not-dev-title"))
                elif not nondev and sum(1 for w in C.DEVSIG if w in desc) >= C.DEVSIG_MIN:
                    filtered.append(_bucket(j,"jd-signal"))   # oddly-titled but JD reads as dev
                elif (not nondev and len(desc.strip()) < 100 and _NO_JD_TITLE.search(tl)
                      and not (is_senior_title(tl) or is_industrial_control(tl)
                               or _has_word(tl, C.FOUNDATION_SKIP))):
                    # no JD to read (Experis = metadata only): an engineer/developer title is
                    # kept for review instead of vanishing ('מהנדס/ת שילובים', 'SW Engineer'...)
                    filtered.append(_bucket(j,"no-jd-title"))
            continue
        # Location filter is Jerusalem+South EXCLUSION only (done above via DROP_REGIONS).
        # "Israel"/no-city -> Unknown is kept: it's Israel and not positively Jer/South.
        if c["lane"]=="skip":
            tl=(j.get("title") or "").lower()
            if qa is not None and is_qa(tl):
                qa.append(_bucket(j,"qa:"+c["why"]))          # manual-QA etc. -> QA-bucket
            elif filtered is not None:
                filtered.append(_bucket(j,c["why"]))          # senior/foundation/student/...
            continue
        if c["lane"]=="review":
            if filtered is not None: filtered.append(_bucket(j,"review:"+c["why"]))
            if j["region"] not in ("North","Unknown"): continue  # Center unclear-seniority: off page, but in bucket
        j["_c"]=c; keep.append(j)
    print("after filter:", len(keep), "| bucket:", len(filtered) if filtered is not None else 0)
    keep=dedup(keep); print("after dedup:", len(keep))
    seen=reg.setdefault("seen",{})
    def _sids(j): return ["%s:%s"%(m["source"],m["sid"]) for m in (j.get("_members") or [j])]
    # Rows already on the tracker (any merged copy's source:sid in seen) register their CURRENT
    # soft key (region-aware / JD-fingerprinted) under their original date, so this run's
    # reposts of them are caught; the old region-less company|title key they were admitted
    # under is then retired (it would hide e.g. a Haifa req behind a Tel Aviv one).
    retired=set()
    for j in keep:
        hit=next((seen[s] for s in _sids(j) if s in seen), None)
        if hit is None: continue
        k=soft_key(j)
        if k: seen.setdefault(k, _soft_value(j, (hit.get("seen") if isinstance(hit, dict) else None) or TODAY))
        lk=_legacy_key(j)
        if lk: retired.add(lk)
    fresh=[]; nsup=0; run_keys={}
    for j in keep:
        if any(s in seen for s in _sids(j)): continue                  # already on the tracker
        k=soft_key(j)
        owner=_soft_block(seen, j, retired)
        if owner is None and k in run_keys:
            # the same key twice in THIS run: a masked repost (same JD), or another board's copy
            src, u = run_keys[k]
            if not norm(j["company"]) or src != j["source"]: owner=u
        if owner is not None:
            # a repost of a role admitted in the last SUPPRESS_DAYS: keep it visible in the
            # review bucket (with the URL that owns the key) instead of letting it vanish
            nsup+=1
            if filtered is not None:
                b=_bucket(j, "dup-suppressed:"+owner if owner else "dup-suppressed")
                b["dup_of"]=owner; filtered.append(b)
            continue
        if k: run_keys.setdefault(k, (j["source"], j.get("url","")))
        fresh.append(j)
    print("fresh (new):", len(fresh), "| dup-suppressed:", nsup)
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
            "openings":{"status":"live","roles":[{"title":m["title"],"url":m["url"]}
                    for m in (j.get("_members") or [{"title":j["title"],"url":j["url"]}])],
                "note":"auto-scan %s | sources:%s | lane:%s | %s%s%s%s"%(TODAY,srcs,c["lane"],
                    "REFERRAL " if c["referral"] else "","GIANT " if c["giant"] else "","TAILOR " if c.get("tailor") else "","ALERT" if alertok else "")}
        })
        entry={"t":j["title"][:60],"lane":c["lane"],"tailor":bool(c.get("tailor")),"seen":TODAY}
        seen["%s:%s"%(j["source"],j["sid"])]=entry
        # the other boards' copies merged into this row are the same role -> seen too
        for m in (j.get("_members") or [])[1:]:
            seen.setdefault("%s:%s"%(m["source"],m["sid"]), dict(entry))
        k=soft_key(j)
        if k: seen[k]=_soft_value(j)
    return rows

def alerts_for(rows):
    return [r for r in rows if "ALERT" in r["openings"]["note"]]

ALERT_BATCH_MAX = 60    # roles sent per run (as 10-role messages, referral first); the rest of a
                        # backfill burst gets one count nudge (they're all on the tracker anyway)
ALERT_QUEUE_MAX = 60    # undelivered roles kept for retry...
ALERT_QUEUE_DAYS = 14   # ...for at most this long
ALERT_FAIL_EXIT = 3     # consecutive failed deliveries -> exit non-zero in CI (workflow failure step fires)

def _alert_item(r):
    """A tracker row (or an already-queued item) -> the small dict notify + the queue need."""
    note=((r.get("openings") or {}).get("note") or "")
    return {"company":r.get("company",""), "role":r.get("role",""), "region":r.get("region",""),
            "url":r.get("url",""), "cv":r.get("cv",""),
            "ref":bool(r.get("ref")) or "REFERRAL" in note, "giant":bool(r.get("giant")) or "GIANT" in note,
            "q":r.get("q") or TODAY}

def _queue_fresh(it):
    try: return (_today() - datetime.date.fromisoformat(it.get("q") or TODAY)).days <= ALERT_QUEUE_DAYS
    except Exception: return True

def send_alerts(rows, reg=None, path=None):
    """Telegram/WhatsApp this run's giant/referral ALERT rows plus any still queued from a
    failed run. Returns how many roles were ACTUALLY delivered. Undelivered roles go to
    reg['alert_queue'] (written back to the registry) and are retried next run, since their
    source:sid is already in `seen` and would otherwise never alert again. After
    ALERT_FAIL_EXIT failed runs in a row it exits non-zero on CI so the failure alert fires.
    `reg`/`path` default to the registry last loaded/saved (cloud_run passes neither)."""
    if os.environ.get("JOBSCAN_NO_ALERT"):
        print("(alerts suppressed via JOBSCAN_NO_ALERT)"); return 0
    delivered=0; streak=0
    try:
        if reg is None and _LAST_REG.get("reg") is not None:
            reg, path = _LAST_REG["reg"], _LAST_REG.get("path")
        queued=[q for q in ((reg or {}).get("alert_queue") or []) if isinstance(q, dict) and _queue_fresh(q)]
        items=[]; urls=set()
        for it in queued + [_alert_item(r) for r in alerts_for(rows)]:
            u=it.get("url") or ""
            if u in urls: continue
            urls.add(u); items.append(it)
        failed=[]; over=[]
        if items:
            items.sort(key=lambda it: 0 if it.get("ref") else 1)     # referral roles first (stable)
            send, over = items[:ALERT_BATCH_MAX], items[ALERT_BATCH_MAX:]
            import notify
            delivered = notify.notify_jobs(send, failed) or 0
            if over:
                notify.notify_text("\U0001F514 JobScan: +%d more new giant/referral roles this run "
                                   "(large batch — see the tracker)" % len(over))
            print("alerted %d/%d giant/referral roles%s" % (delivered, len(send),
                  (" | %d undelivered%s -> queued for retry (max %d)"
                   % (len(failed), (" + %d overflow" % len(over)) if over else "", ALERT_QUEUE_MAX))
                  if failed else ""))
        if reg is not None and (items or reg.get("alert_queue") or reg.get("alert_fail_streak")):
            # a failed run also queues the overflow beyond ALERT_BATCH_MAX (its count nudge most
            # likely failed too); the HEAD is kept, so referral roles survive the cap first
            reg["alert_queue"]=[_alert_item(f) for f in failed + (over if failed else [])][:ALERT_QUEUE_MAX]
            streak = (int(reg.get("alert_fail_streak") or 0) + 1) if failed else 0
            reg["alert_fail_streak"]=streak
            save_reg(reg, path)
    except Exception as e:
        print("notify err", e)
    if streak >= ALERT_FAIL_EXIT and os.environ.get("GITHUB_ACTIONS"):
        print("::error::JobScan: giant/referral alerts undelivered %d runs in a row "
              "(check TELEGRAM_TOKEN / TELEGRAM_CHAT_ID secrets)" % streak)
        raise SystemExit(1)
    return delivered

REF_DIGEST_MAX = 12     # roles per digest message (Telegram's 4096-char cap); the rest roll to the next run
REF_DIGEST_DAYS = 120   # a digested URL is remembered this long
REF_DIGEST_CHARS = 3800 # message budget under Telegram's 4096-char cap (margin for the footer)

def send_ref_digest(items, reg):
    """ONE Telegram message per run listing NEW referral-company roles that missed the title gate
    (select(..., refdigest=...)) - Ron's call #10, 2026-09-24: they used to sit silently in the
    buckets (the Nvlink QA miss). reg['ref_digest'] = {key: date first digested}, keyed by URL
    AND by company|title|region (the same role copied by LinkedIn/BuiltIn is one line). Keys are
    marked only after the message was delivered or permanently rejected, so a failed send is
    retried next run; more than REF_DIGEST_MAX new roles roll over to the next run's digest.
    Returns roles delivered. Never raises."""
    if os.environ.get("JOBSCAN_NO_ALERT"):
        print("(ref digest suppressed via JOBSCAN_NO_ALERT)"); return 0
    try:
        state = reg.get("ref_digest")
        if not isinstance(state, dict): state = reg["ref_digest"] = {}
        cutoff = (_today() - datetime.timedelta(days=REF_DIGEST_DAYS)).isoformat()
        for u in [u for u, d in state.items() if not isinstance(d, str) or d < cutoff]:
            del state[u]
        def _keys(it):
            t = digest_title_key(it.get("company"), it.get("role"))
            ks = [(it.get("url") or "").strip(), "t:%s|%s" % (t, it.get("region") or ""), "t:%s|*" % t]
            # every copy MARKS the region-less key, but only an Unknown-region copy (a '2 Locations'
            # placeholder) is BLOCKED by it: per-site reqs with one title stay separate lines
            return ks, (ks if (it.get("region") or "Unknown") == "Unknown" else ks[:2])
        new = []; run = set()
        for it in sorted(items, key=lambda it: (it.get("region") or "Unknown") == "Unknown"):   # Unknown last
            ks, check = _keys(it)
            if not ks[0] or any(k in state or k in run for k in check): continue
            run.update(ks); new.append(it)
        if not new:
            print("ref digest: nothing new"); return 0
        import notify
        if not notify.configured():
            print("ref digest: no channel configured - %d role(s) wait for the next run" % len(new)); return 0
        lines = ["\U0001F514 JobScan referral digest: %d new role%s at your referral companies that the title "
                 "filter doesn't cover - worth a look:" % (len(new), "" if len(new) == 1 else "s")]
        send = []; total = len(lines[0])
        for it in new[:REF_DIGEST_MAX]:
            ln = "• %s — %s [%s]\n%s" % ((it.get("company") or "")[:30], (it.get("role") or "")[:70],
                                         it.get("region") or "?", (it.get("url") or "")[:400])
            if send and total + 1 + len(ln) > REF_DIGEST_CHARS:
                break                                  # Telegram's 4096 cap: the rest go next run
            send.append(it); lines.append(ln); total += 1 + len(ln)
        rest = len(new) - len(send)
        if rest: lines.append("+%d more in the next run's digest" % rest)
        ok = notify._send("\n".join(lines))     # True sent / False retry later / None rejected
        if ok is False:
            print("ref digest: delivery failed - %d role(s) retried next run" % len(send)); return 0
        for it in send:
            for k in _keys(it)[0]: state[k] = TODAY
        print("ref digest: %s %d role(s)%s" % ("sent" if ok else "REJECTED by the channel (marked, not retried):",
                                               len(send), (", %d wait for the next run" % rest) if rest else ""))
        return len(send) if ok else 0
    except Exception as e:
        print("ref digest err:", e); return 0

# ---------------- main (LOCAL: writes Desktop tracker) ----------------
def main():
    print("JobScan run %s" % TODAY)
    reg=load_reg()
    rows=select(collect(), reg)
    if rows:
        total=append_tracker(rows); print("appended %d rows -> tracker now %d"%(len(rows),total))
    save_reg(reg)
    send_alerts(rows, reg)   # re-saves reg with the alert retry queue
    return rows

if __name__=="__main__":
    main()
