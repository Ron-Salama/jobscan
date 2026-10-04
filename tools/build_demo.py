# -*- coding: utf-8 -*-
"""Build the demo tracker (docs/index.html) from sample data, with the real page builder.

    python tools/build_demo.py

Inputs: docs/demo/sample-jobs.json (real public listings from scans between 2026-09-23 and
2026-10-04: title, company, location, URL, source, pull date) and docs/demo/sample-curation.json
(illustrative verdicts written for a fictional profile, see docs/agents/profile.example.md).

It runs the same steps as `cloud_run.py --rebuild-only` (apply_curation -> drop NO verdicts ->
collapse_dups -> cap_rows -> build_page) inside a temp directory, so no state file in the repo
is read or written and nothing touches the network. The demo then drops the pay-estimate and
pay-track fields and adds a "Demo - sample data" banner.
"""
import json, os, shutil, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEMO = os.path.join(ROOT, "docs", "demo")
OUT = os.path.join(ROOT, "docs", "index.html")
SNAPSHOT = "2026-10-04"

BANNER_CSS = (".demo{margin:0 0 8px;padding:7px 11px;border:1px solid #a8742a;border-radius:8px;"
              "background:#2b2310;color:#ffd98f;font-size:12.5px}.demo b{color:#ffe7b0}"
              'th[data-k="pay"],#b td:nth-child(4){display:none}')   # no pay column in the demo
BANNER = ('<div class="demo"><b>Demo &mdash; sample data.</b> %d real public listings from scans between '
          '2026-09-23 and %s. Verdicts, scores and reasons are illustrative, written for a fictional '
          'profile (a junior C#/Python developer in central Israel, not the author). No statuses, notes or pay data. '
          'The production tracker is private.</div>')


def main():
    os.environ["JOBSCAN_NO_ALERT"] = "1"
    sys.path.insert(0, ROOT)
    tmp = tempfile.mkdtemp(prefix="jobscan-demo-")
    cwd = os.getcwd()
    try:
        os.makedirs(os.path.join(tmp, "data"))
        shutil.copy(os.path.join(DEMO, "sample-jobs.json"), os.path.join(tmp, "data", "jobs.json"))
        shutil.copy(os.path.join(DEMO, "sample-curation.json"), os.path.join(tmp, "data", "curation.json"))
        os.chdir(tmp)                       # cloud_run's data/ and docs/ paths are relative
        import cloud_run as CR
        rows = CR._expect(CR._load_json(CR.JOBS_JSON, []), list, CR.JOBS_JSON)
        cur = CR.load_curation()
        statuses = CR._norm_values(cur.get("statuses"))
        CR.apply_curation(rows, cur)
        rows = [r for r in rows if not CR._is_no(r)]
        rows, merged = CR.collapse_dups(rows, statuses)
        rows, _ = CR.cap_rows(rows, statuses)
        for r in rows:                      # the demo shows no pay estimates or pay-track tags
            for f in ("pay", "paylo", "paytip", "track"):
                r.pop(f, None)
        CR.build_page(rows, "%s (demo snapshot)" % SNAPSHOT, cur, None)
        with open(os.path.join(tmp, "docs", "index.html"), encoding="utf-8") as f:
            html = f.read()
    finally:
        os.chdir(cwd)
        shutil.rmtree(tmp, ignore_errors=True)
    for old, new in (("<title>JobScan — Job Radar</title>", "<title>JobScan — Demo (sample data)</title>"),
                     ("</style>", BANNER_CSS + "\n</style>"),
                     ("<header>\n", "<header>\n  " + BANNER % (len(rows), SNAPSHOT) + "\n")):
        if html.count(old) != 1:
            raise SystemExit("page template changed: %r not found exactly once" % old)
        html = html.replace(old, new, 1)
    CR.J.atomic_write(OUT, html)
    print("wrote %s: %d rows (%d board copies merged)" % (os.path.relpath(OUT, ROOT), len(rows), merged))


if __name__ == "__main__":
    main()
