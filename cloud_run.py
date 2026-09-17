# -*- coding: utf-8 -*-
"""
Cloud entry for JobScan (GitHub Actions). Same scan pipeline as jobscan.py, but instead of
writing the local Desktop tracker it:
  - accumulates rows into  data/jobs.json  (deduped via data/seen.json),
  - regenerates a self-contained filterable web tracker at  docs/index.html  (served by GitHub Pages),
  - sends Telegram/WhatsApp alerts on new giant/referral roles (secrets from env).
The workflow commits data/ + docs/ back to the repo after each run.
"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jobscan as J   # sets utf-8 stdout via reconfigure

DATA = "data"; DOCS = "docs"
JOBS_JSON = os.path.join(DATA, "jobs.json")
SEEN_JSON = os.path.join(DATA, "seen.json")
INDEX_HTML = os.path.join(DOCS, "index.html")
CAP = 1200  # keep the page bounded

def slim(r):
    note = r["openings"]["note"]
    return {
        "date": r["sector"].replace("auto ", ""),
        "region": r["region"], "fit": r["fit"],
        "company": r["company"], "role": r["role"], "loc": r["location"], "url": r["url"],
        "cv": r["cv"].replace("Ron Salama - CV (", "").replace(").pdf", ""),
        "ref": "REFERRAL" in note, "giant": "GIANT" in note, "tailor": "TAILOR" in note,
        "src": note.split("sources:")[1].split("|")[0].strip() if "sources:" in note else "",
    }

PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Ron — Job Radar</title>
<style>
:root{color-scheme:light dark}
body{font:14px/1.5 system-ui,Segoe UI,Arial,sans-serif;margin:0;background:#0f1115;color:#e7e9ee}
header{padding:14px 18px;background:#161a22;border-bottom:1px solid #262c38;position:sticky;top:0;z-index:5}
h1{font-size:17px;margin:0 0 8px}
.meta{color:#96a0b5;font-size:12px}
.controls{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px}
.controls input,.controls select{background:#0f1115;color:#e7e9ee;border:1px solid #2b3240;border-radius:8px;padding:6px 9px;font-size:13px}
.controls label{display:flex;align-items:center;gap:5px;color:#c3cad8;font-size:12px}
main{padding:12px 14px}
table{border-collapse:collapse;width:100%}
th,td{text-align:left;padding:8px 9px;border-bottom:1px solid #20262f;vertical-align:top}
th{color:#96a0b5;font-size:11px;text-transform:uppercase;letter-spacing:.04em;cursor:pointer;position:sticky;top:0}
tr:hover td{background:#151a22}
a{color:#7db4ff;text-decoration:none}a:hover{text-decoration:underline}
.pill{display:inline-block;padding:1px 7px;border-radius:999px;font-size:11px;font-weight:600;white-space:nowrap}
.ref{background:#3a1d2b;color:#ff9ec4}.giant{background:#20344a;color:#8fc7ff}.tailor{background:#3a331a;color:#ffd98f}
.n{background:#1c3a2a;color:#8ff0b8}.c{background:#2a2340;color:#c4b0ff}
.fit5{color:#8ff0b8;font-weight:700}.fit4{color:#c9e69a}.fit3{color:#e6c78a}
.muted{color:#8792a6;font-size:12px}
</style></head><body>
<header>
  <h1>🎯 Ron — Job Radar <span class="meta" id="updated"></span></h1>
  <div class="meta" id="count"></div>
  <div class="controls">
    <input id="q" placeholder="search company / role…" size="22">
    <select id="region"><option value="">all regions</option><option>North</option><option>Center</option></select>
    <select id="fit"><option value="0">fit ≥ any</option><option value="5">fit 5</option><option value="4">fit ≥ 4</option><option value="3">fit ≥ 3</option></select>
    <label><input type="checkbox" id="refonly"> 🔔 referral only</label>
    <label><input type="checkbox" id="tailoronly"> ✎ tailor only</label>
  </div>
</header>
<main><table id="t"><thead><tr>
<th data-k="date">Date</th><th data-k="fit">Fit</th><th data-k="region">Region</th>
<th data-k="flags">Flags</th><th data-k="company">Company</th><th data-k="role">Role</th>
<th data-k="cv">CV</th><th data-k="src">Src</th><th>Open</th>
</tr></thead><tbody id="b"></tbody></table></main>
<script>
const JOBS = __DATA__;
const upd = "__UPDATED__";
document.getElementById("updated").textContent = "· updated " + upd;
let sortK="date", sortDir=-1;
const el=id=>document.getElementById(id);
function pills(j){let s="";if(j.ref)s+='<span class="pill ref">🔔REF</span> ';if(j.giant)s+='<span class="pill giant">★giant</span> ';if(j.tailor)s+='<span class="pill tailor">✎tailor</span> ';return s;}
function render(){
  const q=el("q").value.toLowerCase(),rg=el("region").value,mf=+el("fit").value,ro=el("refonly").checked,to=el("tailoronly").checked;
  let rows=JOBS.filter(j=>(!q||(j.company+" "+j.role).toLowerCase().includes(q))&&(!rg||j.region===rg)&&(j.fit>=mf)&&(!ro||j.ref)&&(!to||j.tailor));
  rows.sort((a,b)=>{let x=a[sortK],y=b[sortK];if(sortK==="flags"){x=(a.ref?2:0)+(a.giant?1:0);y=(b.ref?2:0)+(b.giant?1:0);}return (x>y?1:x<y?-1:0)*sortDir;});
  el("count").textContent=rows.length+" of "+JOBS.length+" roles";
  el("b").innerHTML=rows.map(j=>`<tr>
    <td class="muted">${j.date}</td>
    <td class="fit${j.fit}">${j.fit}</td>
    <td><span class="pill ${j.region==='North'?'n':'c'}">${j.region}</span></td>
    <td>${pills(j)}</td>
    <td>${j.company}</td>
    <td>${j.role}${j.loc?' <span class="muted">· '+j.loc+'</span>':''}</td>
    <td class="muted">${j.cv}</td>
    <td class="muted">${j.src}</td>
    <td>${j.url?'<a href="'+j.url+'" target="_blank" rel="noopener">open ↗</a>':''}</td></tr>`).join("");
}
document.querySelectorAll("th[data-k]").forEach(th=>th.onclick=()=>{const k=th.dataset.k;sortDir=(sortK===k)?-sortDir:1;sortK=k;render();});
["q","region","fit","refonly","tailoronly"].forEach(id=>el(id).addEventListener("input",render));
render();
</script></body></html>"""

def build_page(jobs, updated):
    os.makedirs(DOCS, exist_ok=True)
    html = PAGE.replace("__DATA__", json.dumps(jobs, ensure_ascii=False)).replace("__UPDATED__", updated)
    with open(INDEX_HTML, "w", encoding="utf-8") as f:
        f.write(html)

def main():
    os.makedirs(DATA, exist_ok=True)
    print("JobScan CLOUD run %s" % J.TODAY)
    reg = J.load_reg(SEEN_JSON)
    rows = J.select(J.collect(), reg)
    new = [slim(r) for r in rows]
    try:
        existing = json.load(open(JOBS_JSON, encoding="utf-8"))
    except Exception:
        existing = []
    alljobs = (new + existing)[:CAP]           # newest first, bounded
    json.dump(alljobs, open(JOBS_JSON, "w", encoding="utf-8"), ensure_ascii=False)
    J.save_reg(reg, SEEN_JSON)
    build_page(alljobs, J.TODAY)
    print("new:%d  total_on_page:%d" % (len(new), len(alljobs)))
    J.send_alerts(rows)

if __name__ == "__main__":
    main()
