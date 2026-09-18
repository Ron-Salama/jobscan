"""Compatibility collectors only. Filtering and storage live in radar/."""
import json, re, time, urllib.request, urllib.parse
import config as C
UA = "JobRadar/2.0 (personal job discovery)"

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
    from radar.engine import regions_of
    return regions_of(city)[0]

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
            out[-1]["posted_at"]=j.get("posted_date","")
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
        out[-1]["posted_at"]=j.get("posted_date","")
    return out

SOURCES = [("hiremetech",src_hiremetech),("experis",src_experis),("drushim",src_drushim),
           ("greenhouse",src_greenhouse),("amazon",src_amazon)]

