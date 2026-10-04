# -*- coding: utf-8 -*-
"""Build the public tracker snapshot from a production jobs.json + curation.json, sanitized.

    python tools/build_snapshot.py                      # reads data/jobs.json + data/curation.json
    python tools/build_snapshot.py --jobs J --curation C [--date YYYY-MM-DD] [--out docs]

Step 1 rebuilds the rows the production page shows, with the same calls as
`cloud_run.py --rebuild-only`: apply_curation -> drop NO verdicts / dead hosts (unless a status
or a pin keeps the row) -> collapse_dups -> cap_rows. It runs with this repo's config.py, so the
referral list, pay table and CV labels are the placeholders, not the production values.

Step 2 removes everything personal before anything is written:
  - rows that are on the production page only because of the owner's own marks: a NO verdict
    or dead host kept by a Sent/Interview status or a pin, and roles injected just for a pin
    (src 'important'). The public code says NO rows stay only for those reasons, so showing
    them would reveal the marks;
  - every row tied to an employer on the local blocklist: its company, listed name, title, any of its
    URLs (own, board copies, company / source links) or any curation entry for those URLs
    (origin employer_detail, a masked row's verdict entry, ...);
  - per row, every field not in KEEP: statuses, notes, pay estimates and pay track, CV labels,
    tailor-ready marks, pins and their notes, outsourcing tags and client links, referral and
    alert flags, and the free-text verdict reason. A row keeps its verdict (YES / REACH), its
    score and the verdict's basis (jd / title). The giant flag and the rule fit are recomputed,
    because the production values also encode the private referral list (see clean_row).

Writes <out>/index.html (the tracker page without the status, notes, pay and CV columns, the
status / referral / tailor-ready / outsourcing filters, pins and status export / import) and
<out>/snapshot/jobs.json (the sanitized rows, one per line). A self-check stops the build if a
non-KEEP field, a NO verdict, a blocklisted name or a non-empty STATUSES / NOTES constant would
be published. No network; the input files are only read.
"""
import argparse, contextlib, io, json, os, re, shutil, sys, tempfile
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("JOBSCAN_NO_ALERT", "1")
import cloud_run as CR   # importing has no side effects beyond utf-8 stdout

# Employers whose roles are left out of the snapshot. The list is personal, so it is NOT in this
# repo: it lives in a local, gitignored file (default snapshot_blocklist.txt in the repo root, or
# --blocklist PATH / $JOBSCAN_SNAPSHOT_BLOCKLIST), one name per line, '#' starts a comment. A name
# matches as a whole word, case-insensitively, anywhere in the text tied to a row (row_text); a
# Hebrew name may carry up to two prefix letters (ו ה ב ל מ ש כ) but no Hebrew letter after it.
# Without the file the build stops, unless --no-blocklist says that is intended.
BLOCKLIST_FILE = os.path.join(ROOT, "snapshot_blocklist.txt")
# A second local, gitignored list: employers whose rows ARE published, but as plain listings with no
# verdict, score or rescued flag (same file format). Missing file = nothing unrated.
UNRATED_FILE = os.path.join(ROOT, "snapshot_unrated.txt")
_HE = chr(0x590) + "-" + chr(0x5FF)   # the Hebrew Unicode block, as a regex class range


def load_blocklist(path):
    """Names from a blocklist file -> (whole-word regex or None, raw-substring regex or None, n)."""
    with open(path, encoding="utf-8") as f:
        names = [ln.split("#", 1)[0].strip() for ln in f]
    names = [n for n in names if n]
    if not names: return None, None, 0
    parts = []
    for n in names:
        if re.search("[" + _HE + "]", n):
            parts.append("(?<![%s])[ובהלמשכ]{0,2}%s(?![%s])" % (_HE, re.escape(n), _HE))
        else:
            parts.append(r"(?<![a-z0-9])%s(?![a-z0-9])" % re.escape(n))
    return (re.compile("|".join(parts), re.I),
            re.compile("|".join(re.escape(n) for n in names), re.I), len(names))


# The only row fields that are published. Everything else on a production row is dropped.
KEEP = ("date", "region", "fit", "match", "verdict", "vbasis", "company", "company_listed", "role", "loc",
        "url", "src", "giant", "jobify", "rescued", "gpt_reviewed", "unread", "orig", "srcurl", "dups")
FLAGS = ("giant", "jobify", "rescued", "gpt_reviewed", "unread")   # published only when true

