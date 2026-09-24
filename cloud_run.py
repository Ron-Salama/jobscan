# -*- coding: utf-8 -*-
"""
Cloud entry for JobScan (GitHub Actions). Same scan pipeline as jobscan.py, but writes:
  - data/jobs.json (accumulated, deduped via data/seen.json)
  - docs/index.html (self-contained filterable web tracker, served by GitHub Pages)
  - Telegram/WhatsApp alerts on new giant/referral roles (secrets from env).
The workflow commits data/ + docs/ back after each run.

  python cloud_run.py                 full scan: collect -> select -> curate -> page -> alerts
  python cloud_run.py --rebuild-only  NO network: re-apply data/curation.json to the existing
                                      data/jobs.json and rebuild docs/index.html. No alerts;
                                      seen.json and the bucket files are left untouched.
                                      (scan.yml runs this on every push to data/curation.json.)
"""
import os, sys, json, re, datetime
from collections import Counter
from urllib.parse import urlparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jobscan as J   # sets utf-8 stdout via reconfigure
import config as C

DATA = "data"; DOCS = "docs"
JOBS_JSON = os.path.join(DATA, "jobs.json")
SEEN_JSON = os.path.join(DATA, "seen.json")
BUCKET_JSON = os.path.join(DATA, "review-bucket.json")   # filtered/uncertain roles for later manual/AI review
QA_JSON = os.path.join(DATA, "qa-bucket.json")           # QA-ish roles set aside for review (real test-eng vs manual-QA)
GIANT_JSON = os.path.join(DATA, "giant-bucket.json")     # EVERY giant-company role (all levels) - peace-of-mind catch-all for manual review
CURATION_JSON = os.path.join(DATA, "curation.json")   # Claude's persistent judgment overlay (verdicts + jobify roles)
INDEX_HTML = os.path.join(DOCS, "index.html")
CAP = 1200                # page rows; applied AFTER curation and never evicts judged/tailor-ready/statused rows
BUCKET_CAP = 500          # review + QA bucket rows kept (the giant bucket is NOT capped: every giant role is kept)
SOURCE_DARK_MIN = 5       # a source that once returned >= this, now 0/error = "went dark"
SOURCE_PARTIAL = 0.3      # ...or now returns < 30% of its best run = partial outage (a board/tenant/search died)
SOURCE_ZERO_RUNS = 3      # a source that has returned 0 rows on this many runs in a row, and never more
STALE_HOURS = 6           # the page shows 'last scan N h ago' in red after this many hours
TZ_NAME = "Asia/Jerusalem"
DEAD_HOSTS = ("cps.co.il", "techjob.co.il")
KEEP_STATUSES = ("Sent", "Interview")   # Ron's own applications: never dropped by the NO / dead-host filters

def slim(r):
    note = r["openings"]["note"]
    return {
        "date": r["sector"].replace("auto ", ""),
        "region": r["region"], "fit": r["fit"],
        "company": r["company"], "role": r["role"], "loc": r["location"], "url": r["url"],
        "cv": r["cv"].replace("Ron Salama - CV (", "").replace(").pdf", ""),
        "ref": "REFERRAL" in note, "giant": "GIANT" in note, "tailor": "TAILOR" in note,
        "unread": "·unread" in r["blurb"], "alert": "ALERT" in note,
        "src": note.split("sources:")[1].split("|")[0].strip() if "sources:" in note else "",
    }

PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Ron — Job Radar</title>
<style>
:root{color-scheme:dark}
*{box-sizing:border-box}
body{font:14px/1.5 system-ui,Segoe UI,Arial,sans-serif;margin:0;background:#0f1115;color:#e7e9ee}
header{padding:12px 16px;background:#161a22;border-bottom:1px solid #262c38;position:sticky;top:0;z-index:5}
h1{font-size:17px;margin:0 0 6px}
.meta{color:#96a0b5;font-size:12px}
.controls{display:flex;flex-wrap:wrap;gap:8px;margin-top:9px;align-items:center}
.controls input[type=text],.controls select{background:#0f1115;color:#e7e9ee;border:1px solid #2b3240;border-radius:8px;padding:6px 9px;font-size:13px}
.controls label{display:flex;align-items:center;gap:5px;color:#c3cad8;font-size:12px}
main{padding:10px 12px}
table{border-collapse:collapse;width:100%}
th,td{text-align:left;padding:7px 9px;border-bottom:1px solid #20262f;vertical-align:top}
th{color:#96a0b5;font-size:11px;text-transform:uppercase;letter-spacing:.04em;cursor:pointer;position:sticky;top:0;background:#161a22}
tr:hover td{background:#151a22}
tr.done td{opacity:.4}
a{color:#7db4ff;text-decoration:none}a:hover{text-decoration:underline}
.pill{display:inline-block;padding:1px 7px;border-radius:999px;font-size:11px;font-weight:600;white-space:nowrap}
.ref{background:#3a1d2b;color:#ff9ec4}.giant{background:#20344a;color:#8fc7ff}.tailor{background:#3a331a;color:#ffd98f}
.toppick{background:#14432a;color:#7cf0a8;font-weight:700}.wtailor{background:#3a331a;color:#ffd98f}
.unread{background:#2a2f3a;color:#9aa6bb}
.tready{background:#123a3a;color:#7fe9d6;font-weight:700}
.v-yes{background:#1c3a2a;color:#8ff0b8}.v-reach{background:#3a331a;color:#ffd98f}.v-no{background:#3a1d1d;color:#ff9e9e}
.jbf{background:#20344a;color:#8fc7ff}
tr.filtered td{opacity:.45}
.n{background:#1c3a2a;color:#8ff0b8}.c{background:#2a2340;color:#c4b0ff}
.u{background:transparent;color:#9aa6bb;border:1px dashed #4a5366}
.stale{color:#ff6b6b;font-weight:700}
.fit5{color:#8ff0b8;font-weight:700}.fit4{color:#c9e69a}.fit3{color:#e6c78a}
.mwrap{display:flex;align-items:center;gap:6px;min-width:92px}
.mbar{flex:1;height:7px;border-radius:4px;background:#20262f;overflow:hidden}
.mfill{height:100%;border-radius:4px}
.mnum{font-variant-numeric:tabular-nums;font-weight:700;font-size:12px;width:26px;text-align:right}
.tbtn{background:#20344a;color:#8fc7ff;border:1px solid #2b3240;border-radius:8px;padding:6px 10px;font-size:12px;cursor:pointer}
.tbtn:hover{background:#274058}
.muted{color:#8792a6;font-size:12px}
select.st{background:#0f1115;color:#e7e9ee;border:1px solid #2b3240;border-radius:6px;padding:3px 5px;font-size:12px}
select.st[data-v="Sent"]{border-color:#3a7d52;color:#8ff0b8}
select.st[data-v="Interview"]{border-color:#7d6a2a;color:#ffd98f}
select.st[data-v="Skip"]{border-color:#5a2a2a;color:#ff9e9e}
input.note{background:#0f1115;color:#e7e9ee;border:1px solid #2b3240;border-radius:6px;padding:3px 6px;font-size:12px;width:150px}
input.note:focus{border-color:#4a7bb5;outline:none;width:230px}
input.note::placeholder{color:#5a6474}
input.note.has{border-color:#3a7d52}
</style></head><body>
<header>
  <h1>🎯 Ron — Job Radar <span class="meta" id="updated"></span> <span class="meta" id="lastscan"></span></h1>
  <div class="meta" id="count"></div>
  <div class="controls">
    <input type="text" id="q" placeholder="search company / role…" size="20">
    <select id="date"><option value="">all pulls</option></select>
    <select id="region"><option value="">all regions</option><option>North</option><option value="North+Unknown">North + Unknown</option><option>Center</option><option>Unknown</option></select>
    <select id="fit"><option value="0">match ≥ any</option><option value="85">match ≥ 85</option><option value="70">match ≥ 70</option><option value="55">match ≥ 55</option></select>
    <select id="verdict"><option value="">any verdict</option><option>YES</option><option>REACH</option><option value="_none">unrated</option></select>
    <select id="status"><option value="">any status</option><option>New</option><option>Sent</option><option>Interview</option><option>Skip</option></select>
    <label><input type="checkbox" id="refonly"> 🔔 referral</label>
    <label><input type="checkbox" id="toponly"> 🏆 top picks</label>
    <label><input type="checkbox" id="tailoronly"> ✎ worth tailoring</label>
    <label><input type="checkbox" id="treadyonly"> 🎯 tailor-ready</label>
    <label><input type="checkbox" id="jobifyonly"> Jobify</label>
    <label><input type="checkbox" id="hidedone" checked> hide sent/skip</label>
    <button type="button" id="expBtn" class="tbtn" title="Download your applied/status marks (this browser) as a file">⬇ export status</button>
    <label class="tbtn" title="Load a status file exported from another device">⬆ import status<input type="file" id="impFile" accept="application/json" hidden></label>
  </div>
</header>
<main><table id="t"><thead><tr>
<th data-k="date">Pull</th><th data-k="match">Match</th><th data-k="verdict">Verdict</th><th data-k="region">Region</th>
<th data-k="flags">Flags</th><th data-k="company">Company</th><th data-k="role">Role</th>
<th data-k="cv">CV</th><th data-k="src">Src</th><th>Status</th><th>Open</th><th>Notes</th>
</tr></thead><tbody id="b"></tbody></table></main>
<script>
const JOBS = __DATA__;
const STATUSES = __STATUSES__;  /* Ron's applied/skip marks (global default; a local change overrides) */
const NOTES = __NOTES__;  /* per-role free-text notes (global default; a local edit overrides) */
const SCAN = __SCAN__;  /* last real scan: {iso, label} in Israel time (a --rebuild-only run keeps it) */
document.getElementById("updated").textContent = "· updated __UPDATED__";
let sortK="match", sortDir=-1;
const el=id=>document.getElementById(id);
function scanAge(){const e=el("lastscan");if(!SCAN||!SCAN.iso){e.textContent="";return;}
  const t=Date.parse(SCAN.iso);e.title="last scan "+(SCAN.label||SCAN.iso);
  if(isNaN(t)){e.textContent="· last scan "+(SCAN.label||SCAN.iso);return;}
  const h=Math.max(0,(Date.now()-t)/3.6e6);e.textContent="· last scan "+(h<1?"<1":Math.floor(h))+" h ago";
  e.classList.toggle("stale",h>__STALEH__);}
scanAge();setInterval(scanAge,60000);
/* unrated rows (no judged match score) get a capped ESTIMATE from the rule fit, so they never
   outrank judged YES roles; the meter is greyed with a '~' so it can't pass for a real score.
   The 'match >=' filter applies to judged rows only (an estimate is not a match); unrated rows
   are isolated with the 'unrated' verdict option instead. */
const rated=j=>j.match!=null;
const mval=j=>rated(j)?j.match:Math.min(j.fit?Math.round(j.fit*18):50,65);
const tpk=j=>j.verdict==="YES"&&mval(j)>=90;const wt=j=>j.verdict==="YES"&&mval(j)<90;
function mmeter(j){const m=mval(j);
  if(!rated(j))return '<div class="mwrap" title="unrated — estimate from the rule fit, not a judged match"><div class="mbar"><div class="mfill" style="width:'+m+'%;background:#4a5366"></div></div><span class="mnum" style="color:#8792a6">~'+m+'</span></div>';
  const c=m>=70?'#8ff0b8':m>=45?'#ffd98f':'#ff9e9e';return '<div class="mwrap"><div class="mbar"><div class="mfill" style="width:'+m+'%;background:'+c+'"></div></div><span class="mnum" style="color:'+c+'">'+m+'</span></div>';}
const rgOk=(j,rg)=>!rg||(rg==="North+Unknown"?(j.region==="North"||j.region==="Unknown"):j.region===rg);
function esc(s){return (s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");}
function getSt(u){try{const l=localStorage.getItem("st:"+u);if(l)return l;}catch(e){} return (STATUSES&&STATUSES[u])||"New";}
function setSt(u,v){try{localStorage.setItem("st:"+u,v);}catch(e){}}
function getNote(u){try{const l=localStorage.getItem("nt:"+u);if(l!==null)return l;}catch(e){} return (NOTES&&NOTES[u])||"";}
function setNote(u,v){try{localStorage.setItem("nt:"+u,v);}catch(e){}}
function pills(j){let s="";if(tpk(j))s+='<span class="pill toppick">🏆 TOP PICK</span> ';else if(wt(j))s+='<span class="pill wtailor">✎ worth tailoring</span> ';if(j.tailor_ready)s+='<span class="pill tready" title="triaged - ready to tailor (base: '+esc(j.tready_base||'')+')">🎯 tailor-ready</span> ';if(j.jobify)s+='<span class="pill jbf">Jobify</span> ';if(j.rescued)s+='<span class="pill jbf" title="rescued from the review bucket">🪣bucket</span> ';if(j.ref)s+='<span class="pill ref">🔔REF</span> ';if(j.giant)s+='<span class="pill giant">★giant</span> ';if(j.unread)s+='<span class="pill unread">·unread</span> ';return s;}
function vpill(j){const v=j.verdict||"";if(!v)return '<span class="muted">–</span>';const cls=v==="YES"?"v-yes":v==="REACH"?"v-reach":"v-no";const b=j.vbasis==="jd"?" ✓":j.vbasis==="title"?" ·":"";const tip=(j.vwhy||"")+(j.vbasis?" ["+(j.vbasis==="jd"?"read the JD":"title only — JD hidden")+"]":"");return '<span class="pill '+cls+'" title="'+esc(tip)+'">'+v+b+'</span>';}
// populate the pull/date dropdown
const fmtD=d=>{if(!d||d.indexOf("-")<0)return d||"";const p=d.split("-");return p[2]+"/"+p[1]+"/"+p[0];};
const dcount={}; JOBS.forEach(j=>{dcount[j.date]=(dcount[j.date]||0)+1;});
[...new Set(JOBS.map(j=>j.date))].sort().reverse().forEach(d=>{const o=document.createElement("option");o.value=d;o.textContent=fmtD(d)+" pull ("+(dcount[d]||0)+")";el("date").appendChild(o);});
function exportStatuses(){
  const data={},notes={}; for(let i=0;i<localStorage.length;i++){const k=localStorage.key(i); if(!k)continue;
    if(k.indexOf("st:")===0) data[k.slice(3)]=localStorage.getItem(k);
    else if(k.indexOf("nt:")===0){const v=localStorage.getItem(k); if(v) notes[k.slice(3)]=v;}}
  const n=Object.keys(data).length, m=Object.keys(notes).length;
  const blob=new Blob([JSON.stringify({version:1,exported:new Date().toISOString(),count:n,statuses:data,notes:notes})],{type:"application/json"});
  const a=document.createElement("a"); a.href=URL.createObjectURL(blob);
  a.download="jobscan-status-"+new Date().toISOString().slice(0,10)+".json"; a.click();
}
function importStatuses(file){
  const r=new FileReader();
  r.onload=e=>{try{
    const d=JSON.parse(e.target.result); const st=d.statuses||d.by_url||d; let n=0,skip=0;
    for(const u in st){const v=st[u]; if(!v) continue;
      const cur=localStorage.getItem("st:"+u);
      if(cur&&cur!=="New"&&cur!==v){skip++;continue;}   // don't overwrite an existing decision on this device
      if(v!=="New"){localStorage.setItem("st:"+u,v); n++;}}
    const nt=d.notes||{}; let nn=0;
    for(const u in nt){const v=nt[u]; if(!v) continue;
      const curn=localStorage.getItem("nt:"+u);
      if(curn&&curn!==v){continue;}                     // don't clobber a note already written on this device
      localStorage.setItem("nt:"+u,v); nn++;}
    render(); alert("Imported "+n+" status marks"+(nn?" and "+nn+" notes":"")+(skip?"; kept "+skip+" you'd already set here":"")+".");
  }catch(err){alert("Import failed: "+err.message);}};
  r.readAsText(file);
}
function stChange(sel){setSt(sel.dataset.u, sel.value);render();}
window.stChange=stChange;
function ntChange(inp){setNote(inp.dataset.u, inp.value);inp.classList.toggle("has",!!inp.value);}
window.ntChange=ntChange;
function render(){
  const q=el("q").value.toLowerCase(),dt=el("date").value,rg=el("region").value,mf=+el("fit").value,
        st=el("status").value,ro=el("refonly").checked,to=el("tailoronly").checked,hd=el("hidedone").checked,
        vd=el("verdict").value,jo=el("jobifyonly").checked,tp=el("toponly").checked,tr=el("treadyonly").checked;
  let rows=JOBS.filter(j=>{
    const s=getSt(j.url);
    const vmatch = !vd || (vd==="_none" ? !j.verdict : j.verdict===vd);
    return (!q||((j.company||"")+" "+(j.role||"")).toLowerCase().includes(q))&&(!dt||j.date===dt)&&rgOk(j,rg)
      &&(!rated(j)||mval(j)>=mf)&&vmatch&&(!jo||j.jobify)&&(!st||s===st)&&(!ro||j.ref)&&(!to||wt(j))&&(!tp||tpk(j))&&(!tr||j.tailor_ready)&&(!hd||(s!=="Sent"&&s!=="Skip"));
  });
  rows.sort((a,b)=>{let x=a[sortK],y=b[sortK];if(sortK==="flags"){x=(a.ref?2:0)+(a.giant?1:0);y=(b.ref?2:0)+(b.giant?1:0);}else if(sortK==="match"){x=mval(a);y=mval(b);}return (x>y?1:x<y?-1:0)*sortDir;});
  el("count").textContent=rows.length+" of "+JOBS.length+" roles";
  el("b").innerHTML=rows.map(j=>{const s=getSt(j.url);const opts=["New","Sent","Interview","Skip"].map(o=>`<option${o===s?" selected":""}>${o}</option>`).join("");
    return `<tr class="${(s==='Sent'||s==='Skip')?'done':''} ${j.verdict==='NO'?'filtered':''}">
    <td class="muted">${esc(fmtD(j.date))}</td>
    <td>${mmeter(j)}</td>
    <td>${vpill(j)}</td>
    <td><span class="pill ${j.region==='North'?'n':j.region==='Unknown'?'u':'c'}">${esc(j.region)}</span></td>
    <td>${pills(j)}</td>
    <td>${esc(j.company)}</td>
    <td>${esc(j.role)}${j.loc?' <span class="muted">· '+esc(j.loc)+'</span>':''}</td>
    <td class="muted">${esc(j.cv)}</td>
    <td class="muted">${esc(j.src)}</td>
    <td><select class="st" data-v="${s}" data-u="${esc(j.url)}" onchange="stChange(this)">${opts}</select></td>
    <td>${j.url?'<a href="'+esc(j.url)+'" target="_blank" rel="noopener">open ↗</a>':''}</td>
    <td><input class="note${getNote(j.url)?' has':''}" type="text" data-u="${esc(j.url)}" value="${esc(getNote(j.url))}" placeholder="notes…" oninput="ntChange(this)"></td></tr>`;}).join("");
}
document.querySelectorAll("th[data-k]").forEach(th=>th.onclick=()=>{const k=th.dataset.k;sortDir=(sortK===k)?-sortDir:1;sortK=k;render();});
["q","date","region","fit","verdict","status","refonly","toponly","tailoronly","treadyonly","jobifyonly","hidedone"].forEach(id=>el(id).addEventListener("input",render));
el("expBtn").onclick=exportStatuses;
el("impFile").onchange=e=>{if(e.target.files[0]){importStatuses(e.target.files[0]); e.target.value="";}};
render();
</script></body></html>"""

# ---------------- state files ----------------
def _load_json(path, default):
    """Read a JSON state file. A MISSING file -> `default` (first run). A CORRUPT file raises
    SystemExit, so the run fails (-> the workflow's Telegram failure alert) instead of
    silently treating it as empty and overwriting real state with []/{}."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except ValueError as e:        # JSONDecodeError / UnicodeDecodeError
        raise SystemExit("FATAL: %s is not valid JSON (%s) - refusing to overwrite it" % (path, e))

def _expect(obj, typ, path):
    if not isinstance(obj, typ):
        raise SystemExit("FATAL: %s holds a %s, expected a %s - refusing to overwrite it"
                         % (path, type(obj).__name__, typ.__name__))
    return obj

def load_curation():
    """data/curation.json as a dict ({} when missing; SystemExit when corrupt)."""
    return _expect(_load_json(CURATION_JSON, {}), dict, CURATION_JSON)

def _now_il():
    """Now in Israel time (falls back to UTC if the tz database is unavailable)."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.datetime.now(ZoneInfo(TZ_NAME))
    except Exception:
        return datetime.datetime.now(datetime.timezone.utc)

# ---------------- URL keys ----------------
def _nu(u):
    """Lookup key for a posting URL: '.../job/12474' and '.../job/12474/' are the same posting."""
    return (u or "").strip().rstrip("/") if isinstance(u, str) else ""

_VRANK = {"YES": 3, "REACH": 2, "NO": 1}             # jobify / rescued / tailor_ready: strongest verdict wins
_VRANK_VERDICTS = {"NO": 4, "YES": 3, "REACH": 2}    # verdicts map: a NO is a tombstone and must win
def _norm_map(mp, vrank=None):
    """{url: entry} -> ({key: entry}, {key: canonical url}). On a trailing-slash collision keep the
    higher-ranked verdict per `vrank` (default YES>REACH>NO; the verdicts map passes
    _VRANK_VERDICTS so a NO tombstone beats a YES), then the entry with company/role filled;
    the no-slash spelling is canonical."""
    out, canon = {}, {}
    if not isinstance(mp, dict): return out, canon
    vr = vrank or _VRANK
    for u, v in mp.items():
        k = _nu(u)
        if not k: continue
        if k not in out:
            out[k] = v; canon[k] = u
            continue
        old = out[k]
        def rank(e):
            if not isinstance(e, dict): return (-1, 0)
            return (vr.get((e.get("v") or "").upper(), 0),
                    bool((e.get("company") or "").strip()) + bool((e.get("role") or "").strip()))
        if rank(v) > rank(old): out[k] = v
        if not u.endswith("/"): canon[k] = u
    return out, canon

def _norm_values(mp):
    """{url: str} (statuses / notes) keyed by _nu(url); a real mark beats a 'New' default."""
    out = {}
    if not isinstance(mp, dict): return out
    for u, v in mp.items():
        k = _nu(u)
        if k and (k not in out or out[k] in ("", "New")): out[k] = v
    return out

def _is_no(r):
    return isinstance(r, dict) and (r.get("verdict") or r.get("v") or "").upper() == "NO"

def _dead(r):
    u = r.get("url") or ""
    return any(h in u for h in DEAD_HOSTS)

def _not_a_job(u):
    """Curation entries that are search pages, not postings (render as blank rows)."""
    return "linkedin.com/jobs/search" in (u or "")

def _kept_by_status(r, statuses):
    """Ron applied (Sent) or is interviewing: the row stays whatever the verdict/host says."""
    return statuses.get(_nu(r.get("url"))) in KEEP_STATUSES

# ---------------- company helpers ----------------
def _company_match(company, words):
    """Company-name match. Uses jobscan.company_is() when another pass adds it (stricter
    matching); otherwise the same substring test the scanner uses (J._has)."""
    fn = getattr(J, "company_is", None)
    if fn:
        try: return bool(fn(company or "", words))
        except Exception: pass
    return J._has((company or "").lower(), words)

# job boards / ATS / aggregators: their host is NOT the employer (matched as a whole host label)
_AGG_LABELS = {"hiremetech", "linkedin", "ethosia", "jobify360", "dialog", "gotfriends", "alljobs", "drushim",
               "experis", "nisha", "builtin", "comeet", "greenhouse", "lever", "ashbyhq", "indeed", "glassdoor",
               "jobmaster", "quality-ai", "facebook", "whatsapp", "smartrecruiters", "workable", "breezy",
               "jobvite", "taleo", "icims", "successfactors",
               # HR platforms / placement agencies (review 2026-09-24): never the employer
               "hibob", "qualityai", "sqlink", "jobnet", "adamtotal", "jobkarov", "jobs2"}
# link shorteners / link-in-bio / chat links: the host says nothing about the employer
_AGG_DOMAINS = ("t.me", "bit.ly", "forms.gle", "docs.google.com", "forms.google.com",
                "lnkd.in", "wa.me", "tinyurl.com", "goo.gl", "bitly.com", "linktr.ee")
_HOST_SKIP = {"www", "career", "careers", "jobs", "job", "apply", "boards", "hr", "join", "work", "en", "he", "app"}
_HOST_TLD = {"co", "il", "com", "org", "net", "io", "ai", "gov", "ac", "biz", "info", "tech", "jobs"}
def _company_from_host(url):
    """Employer from the posting's own host, e.g. career.rafael.co.il -> 'Rafael',
    nvidia.wd5.myworkdayjobs.com -> 'Nvidia'. '' for job boards/aggregators."""
    try:
        host = urlparse(url or "").netloc.lower().split(":")[0]
    except Exception:
        return ""
    if not host: return ""
    parts = host.split(".")
    if "myworkdayjobs" in parts:                      # <tenant>.wdN.myworkdayjobs.com
        return parts[0].replace("-", " ").title()
    if _AGG_LABELS & set(parts) or any(host == d or host.endswith("." + d) for d in _AGG_DOMAINS): return ""
    labels = [x for x in parts if x and x not in _HOST_SKIP and x not in _HOST_TLD]
    return labels[0].replace("-", " ").title() if labels else ""

# ---------------- page ----------------
def _js(obj):
    """JSON for embedding inside <script> ('</' can't close the script tag early)."""
    return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")

def build_page(jobs, updated, cur=None, last_scan=None):
    """Write docs/index.html. `cur` = loaded curation.json (read here when not given);
    `last_scan` = ISO timestamp of the last real scan (Israel time) for the staleness label."""
    os.makedirs(DOCS, exist_ok=True)
    if cur is None: cur = load_curation()
    statuses = cur.get("statuses") if isinstance(cur.get("statuses"), dict) else {}
    notes = cur.get("notes") if isinstance(cur.get("notes"), dict) else {}
    # a status/note stored under the other trailing-'/' spelling still reaches its row
    st_n, nt_n = _norm_values(statuses), _norm_values(notes)
    statuses = dict(statuses); notes = dict(notes)
    for r in jobs:
        u = r.get("url") or ""; k = _nu(u)
        if u and u not in statuses and k in st_n: statuses[u] = st_n[k]
        if u and u not in notes and k in nt_n: notes[u] = nt_n[k]
    scan = {}
    if last_scan:
        label = last_scan
        try:
            dt = datetime.datetime.fromisoformat(last_scan)
            label = dt.strftime("%Y-%m-%d %H:%M") + (" Israel time" if dt.utcoffset() else " UTC")
        except Exception:
            pass
        scan = {"iso": last_scan, "label": label}
    html = (PAGE.replace("__UPDATED__", updated)          # small placeholders first, the data blob last,
                .replace("__STALEH__", str(STALE_HOURS))  # so text inside the data can't be mistaken
                .replace("__SCAN__", _js(scan))           # for a placeholder
                .replace("__NOTES__", _js(notes))
                .replace("__STATUSES__", _js(statuses))
                .replace("__DATA__", _js(jobs)))
    J.atomic_write(INDEX_HTML, html)

def check_sources_dark(reg, counts):
    """Source-health alarm: compare each source's yield with its own history
    (seen.json source_stats) and flag a silent mass-miss:
      dark    - it used to return >= SOURCE_DARK_MIN rows, now 0 / error
      partial - it now returns < SOURCE_PARTIAL x its best run (a board/tenant/search lane died)
      never   - it returned 0 on SOURCE_ZERO_RUNS runs in a row and has never returned a row
    Always printed; each issue ('<source>:<kind>') is sent to Telegram at most ONCE per (Israel)
    day (reg['source_alerts_sent'] = {day, keys}), so a second source going dark later the same
    day still alerts. Returns [(name, kind, prev_max, n)]."""
    stats = reg.setdefault("source_stats", {})
    issues = []
    for name, n in counts.items():
        s = stats.setdefault(name, {"max": 0})
        if not isinstance(s, dict): s = stats[name] = {"max": 0}
        prev_max = s.get("max") or 0
        if isinstance(n, int) and n > prev_max: s["max"] = n
        s["last"] = n
        ok = isinstance(n, int) and n > 0
        if (s.get("max") or 0) <= 0 and not ok: s["zero_runs"] = (s.get("zero_runs") or 0) + 1
        else: s.pop("zero_runs", None)
        if prev_max >= SOURCE_DARK_MIN and not ok:
            issues.append((name, "dark", prev_max, n))
        elif prev_max >= SOURCE_DARK_MIN and n < SOURCE_PARTIAL * prev_max:
            issues.append((name, "partial", prev_max, n))
        elif (s.get("zero_runs") or 0) >= SOURCE_ZERO_RUNS:
            issues.append((name, "never", prev_max, n))
    if issues:
        def one(nm, kind, mx, n):
            if kind == "dark": return "%s went dark (usually ~%d, now %s)" % (nm, mx, "error" if n == -1 else n)
            if kind == "partial": return "%s partial (%d vs best %d)" % (nm, n, mx)
            return "%s never returned a row (%d runs)" % (nm, stats[nm].get("zero_runs", 0))
        msg = "⚠️ JobScan source health — " + "; ".join(one(*i) for i in issues)
        print(msg)
        today = _now_il().date().isoformat()
        sent = reg.get("source_alerts_sent")
        if not isinstance(sent, dict) or sent.get("day") != today or not isinstance(sent.get("keys"), list):
            sent = {"day": today, "keys": []}
        reg.pop("source_alert_day", None)          # the old once-a-day-for-everything marker
        todo = [i for i in issues if "%s:%s" % (i[0], i[1]) not in sent["keys"]]
        if os.environ.get("JOBSCAN_NO_ALERT"):
            print("(source alert suppressed via JOBSCAN_NO_ALERT)")
        elif not todo:
            print("(every source issue was already alerted today - not re-sent)")
        else:
            try:
                import notify
                if notify.notify_text("⚠️ JobScan source health — " + "; ".join(one(*i) for i in todo)):
                    sent["keys"].extend("%s:%s" % (i[0], i[1]) for i in todo)
                    reg["source_alerts_sent"] = sent
            except Exception as e: print("notify err", e)
    return issues

def divergent_verdicts(verdicts, jobify, rescued, show=True):
    """URLs whose verdict 'v' differs across the three curation maps (e.g. a NO in verdicts but
    YES in jobify). `verdicts` always wins; the list is printed so the maps can be reconciled."""
    diff = []
    for k in sorted(set(verdicts) | set(jobify) | set(rescued)):
        vs = {}
        for nm, mp in (("verdicts", verdicts), ("jobify", jobify), ("rescued", rescued)):
            e = mp.get(k)
            if isinstance(e, dict): vs[nm] = (e.get("v") or "").upper()
        if len(set(vs.values())) > 1: diff.append((k, vs))
    if diff and show:
        print("curation: %d URL(s) have a different verdict across verdicts/jobify/rescued (verdicts wins):" % len(diff))
        for k, vs in diff:
            print("   %-40s %s" % (" ".join("%s=%s" % (nm, v or "-") for nm, v in vs.items()), k))
    return diff

_SPECIFIC_REGIONS = ("North", "South", "Jerusalem", "Abroad")
def _entry_region(v):
    """(derived, effective) region of a curation entry. derived = region_of(loc + role) (a role
    like 'Developer (Beer Sheva)' names its place); effective = the stored region, unless it is
    missing / 'Unknown' / 'Center' and the derived one is specific (North/South/Jerusalem/Abroad).
    A bare role reads as 'Center' in region_of, so a derived Center never overrides.
    effective is '' when the entry stores no region and names no specific place."""
    stored = v.get("region") if isinstance(v.get("region"), str) else ""
    stored = stored.strip()
    rg = ""
    fn = getattr(J, "region_of", None)
    if fn:
        try: rg = fn(((v.get("loc") or "") + " " + (v.get("role") or "")).strip())
        except Exception: rg = ""
    if stored in ("", "Unknown", "Center") and rg in _SPECIFIC_REGIONS:
        return rg, rg
    return rg, stored

def _overlay_meta(r, meta):
    """curation.json company/role/region onto a row (BUG 20). A curated (injected) row follows its
    curation entry, so fixes made there reach the page; a scanned row only gets its blanks, masked
    employer or Unknown region filled - the scanner's own data is never overwritten.
    A curated row's region is the entry's EFFECTIVE region (_entry_region), the same one it was
    injected with, so a stale stored 'Center'/'Unknown' can't undo a place named in loc/role."""
    curated = r.get("src") in ("jobify", "bucket")
    for f in ("company", "role", "region", "loc", "cv"):
        if f in ("loc", "cv") and not curated: continue
        val = _entry_region(meta)[1] if (f == "region" and curated) else meta.get(f)
        val = val.strip() if isinstance(val, str) else ""
        if not val or (f == "company" and val == "(masked)"): continue
        if f == "region" and val == "Unknown" and not curated: continue
        rv = r.get(f) if isinstance(r.get(f), str) else ""
        if curated or not rv.strip() or rv == "(masked)" or (f == "region" and rv == "Unknown"):
            r[f] = val

def apply_curation(alljobs, cur=None):
    """Overlay Claude's persistent verdicts (data/curation.json) onto the rows, inject the curated
    roles (jobify / rescued) that aren't present, then refresh every row's metadata + flags.
    Runs every scan (and in --rebuild-only) so a manual judgment pass is never wiped by the
    auto-refresh. Mutates `alljobs`; returns the curation dict. Only a CORRUPT curation.json
    raises (a missing one is a no-op overlay)."""
    if cur is None: cur = load_curation()
    verdicts, _ = _norm_map(cur.get("verdicts"), _VRANK_VERDICTS)   # NO tombstone wins a '/' collision
    jobify, jcanon = _norm_map(cur.get("jobify"))
    rescued, rcanon = _norm_map(cur.get("rescued"))
    tready, _ = _norm_map(cur.get("tailor_ready"))   # roles Claude has triaged + picked a base CV for (badge 🎯)
    statuses = _norm_values(cur.get("statuses"))
    divergent_verdicts(verdicts, jobify, rescued)
    have = {_nu(r.get("url")) for r in alljobs}
    # roles not on the tracker but in an injected map -> add them.
    #   jobify: from Ron's Jobify feed | bucket: rescued by Claude from the review bucket
    # The verdicts map is consulted FIRST: a NO there is a tombstone, so the role is not
    # re-injected from a stale jobify/rescued YES/REACH (BUG 1) - unless Ron applied to it.
    skipped_no = skipped_rg = 0
    for src, mp, canon, tag in (("jobify", jobify, jcanon, "jobify"), ("bucket", rescued, rcanon, "rescued")):
        for k, v in mp.items():
            if k in have or not isinstance(v, dict) or _not_a_job(k): continue
            vd = verdicts.get(k)
            if not isinstance(vd, dict): vd = v
            if _is_no(vd) and statuses.get(k) not in KEEP_STATUSES:
                skipped_no += 1; continue
            # the same region rule as the scanner: a South/Jerusalem/abroad role (by its loc or
            # the place in its role text) is not injected - unless Ron applied to it
            rg, region = _entry_region(v)
            if rg in C.DROP_REGIONS and statuses.get(k) not in KEEP_STATUSES:
                skipped_rg += 1; continue
            have.add(k)
            vv = (vd.get("v") or "").upper()
            score = vd.get("score") if vd.get("score") is not None else v.get("score")
            alljobs.append({
                "date": v.get("date") or cur.get("updated") or J.TODAY, "region": region or "Unknown",
                "fit": {"YES": 5, "REACH": 4}.get(vv, 4), "match": score if score is not None else 60,
                "company": v.get("company", ""), "role": v.get("role", ""), "loc": v.get("loc", ""),
                "url": canon.get(k, k), "cv": v.get("cv", ""), "ref": bool(v.get("ref")), "giant": bool(v.get("giant")),
                "tailor": False, "unread": False, "alert": False, "src": src,
                "verdict": vd.get("v", ""), "vwhy": vd.get("why", ""), "vbasis": vd.get("basis") or "title",
                tag: True})
    if skipped_no:
        print("curation: %d jobify/rescued role(s) not injected - NO in verdicts" % skipped_no)
    if skipped_rg:
        print("curation: %d jobify/rescued role(s) not injected - region in %s"
              % (skipped_rg, "/".join(sorted(C.DROP_REGIONS))))
    pick_cv = getattr(J, "pick_cv", None)
    # overlay pass over EVERY row, re-injected ones included (tailor_ready used to miss those)
    for r in alljobs:
        k = _nu(r.get("url"))
        vd = verdicts.get(k) or jobify.get(k) or rescued.get(k)
        if isinstance(vd, dict):
            r["verdict"] = vd.get("v", ""); r["vwhy"] = vd.get("why", ""); r["vbasis"] = vd.get("basis", "")
            if vd.get("score") is not None: r["match"] = vd.get("score")
        if k and k in jobify:
            r["jobify"] = True
        meta = jobify.get(k) or rescued.get(k)
        if isinstance(meta, dict):
            _overlay_meta(r, meta)
        if pick_cv and not (r.get("cv") or "").strip():
            # an injected role with no cv in its entry (or an old row) gets the title-based pick
            try: r["cv"] = pick_cv(r.get("role") or "", "") or ""
            except Exception: pass
        tr = tready.get(k)
        if isinstance(tr, dict):
            r["tailor_ready"] = True; r["tready_base"] = tr.get("base", "")
            emp = tr.get("emp", "")
            if emp and (not r.get("company") or r.get("company") in ("", "(masked)")):
                r["company"] = emp   # unmask: employer is named in the JD body
            if tr.get("region") and r.get("region") in ("", "Unknown", None):
                r["region"] = tr["region"]   # fill region the aggregator hid (from the JD)
        if not (r.get("company") or "").strip():
            # e.g. career.rafael.co.il -> 'Rafael'; a job board's host names no employer ->
            # '(masked)', the scanner's own convention for an agency-hidden employer
            r["company"] = _company_from_host(r.get("url")) or "(masked)"
        # flags follow the company name, not whatever was hand-typed into the entry (BUG 20)
        co = r.get("company") or ""
        r["ref"] = bool(r.get("ref")) or _company_match(co, C.REFERRAL_COMPANIES)
        r["giant"] = r["ref"] or bool(r.get("giant")) or _company_match(co, C.GIANTS)
    return cur

# ---------------- page-row housekeeping ----------------
def merge_rows(new, existing):
    """New scan rows first, then the existing page; dedup by URL (trailing '/' ignored) so
    nothing shows twice."""
    seenu = set(); out = []
    for x in list(new) + list(existing):
        if not isinstance(x, dict): continue
        k = _nu(x.get("url"))
        if k and k in seenu: continue
        seenu.add(k); out.append(x)
    return out

_STUDENT_RE = re.compile(r"\b(student|interns?|internship|co-?op|trainee)\b", re.I)
def _is_student_title(title):
    fn = getattr(J, "is_student_title", None)   # added by the rules pass; word-bounded fallback until then
    if fn:
        try: return bool(fn(title or ""))
        except Exception: pass
    t = title or ""
    return bool(_STUDENT_RE.search(t)) or "סטודנט" in t or t.strip().startswith("מתמח")

def _is_senior_title(tl):
    fn = getattr(J, "is_senior_title", None)
    if fn:
        try: return bool(fn(tl))
        except Exception: pass
    return J._has(tl, C.SENIOR_TITLE) or J._has_word(tl, getattr(C, "SENIOR_TITLE_WORDS", []))

def rule_fail(r):
    """Title-level rules an unrated row must still pass (CHANGE 5): the failing rule, or ''."""
    title = r.get("role") or ""; tl = title.lower()
    try:
        if J._has_word(tl, C.FOUNDATION_SKIP): return "foundation-gap"
        if _is_senior_title(tl): return "senior-title"
        if _is_student_title(title): return "student"
        region_of = getattr(J, "region_of", None)
        loc = (r.get("loc") or "").strip()
        if region_of and loc:
            rg = region_of(loc)
            if rg in C.DROP_REGIONS: return "region-" + rg
    except Exception as e:
        print("rule re-check err:", e)
    return ""

def recheck_rules(alljobs, skip_keys, statuses):
    """Re-run today's title rules on EXISTING rows nobody has judged (no verdict, no status,
    not curated/tailor-ready): a row the rules would now reject leaves the page for the review
    bucket (reason 'rule-changed:<rule>') instead of lingering forever. Judged rows are never
    re-checked - a YES/REACH on a 'senior' title is a deliberate override.
    Returns (kept_rows, bucket_entries)."""
    kept, moved = [], []
    for r in alljobs:
        k = _nu(r.get("url"))
        if (k in skip_keys or r.get("verdict") or r.get("tailor_ready")
                or r.get("src") in ("jobify", "bucket") or (statuses.get(k) or "New") != "New"):
            kept.append(r); continue
        why = rule_fail(r)
        if not why:
            kept.append(r); continue
        moved.append({"reason": "rule-changed:" + why, "company": r.get("company", ""), "role": r.get("role", ""),
                      "url": r.get("url", ""), "region": r.get("region", ""), "loc": r.get("loc", ""),
                      "src": r.get("src", ""), "desc": ""})
    return kept, moved

def cap_rows(alljobs, statuses, cap=CAP):
    """Trim the page to `cap` rows AFTER curation (BUG 19). Never evicts a YES/REACH row, a
    tailor-ready row or a row Ron has marked (any status but New); evicts unjudged rows,
    oldest pull first. If the protected rows alone exceed `cap`, all of them are kept.
    Returns (rows, n_evicted)."""
    if len(alljobs) <= cap: return alljobs, 0
    def protected(r):
        return ((r.get("verdict") or "").upper() in ("YES", "REACH") or bool(r.get("tailor_ready"))
                or (statuses.get(_nu(r.get("url"))) or "New") != "New")
    unprot = [i for i, r in enumerate(alljobs) if not protected(r)]
    n = min(len(alljobs) - cap, len(unprot))
    # oldest pull date first; within a date the row further down the list (older) goes first
    evict = set(sorted(unprot, key=lambda i: (str(alljobs[i].get("date") or ""), -i))[:n])
    kept = [r for i, r in enumerate(alljobs) if i not in evict]
    if len(kept) > cap:
        print("WARNING: %d protected rows (YES/REACH/tailor-ready/marked) exceed CAP=%d - all kept" % (len(kept), cap))
    return kept, len(evict)

# ---------------- buckets ----------------
# Order the review bucket by how likely a real miss hides there, so the cap never drops the best
# leads first: review-lane roles, then mis-titled giants, then foundation-gap, then the rest.
_PRI = {"review": 0, "jd-signal": 0, "not-dev-title": 1, "no-jd-title": 1, "rule-changed": 1,
        "foundation-gap": 2, "student": 2, "too-senior-even-w-referral": 3, "dup-suppressed": 3}
_GPRI = {"open": 0, "student": 1, "senior": 2}

def _rtag(reason):
    """Leading tag of a bucket reason: 'review:unclear' -> 'review', 'dup-suppressed: <url>' -> 'dup-suppressed'."""
    m = re.match(r"[A-Za-z0-9_\-]+", reason or "")
    return m.group(0) if m else "?"

def _rkey(reason):
    """Reason for per-reason counts: the full 'tag:sub' reason minus any URL / free text."""
    s = re.split(r"\s|\(|:(?=\s*https?:)|https?:", (reason or "").strip(), maxsplit=1)[0].rstrip(":")
    return s or "?"

def _review_key(b):
    """Junior-marked titles first whatever the reason (CHANGE 4), then by reason priority.
    A student title is not junior ('Undergraduate student developer' has 'graduate' inside)."""
    role = b.get("role") or ""
    jr = J._has(role.lower(), C.JUNIOR_MARK) and not _is_student_title(role)
    return (0 if jr else 1, _PRI.get(_rtag(b.get("reason")), 4))

def finish_bucket(rows, key=None, cap=None, drops=()):
    """Sort -> drop rows whose URL is in one of `drops` [(label, url_keys)] -> dedup by URL ->
    cap. Returns (json_dict, rows_before_cap). The dict carries the per-reason counts
    (count_by_reason over everything produced, dropped_by_reason / dropped_by_cause for what
    was not written) so a truncation is never invisible."""
    rows = [b for b in rows if isinstance(b, dict)]
    ordered = sorted(rows, key=key) if key else list(rows)
    kept, seen = [], set()
    dropped, cause = Counter(), Counter()
    for b in ordered:
        k = _nu(b.get("url"))
        why = next((lbl for lbl, keys in drops if k and k in keys), None)
        if not why and k and k in seen: why = "dup-url"
        if why:
            dropped[_rkey(b.get("reason"))] += 1; cause[why] += 1; continue
        if k: seen.add(k)
        kept.append(b)
    precap = kept
    if cap is not None and len(kept) > cap:
        for b in kept[cap:]: dropped[_rkey(b.get("reason"))] += 1
        cause["cap"] += len(kept) - cap
        kept = kept[:cap]
    return ({"generated": J.TODAY, "count": len(rows), "kept": len(kept),
             "count_by_reason": dict(Counter(_rkey(b.get("reason")) for b in rows).most_common()),
             "dropped_by_reason": dict(dropped.most_common()), "dropped_by_cause": dict(cause),
             "roles": kept}, precap)

def write_buckets(bucket, qa_bucket, giant_bucket, page_rows):
    """review / QA / giant bucket JSONs. Giant: every giant role, uncapped (BUG 17). Review: rows
    already on the page and giant rows already in the giant bucket are dropped, URLs deduped,
    THEN capped. QA: on-page + dedup, then capped."""
    on_page = {_nu(r.get("url")) for r in page_rows} - {""}
    g, _ = finish_bucket(giant_bucket, key=lambda b: _GPRI.get((b.get("reason") or "").split(":")[-1], 3))
    in_giant = {_nu(b.get("url")) for b in g["roles"]} - {""}
    rv, precap = finish_bucket(bucket, key=_review_key, cap=BUCKET_CAP,
                               drops=(("on-page", on_page), ("in-giant-bucket", in_giant)))
    top = sum(1 for b in precap if _rtag(b.get("reason")) in ("review", "jd-signal"))
    if top > BUCKET_CAP:
        print("WARNING: review+jd-signal rows alone (%d) exceed BUCKET_CAP=%d - some are cut" % (top, BUCKET_CAP))
    qa, _ = finish_bucket(qa_bucket, cap=BUCKET_CAP, drops=(("on-page", on_page),))
    J.atomic_write(BUCKET_JSON, json.dumps(rv, ensure_ascii=False))
    J.atomic_write(QA_JSON, json.dumps(qa, ensure_ascii=False))
    J.atomic_write(GIANT_JSON, json.dumps(g, ensure_ascii=False))
    for nm, d in (("review", rv), ("qa", qa), ("giant", g)):
        print("  %-6s bucket: %d produced, %d kept, dropped %s" % (nm, d["count"], d["kept"], d["dropped_by_cause"] or "-"))
    return rv, qa, g

def main(argv=None):
    os.makedirs(DATA, exist_ok=True)
    rebuild = "--rebuild-only" in (sys.argv[1:] if argv is None else list(argv))
    print("JobScan CLOUD %s %s" % ("REBUILD-ONLY (no scan, no alerts)" if rebuild else "run", J.TODAY))
    # Load every state file BEFORE the (slow) scan. A missing file is a fresh start; a corrupt one
    # stops the run here, before seen.json/jobs.json are overwritten or any alert goes out (BUG 18).
    reg = _load_json(SEEN_JSON, None)
    reg = {"seen": {}} if reg is None else _expect(reg, dict, SEEN_JSON)
    reg.setdefault("seen", {})
    existing = _expect(_load_json(JOBS_JSON, []), list, JOBS_JSON)
    cur = load_curation()
    statuses = _norm_values(cur.get("statuses"))
    counts = {}; bucket = []; qa_bucket = []; giant_bucket = []; rows = []
    if not rebuild:
        rows = J.select(J.collect(counts), reg, bucket, qa_bucket, giant_bucket)
    new = [slim(r) for r in rows]
    new_keys = {_nu(x.get("url")) for x in new}
    alljobs = merge_rows(new, existing)
    apply_curation(alljobs, cur)   # overlay Claude's verdicts + inject Jobify roles (survives every scan)
    # drop rejected roles (NO verdicts stay in curation.json as tombstones) + dead-source links.
    # cps.co.il / techjob.co.il were disabled as sources 2026-09-23; their listing URLs redirect to
    # the homepage (verified expired, title-only, no JD), so purge any lingering rows for good.
    # A role Ron applied to (status Sent / Interview) is NEVER dropped here: he keeps tracking it
    # (the page's 'hide sent/skip' toggle can still hide it).
    n0 = len(alljobs)
    alljobs = [r for r in alljobs
               if _kept_by_status(r, statuses)
               or not (_is_no(r) or _dead(r) or _not_a_job(r.get("url")))]
    moved = []
    if not rebuild:   # rules only change with code, and the buckets are only rewritten by a scan
        alljobs, moved = recheck_rules(alljobs, new_keys, statuses)
        bucket = moved + bucket
    alljobs, evicted = cap_rows(alljobs, statuses)
    print("page: %d rows (dropped %d NO/dead-host/non-job, %d rule-changed -> review bucket, %d evicted by CAP=%d)"
          % (len(alljobs), n0 - len(alljobs) - len(moved) - evicted, len(moved), evicted, CAP))
    J.atomic_write(JOBS_JSON, json.dumps(alljobs, ensure_ascii=False))
    if not rebuild:
        # invisible buckets: filtered/uncertain roles + their JD text, for on-demand review
        write_buckets(bucket, qa_bucket, giant_bucket, alljobs)
        check_sources_dark(reg, counts)
        reg["last_scan"] = _now_il().isoformat(timespec="minutes")
        J.save_reg(reg, SEEN_JSON)
    build_page(alljobs, J.TODAY, cur, reg.get("last_scan"))
    print("new:%d  total_on_page:%d  bucket:%d" % (len(new), len(alljobs), len(bucket)))
    if not rebuild:
        # send_alerts raises SystemExit(1) after ALERT_FAIL_EXIT failed deliveries in a row. Exiting
        # here would skip the workflow's Commit step (seen.json + the retry queue unpublished, so the
        # same roles re-alert); instead exit 0, and scan.yml fails the job AFTER committing.
        alert_fail = False
        try:
            J.send_alerts(rows)
        except SystemExit as e:
            alert_fail = True
            print("alerts: send_alerts requested a failing exit (%s) - deferred until after the commit" % (e.code,))
        if alert_fail:
            _gh_output("alert_fail", "1")

def _gh_output(key, val):
    """Append key=val to $GITHUB_OUTPUT (a step output for later workflow steps). No-op locally."""
    path = os.environ.get("GITHUB_OUTPUT")
    if not path: return
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write("%s=%s\n" % (key, val))
    except Exception as e:
        print("GITHUB_OUTPUT write err:", e)

if __name__ == "__main__":
    main()
