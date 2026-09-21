# -*- coding: utf-8 -*-
"""
Cloud entry for JobScan (GitHub Actions). Same scan pipeline as jobscan.py, but writes:
  - data/jobs.json (accumulated, deduped via data/seen.json)
  - docs/index.html (self-contained filterable web tracker, served by GitHub Pages)
  - Telegram/WhatsApp alerts on new giant/referral roles (secrets from env).
The workflow commits data/ + docs/ back after each run.
"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jobscan as J   # sets utf-8 stdout via reconfigure

DATA = "data"; DOCS = "docs"
JOBS_JSON = os.path.join(DATA, "jobs.json")
SEEN_JSON = os.path.join(DATA, "seen.json")
BUCKET_JSON = os.path.join(DATA, "review-bucket.json")   # filtered/uncertain roles for later manual/AI review
INDEX_HTML = os.path.join(DOCS, "index.html")
CAP = 1200
BUCKET_CAP = 500          # newest filtered roles kept for review
SOURCE_DARK_MIN = 5       # a source that once returned >= this, now 0/error = "went dark"

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
.unread{background:#2a2f3a;color:#9aa6bb}
.n{background:#1c3a2a;color:#8ff0b8}.c{background:#2a2340;color:#c4b0ff}
.fit5{color:#8ff0b8;font-weight:700}.fit4{color:#c9e69a}.fit3{color:#e6c78a}
.muted{color:#8792a6;font-size:12px}
select.st{background:#0f1115;color:#e7e9ee;border:1px solid #2b3240;border-radius:6px;padding:3px 5px;font-size:12px}
select.st[data-v="Sent"]{border-color:#3a7d52;color:#8ff0b8}
select.st[data-v="Interview"]{border-color:#7d6a2a;color:#ffd98f}
select.st[data-v="Skip"]{border-color:#5a2a2a;color:#ff9e9e}
</style></head><body>
<header>
  <h1>🎯 Ron — Job Radar <span class="meta" id="updated"></span></h1>
  <div class="meta" id="count"></div>
  <div class="controls">
    <input type="text" id="q" placeholder="search company / role…" size="20">
    <select id="date"><option value="">all pulls</option></select>
    <select id="region"><option value="">all regions</option><option>North</option><option>Center</option></select>
    <select id="fit"><option value="0">fit ≥ any</option><option value="5">fit 5</option><option value="4">fit ≥ 4</option><option value="3">fit ≥ 3</option></select>
    <select id="status"><option value="">any status</option><option>New</option><option>Sent</option><option>Interview</option><option>Skip</option></select>
    <label><input type="checkbox" id="refonly"> 🔔 referral</label>
    <label><input type="checkbox" id="tailoronly"> ✎ tailor</label>
    <label><input type="checkbox" id="hidedone" checked> hide sent/skip</label>
  </div>
</header>
<main><table id="t"><thead><tr>
<th data-k="date">Pull</th><th data-k="fit">Fit</th><th data-k="region">Region</th>
<th data-k="flags">Flags</th><th data-k="company">Company</th><th data-k="role">Role</th>
<th data-k="cv">CV</th><th data-k="src">Src</th><th>Status</th><th>Open</th>
</tr></thead><tbody id="b"></tbody></table></main>
<script>
const JOBS = __DATA__;
document.getElementById("updated").textContent = "· updated __UPDATED__";
let sortK="fit", sortDir=-1;
const el=id=>document.getElementById(id);
function esc(s){return (s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");}
function getSt(u){try{return localStorage.getItem("st:"+u)||"New";}catch(e){return "New";}}
function setSt(u,v){try{localStorage.setItem("st:"+u,v);}catch(e){}}
function pills(j){let s="";if(j.ref)s+='<span class="pill ref">🔔REF</span> ';if(j.giant)s+='<span class="pill giant">★giant</span> ';if(j.tailor)s+='<span class="pill tailor">✎tailor</span> ';if(j.unread)s+='<span class="pill unread">·unread</span> ';return s;}
// populate the pull/date dropdown
[...new Set(JOBS.map(j=>j.date))].sort().reverse().forEach(d=>{const o=document.createElement("option");o.value=o.textContent=d;el("date").appendChild(o);});
function stChange(sel){setSt(sel.dataset.u, sel.value);render();}
window.stChange=stChange;
function render(){
  const q=el("q").value.toLowerCase(),dt=el("date").value,rg=el("region").value,mf=+el("fit").value,
        st=el("status").value,ro=el("refonly").checked,to=el("tailoronly").checked,hd=el("hidedone").checked;
  let rows=JOBS.filter(j=>{
    const s=getSt(j.url);
    return (!q||(j.company+" "+j.role).toLowerCase().includes(q))&&(!dt||j.date===dt)&&(!rg||j.region===rg)
      &&(j.fit>=mf)&&(!st||s===st)&&(!ro||j.ref)&&(!to||j.tailor)&&(!hd||(s!=="Sent"&&s!=="Skip"));
  });
  rows.sort((a,b)=>{let x=a[sortK],y=b[sortK];if(sortK==="flags"){x=(a.ref?2:0)+(a.giant?1:0);y=(b.ref?2:0)+(b.giant?1:0);}return (x>y?1:x<y?-1:0)*sortDir;});
  el("count").textContent=rows.length+" of "+JOBS.length+" roles";
  el("b").innerHTML=rows.map(j=>{const s=getSt(j.url);const opts=["New","Sent","Interview","Skip"].map(o=>`<option${o===s?" selected":""}>${o}</option>`).join("");
    return `<tr class="${(s==='Sent'||s==='Skip')?'done':''}">
    <td class="muted">${esc(j.date)}</td>
    <td class="fit${j.fit}">${j.fit}</td>
    <td><span class="pill ${j.region==='North'?'n':'c'}">${esc(j.region)}</span></td>
    <td>${pills(j)}</td>
    <td>${esc(j.company)}</td>
    <td>${esc(j.role)}${j.loc?' <span class="muted">· '+esc(j.loc)+'</span>':''}</td>
    <td class="muted">${esc(j.cv)}</td>
    <td class="muted">${esc(j.src)}</td>
    <td><select class="st" data-v="${s}" data-u="${esc(j.url)}" onchange="stChange(this)">${opts}</select></td>
    <td>${j.url?'<a href="'+esc(j.url)+'" target="_blank" rel="noopener">open ↗</a>':''}</td></tr>`;}).join("");
}
document.querySelectorAll("th[data-k]").forEach(th=>th.onclick=()=>{const k=th.dataset.k;sortDir=(sortK===k)?-sortDir:1;sortK=k;render();});
["q","date","region","fit","status","refonly","tailoronly","hidedone"].forEach(id=>el(id).addEventListener("input",render));
render();
</script></body></html>"""