BANNER_CSS = (".snap{margin:0 0 8px;padding:7px 11px;border:1px solid #2f5d86;border-radius:8px;"
              "background:#122235;color:#cfe3ff;font-size:12.5px}.snap b{color:#eaf3ff}")
BANNER = ('<div class="snap"><b>Snapshot of the production tracker, %s: %d roles.</b> Personal application '
          'statuses, notes, pay estimates and reasons are removed; verdicts and scores come from the AI '
          'review step.</div>')
# the snapshot's pills: verdict-derived top pick, provenance and the giant flag (no pins, pay track,
# outsourcing, tailor or referral pills)
PILLS = ("function pills(j){let s=\"\";if(tpk(j))s+='<span class=\"pill toppick\">🏆 TOP PICK</span> ';"
         "if(j.jobify)s+='<span class=\"pill jbf\">Jobify</span> ';"
         "if(j.rescued)s+='<span class=\"pill jbf\" title=\"rescued from the review bucket by the AI review step\">rescued</span> ';"
         "if(j.gpt_reviewed)s+='<span class=\"pill gptrev\">GPT reviewed</span> ';"
         "if(j.giant)s+='<span class=\"pill giant\">★giant</span> ';"
         "if(j.unread)s+='<span class=\"pill unread\">·unread</span> ';return s;}")
HIDDEN = '<input type="checkbox" id="%s" hidden>'   # render() still reads these ids
# (old, new) edits on the built page; each `old` must occur exactly once
PAGE_EDITS = [
    ("<title>JobScan — Job Radar</title>", "<title>JobScan — Tracker snapshot</title>"),
    ("</style>", BANNER_CSS + "\n</style>"),
    ('<select id="status"><option value="">any status</option><option>New</option><option>Sent</option>'
     '<option>Interview</option><option>Skip</option></select>', '<select id="status" hidden><option value=""></option></select>'),
    ('<label><input type="checkbox" id="refonly"> 🔔 referral</label>', HIDDEN % "refonly"),
    ('<label><input type="checkbox" id="tailoronly"> ✎ worth tailoring</label>', HIDDEN % "tailoronly"),
    ('<label><input type="checkbox" id="treadyonly"> 🎯 tailor-ready</label>', HIDDEN % "treadyonly"),
    ('<label><input type="checkbox" id="hidedone" checked> hide sent/skip</label>', HIDDEN % "hidedone"),
    ('<label title="hide roles from outsourcing / manpower contractors (the outsourcing tag)">'
     '<input type="checkbox" id="hideos"> hide outsourcing</label>', HIDDEN % "hideos"),
    ('\n    <button type="button" id="expBtn" class="tbtn" title="Download your applied/status marks (this browser) '
     'as a file">⬇ export status</button>', ""),
    ('\n    <label class="tbtn" title="Load a status file exported from another device">⬆ import status'
     '<input type="file" id="impFile" accept="application/json" hidden></label>', ""),
    ('<th data-k="pay" title="Rough junior monthly gross estimate (YES roles) - not an offer">Est. pay</th>', ""),
    ('<th data-k="cv">CV</th>', ""),
    ("<th>Status</th>", ""),
    ("<th>Notes</th>", ""),
    ("\n    <td class=\"muted\" title=\"${esc(j.paytip||'')}\">${esc(j.pay||'')}</td>", ""),
    ("\n    <td class=\"muted\">${esc(j.cv)}</td>", ""),
    ('\n    <td><select class="st" data-v="${s}" data-u="${esc(j.url)}" onchange="stChange(this)">${opts}</select></td>', ""),
    ("\n    <td><input class=\"note${rowNote(j)?' has':''}\" type=\"text\" data-u=\"${esc(j.url)}\" "
     "value=\"${esc(rowNote(j))}\" placeholder=\"notes…\" oninput=\"ntChange(this)\"></td></tr>", "</tr>"),
    ("const STATUSES = {};  /* the owner's applied/skip marks (global default; a local change overrides) */",
     "const STATUSES = {};  /* empty in the public snapshot */"),
    ("const NOTES = {};  /* per-role free-text notes (global default; a local edit overrides) */",
     "const NOTES = {};  /* empty in the public snapshot */"),
    ('el("expBtn").onclick=exportStatuses;\n', ""),
    ('el("impFile").onchange=e=>{if(e.target.files[0]){importStatuses(e.target.files[0]); e.target.value="";}};\n', ""),
]
# (pattern, replacement) edits; each pattern must match exactly once
PAGE_RX = [
    (re.compile(r"^function pills\(j\)\{.*\}$", re.M), PILLS),
    (re.compile(r"^function exportStatuses\(\)\{.*?^  r\.readAsText\(file\);\n\}\n", re.M | re.S), ""),
]

_SALARY = re.compile(r"\d[\d,.]*\s*[-–]\s*\d[\d,.]*\s*(₪|ש\"?ח|ils|nis)?", re.I)
# Drushim geo strings: '690 חיפה \tHaifa\t 539095 34.989571 32.7940463 21' -> 'Haifa'
_GEO = re.compile(r"^\d+\s+\S.*?\s+([A-Za-z][A-Za-z' .\-]*?)\s+\d{5,7}\s+-?\d+\.\d+\s+-?\d+\.\d+\s+\d+\s*$")


def tidy_loc(loc):
    """A row's location as text: Jobify puts the posted salary range in loc ('18,000-25,000 ₪'),
    which is not a place -> ''; a raw Drushim geo string -> its English city name."""
    loc = (loc or "").strip() if isinstance(loc, str) else ""
    if "₪" in loc or _SALARY.fullmatch(loc):
        loc = _SALARY.sub("", loc).replace("₪", "").strip(" ,|·-–")
    m = _GEO.match(loc)
    return m.group(1).strip() if m else loc


def clean_row(r):
    """The published copy of a page row: KEEP fields only, verdict fields only for YES / REACH."""
    out = {}
    for k in KEEP:
        v = r.get(k)
        if k in FLAGS:
            if v is True: out[k] = True
        elif k == "dups":
            dups = [{"url": d.get("url"), "src": d.get("src") or "", "region": d.get("region") or ""}
                    for d in (v or []) if isinstance(d, dict) and d.get("url")]
            if dups: out[k] = dups
        elif k in ("verdict", "vbasis", "match", "fit"):
            continue
        elif isinstance(v, (str, int, float)) and not isinstance(v, bool) and v != "":
            out[k] = v
    # A production row's giant flag is 'referral OR giant' (apply_curation) and its rule fit is 5 for
    # any referral employer (jobscan.classify), so both are recomputed from this repo's config alone:
    # giant = a config.GIANTS name; fit only where the page uses it (unrated rows), and a 5 outside
    # the North (only a referral gives that) becomes 4.
    out.pop("giant", None)
    if any(CR._company_match(r.get(f) or "", CR.C.GIANTS) for f in ("company", "company_listed")):
        out["giant"] = True
    verdict = (r.get("verdict") or "").upper()
    if verdict in ("YES", "REACH"):
        out["verdict"] = verdict
        if r.get("vbasis") in ("jd", "title"): out["vbasis"] = r["vbasis"]
        if isinstance(r.get("match"), (int, float)) and not isinstance(r.get("match"), bool): out["match"] = r["match"]
    elif isinstance(r.get("fit"), int) and not isinstance(r.get("fit"), bool):
        out["fit"] = min(r["fit"], 4) if r.get("region") != "North" else r["fit"]
    # Which merged copy is a row's main link was ranked partly by personal state (pins, statuses,
    # tailor marks; cloud_run._dup_rank), so re-pick it from public facts only: an employer's own
    # posting beats a job-board copy, and the remaining copies are listed in URL order.
    dups = out.get("dups") or []
    if dups and CR._is_board(out.get("url")):
        emp = next((d for d in sorted(dups, key=lambda d: d["url"]) if not CR._is_board(d["url"])), None)
        if emp:
            dups = [d for d in dups if d is not emp] + [{"url": out.get("url"), "src": out.get("src") or "",
                                                         "region": r.get("region") or ""}]
            out["url"], out["src"] = emp["url"], emp["src"] or out.get("src", "")
    if dups: out["dups"] = sorted(dups, key=lambda d: d["url"])
    out["loc"] = tidy_loc(r.get("loc"))
    if not out["loc"]: del out["loc"]
    out["role"] = (r.get("role") or "").strip() or "(title not captured)"
    return out


def curation_maps(cur):
    """Every URL-keyed curation map, keyed by cloud_run._nu (for the blocklist check)."""
    maps = [CR._norm_map(cur.get(nm))[0] for nm in ("verdicts", "jobify", "rescued", "origin", "tailor_ready", "important")]
    maps.append(CR._norm_values(cur.get("notes")))
    osrc = cur.get("outsourcing") if isinstance(cur.get("outsourcing"), dict) else {}
    for nm in ("urls", "client_links"):
        maps.append({CR._nu(u): v for u, v in (osrc.get(nm) or {}).items()})
    return maps