def build_page(jobs, updated):
    os.makedirs(DOCS, exist_ok=True)
    html = PAGE.replace("__DATA__", json.dumps(jobs, ensure_ascii=False)).replace("__UPDATED__", updated)
    J.atomic_write(INDEX_HTML, html)

def check_sources_dark(reg, counts):
    """Compare each source's yield to its historical best; warn (and Telegram) when a
    source that used to return jobs now returns 0 or errored — a silent mass-miss."""
    stats = reg.setdefault("source_stats", {})
    dark = []
    for name, n in counts.items():
        s = stats.setdefault(name, {"max": 0})
        prev_max = s.get("max", 0)
        if n is not None and n > prev_max: s["max"] = n
        s["last"] = n
        if prev_max >= SOURCE_DARK_MIN and (n is None or n <= 0):
            dark.append((name, prev_max, n))
    if dark:
        msg = "⚠️ JobScan: source(s) went dark — " + ", ".join(
            "%s (usually ~%d, now %s)" % (nm, mx, "error" if n == -1 else n) for nm, mx, n in dark)
        print(msg)
        if not os.environ.get("JOBSCAN_NO_ALERT"):
            try:
                import notify; notify.notify_text(msg)
            except Exception as e: print("notify err", e)
    return dark

def main():
    os.makedirs(DATA, exist_ok=True)
    print("JobScan CLOUD run %s" % J.TODAY)
    reg = J.load_reg(SEEN_JSON)
    counts = {}; bucket = []
    rows = J.select(J.collect(counts), reg, bucket)
    new = [slim(r) for r in rows]
    try:
        existing = json.load(open(JOBS_JSON, encoding="utf-8"))
    except Exception:
        existing = []
    seenu = set(); alljobs = []
    for x in (new + existing):                 # newest first, dedup by url so nothing shows twice
        u = x.get("url", "")
        if u and u in seenu: continue
        seenu.add(u); alljobs.append(x)
    alljobs = alljobs[:CAP]
    J.atomic_write(JOBS_JSON, json.dumps(alljobs, ensure_ascii=False))
    # invisible review bucket: filtered/uncertain roles + their JD text, for on-demand review
    J.atomic_write(BUCKET_JSON, json.dumps(
        {"generated": J.TODAY, "count": len(bucket), "roles": bucket[:BUCKET_CAP]}, ensure_ascii=False))
    check_sources_dark(reg, counts)
    J.save_reg(reg, SEEN_JSON)
    build_page(alljobs, J.TODAY)
    print("new:%d  total_on_page:%d  bucket:%d" % (len(new), len(alljobs), len(bucket)))
    J.send_alerts(rows)

if __name__ == "__main__":
    main()