def row_text(r, maps):
    """All text tied to a row: the full production row and the curation entries of all its URLs."""
    keys = CR._row_urls(r) | CR._points_to(r) | {CR._nu(r.get("client_url"))}
    keys.discard("")
    parts = [json.dumps(r, ensure_ascii=False)]
    for k in sorted(keys):
        for mp in maps:
            if k in mp: parts.append(k + " " + json.dumps(mp[k], ensure_ascii=False))
    return "\n".join(parts)


def page_rows(rows, cur):
    """The production page's rows (cloud_run.main, --rebuild-only path). Returns (rows, merged, evicted)."""
    statuses = CR._norm_values(cur.get("statuses"))
    log = io.StringIO()
    with contextlib.redirect_stdout(log):          # its per-URL divergence list is noise here
        CR.apply_curation(rows, cur)
    for line in log.getvalue().splitlines():
        if not line.startswith(" "): print("  overlay:", line.replace("curation: ", ""))
    rows = [r for r in rows if CR._kept_by_status(r, statuses) or r.get("important")
            or not (CR._is_no(r) or CR._dead(r) or CR._not_a_job(r.get("url")))]
    rows, merged = CR.collapse_dups(rows, statuses)
    rows, evicted = CR.cap_rows(rows, statuses)
    return rows, merged, evicted


def personal_only(r):
    """On the production page only because of the owner's own mark (a status or a pin)."""
    return r.get("src") == "important" or CR._is_no(r) or CR._dead(r) or CR._not_a_job(r.get("url"))


def build_html(rows, date):
    """The tracker page for `rows` with cloud_run.build_page, then the snapshot edits."""
    tmp = tempfile.mkdtemp(prefix="jobscan-snapshot-")
    saved = CR.DOCS, CR.INDEX_HTML
    try:
        CR.DOCS, CR.INDEX_HTML = tmp, os.path.join(tmp, "index.html")
        CR.build_page(rows, "%s (snapshot)" % date, {"statuses": {}, "notes": {}}, None)
        with open(CR.INDEX_HTML, encoding="utf-8") as f:
            html = f.read()
    finally:
        CR.DOCS, CR.INDEX_HTML = saved
        shutil.rmtree(tmp, ignore_errors=True)
    for old, new in PAGE_EDITS + [("<header>\n", "<header>\n  " + BANNER % (date, len(rows)) + "\n")]:
        if html.count(old) != 1:
            raise SystemExit("page template changed: %r found %d times (expected once)" % (old[:70], html.count(old)))
        html = html.replace(old, new, 1)
    for rx, new in PAGE_RX:
        if len(rx.findall(html)) != 1:
            raise SystemExit("page template changed: /%s/ matched %d times (expected once)" % (rx.pattern[:50], len(rx.findall(html))))
        html = rx.sub(lambda m: new, html, count=1)
    return html


def self_check(rows, html, block):
    """Stop the build if anything personal would be published."""
    blob = json.dumps(rows, ensure_ascii=False)
    problems = []
    extra = sorted({k for r in rows for k in r} - set(KEEP))
    if extra: problems.append("fields outside KEEP: %s" % extra)
    if any(r.get("verdict") not in (None, "YES", "REACH") for r in rows): problems.append("a verdict other than YES/REACH")
    if block and block.search(blob): problems.append("a blocklisted name is still in the rows")
    if "₪" in blob: problems.append("a ₪ amount in the rows")
    if any(r.get("giant") and not any(CR._company_match(r.get(f) or "", CR.C.GIANTS) for f in ("company", "company_listed"))
           for r in rows): problems.append("a giant flag on a company outside config.GIANTS")
    if any("fit" in r and (r.get("verdict") or (r["fit"] > 4 and r.get("region") != "North")) for r in rows):
        problems.append("a fit value that could encode a referral")
    if any(CR._is_board(r.get("url")) and any(not CR._is_board(d.get("url")) for d in r.get("dups") or [])
           for r in rows): problems.append("a job-board main link while an employer posting is in dups")
    for const in ("const STATUSES = {};", "const NOTES = {};"):
        if html.count(const) != 1: problems.append("%s missing" % const)
    if problems:
        raise SystemExit("snapshot self-check FAILED, nothing written:\n  " + "\n  ".join(problems))


def _rel(p):
    try: return os.path.relpath(p, ROOT)
    except ValueError: return p             # another drive (Windows)


def _load(path, typ):
    obj = CR._load_json(path, None)
    if obj is None: raise SystemExit("%s not found (pass --jobs / --curation)" % path)
    return CR._expect(obj, typ, path)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--jobs", default=os.path.join(ROOT, "data", "jobs.json"))
    ap.add_argument("--curation", default=os.path.join(ROOT, "data", "curation.json"))
    ap.add_argument("--date", help="snapshot date for the banner (default: newest pull date in --jobs)")
    ap.add_argument("--out", default=os.path.join(ROOT, "docs"))
    ap.add_argument("--blocklist", default=os.environ.get("JOBSCAN_SNAPSHOT_BLOCKLIST") or BLOCKLIST_FILE,
                    help="local file of employers to leave out (default: snapshot_blocklist.txt, gitignored)")
    ap.add_argument("--no-blocklist", action="store_true", help="build without a blocklist file")
    ap.add_argument("--unrated", default=os.environ.get("JOBSCAN_SNAPSHOT_UNRATED") or UNRATED_FILE,
                    help="local file of employers published without verdict/score (default: snapshot_unrated.txt)")
    a = ap.parse_args(argv)
    block = near_rx = None
    if not a.no_blocklist:
        if not os.path.isfile(a.blocklist):
            raise SystemExit("blocklist file %s not found: create it (one employer per line) or pass --no-blocklist"
                             % a.blocklist)
        block, near_rx, n_block = load_blocklist(a.blocklist)
        print("blocklist: %d name(s) from %s" % (n_block, _rel(a.blocklist)))
    rows, cur = _load(a.jobs, list), _load(a.curation, dict)
    date = a.date or max((str(r.get("date") or "") for r in rows if isinstance(r, dict)), default="") or CR.J.TODAY
    n_in = len(rows)

    rows, merged, evicted = page_rows(rows, cur)
    print("production page: %d rows (from %d in %s; %d board copies merged, %d evicted by the cap)"
          % (len(rows), n_in, os.path.basename(a.jobs), merged, evicted))
    personal = [r for r in rows if personal_only(r)]
    rows = [r for r in rows if not personal_only(r)]
    print("dropped %d row(s) on the page only because of a status or a pin" % len(personal))
    maps = curation_maps(cur)
    blocked, kept = [], []
    for r in rows:
        (blocked if block and block.search(row_text(r, maps)) else kept).append(r)
    print("dropped %d row(s) tied to a blocklisted employer%s" % (len(blocked), ":" if blocked else ""))
    for r in blocked:
        m = block.search(row_text(r, maps))
        print("   %-28s | %-45s | matched %r" % ((r.get("company") or "")[:28], (r.get("role") or "")[:45], m.group(0)))
    for r in kept:                       # a name inside a longer word: kept, but worth a look
        m = near_rx.search(row_text(r, maps)) if near_rx else None
        if m: print("   check by hand (substring only, kept): %s | %s | %r" % (r.get("company"), r.get("role"), m.group(0)))

    unrate = load_blocklist(a.unrated)[0] if os.path.isfile(a.unrated) else None
    n_unrated = 0
    for i, r in enumerate(kept):
        if unrate and unrate.search(row_text(r, maps)):
            kept[i] = {k: v for k, v in r.items() if k not in ("verdict", "vbasis", "match", "rescued")}
            n_unrated += 1
    if unrate: print("published %d row(s) as plain listings (no verdict or score)" % n_unrated)

    out_rows = [clean_row(r) for r in kept]
    html = build_html(out_rows, date)
    self_check(out_rows, html, block)
    os.makedirs(os.path.join(a.out, "snapshot"), exist_ok=True)
    jpath, hpath = os.path.join(a.out, "snapshot", "jobs.json"), os.path.join(a.out, "index.html")
    CR.J.atomic_write(jpath, "[\n" + ",\n".join(json.dumps(r, ensure_ascii=False) for r in out_rows) + "\n]\n")
    CR.J.atomic_write(hpath, html)
    vc = Counter(r.get("verdict") or "unrated" for r in out_rows)
    print("snapshot %s: %d roles (YES %d, REACH %d, unrated %d) -> %s, %s"
          % (date, len(out_rows), vc["YES"], vc["REACH"], vc["unrated"],
             _rel(hpath), _rel(jpath)))


if __name__ == "__main__":
    main()
