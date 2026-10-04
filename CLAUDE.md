# CLAUDE.md

Context for AI coding agents (Claude Code) working in this repo. Read it before changing code.

## What this is

JobScan scans about 30 Israeli job sources, filters them with deterministic rules to junior
software roles in the target regions, deduplicates across sources, and publishes a static
tracker page. In production it runs on GitHub Actions in a private repo. This repo is the
public code snapshot of that deployment: personal values in `config.py` are placeholders and
there is no `data/` directory.

## Architecture map

```
sources/*.py, jobscan.SOURCES   about 30 adapters -> list of row dicts (one shape, see below)
jobscan.collect()               calls every adapter in its own try/except, normalize() each row
jobscan.select()                region drop -> classify() -> buckets -> dedup() -> registry check
jobscan.classify()              title gate, seniority, years, student, profile-gap -> lane + flags
cloud_run.main()                merge with data/jobs.json -> apply_curation() -> collapse_dups()
                                -> cap_rows() -> data/*.json + docs/index.html -> alerts
notify.py                       Telegram Bot API / CallMeBot sends; reports delivered / retry / rejected
```

| File | Role |
|---|---|
| `jobscan.py` | Core pipeline and rules: HTTP helpers, the 5 open-API sources (hiremetech, Experis, Drushim, Greenhouse, amazon.jobs), `region_of`, `parse_years`, `company_is`, `classify`, `dedup`, `select`, alert queue, referral digest. Its `main()` is the legacy local mode. |
| `sources/` | One module per adapter (`src_<name>()`), re-exported by `sources/__init__.py`. `sources_ext.py` is a compatibility shim; new code imports `sources`. |
| `cloud_run.py` | The production entry. State files, curation overlay, cross-board duplicate collapse, page cap, buckets, source-health alarm, the page template (`PAGE`). |
| `config.py` | All rule data: region token sets (EN + HE), title gates, senior/junior/student markers, foundation-skip list, company lists, CV labels, Greenhouse slugs. |
| `notify.py` | Alert delivery. Secrets come from env (`TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`) or a local, gitignored `notify_config.py`. |
| `tests/test_rules.py` | 64 network-free regression tests. |
| `docs/agents/` | Specs for the Claude Code judge and skeptic review step (outside the pipeline). |
| `tools/` | Local helpers (Telegram setup, local runner, `build_demo.py` for the demo page). |

**Canonical row shape** (what an adapter returns; `jobscan.job()` builds it, `normalize()` fills
gaps): `source, sid, title, company, city, url, level, years_min, years_max, tech, desc, active`.
`region` is computed from `city` by `normalize()`. Use `""` for an unknown employer; the scanner
shows it as `(masked)`.

**Lanes** from `classify()`: `apply` (tracker), `reach` (tracker, flagged), `review` (review bucket;
North/Unknown rows also go on the tracker), `skip` (bucket only). A title that misses the dev gate
returns `None` and may still land in a bucket.

**Registered adapters:** `jobscan._EXT_NAMES` (25) plus the 5 core sources in `jobscan.SOURCES`.
`src_cps`, `src_techjob`, `src_kaltura` and `src_moonactive` are retired (broken links, no rows, or
replaced by `src_ashby`) and are not registered; leave them unregistered unless asked.

## Glossary (page and curation terms)

| Term | Meaning |
|---|---|
| bucket | A JSON list of roles the rules set aside instead of dropping: review, QA, giant (`write_buckets`). |
| giant | A large employer (`config.GIANTS`); its roles are always surfaced, at any level. |
| referral (🔔) | An employer in `config.REFERRAL_COMPANIES` (placeholders here). |
| verdict / score | The review step's YES / REACH / NO and its band-locked 0-100 score (`curation.verdicts`). |
| basis | `jd` or `title`: what the verdict was made from. The page shows ✓ for JD-read. |
| rescued | A bucket role the review step rated YES/REACH, injected onto the tracker (`curation.rescued`). |
| Jobify | Roles from the jobify360 feed, judged in the review step (`curation.jobify`, `origin` = real employer). |
| GPT reviewed | Rows judged by one GPT-run review pass on 2026-09-29 (`curation.gpt_reviewed`). |
| tailor-ready (🎯) | Roles triaged in the review step with a base CV picked (`curation.tailor_ready`). |
| pinned (📌) | `curation.important`: kept at the top and never dropped. |
| outsourcing | Employer of record is a manpower contractor (`curation.outsourcing`). |
| Est. pay | `cloud_run.est_pay()` over `config.PAY_TIERS` (empty here, so the column is blank). |

## Commands

```bash
python tests/test_rules.py              # all 64 tests, no pytest needed; exit code 1 on a failure
python -m pytest -q tests               # the same suite, as CI runs it
python tools/build_demo.py              # rebuild docs/index.html (the demo) from docs/demo/*.json

# Full scan: network, about 20 minutes. Writes data/ and OVERWRITES docs/index.html (the demo).
JOBSCAN_NO_ALERT=1 python cloud_run.py              # PowerShell: $env:JOBSCAN_NO_ALERT=1; python cloud_run.py
python cloud_run.py --rebuild-only                  # no network: re-apply data/curation.json, rebuild the page
```

`JOBSCAN_NO_ALERT=1` suppresses every Telegram/WhatsApp send (alerts, digest, source-health).
Set it for any local run.

## Rules of the road

1. **No LLM calls inside the pipeline.** Scanning, filtering, dedup and the page are
   deterministic Python. AI judgment happens only in the separate, human-started review step
   (`docs/agents/`), whose output is data (`data/curation.json`) the pipeline overlays.
2. **Never change filter rules without the owner's decision.** Comments like
   `owner's call #7, 2026-09-24` mark decisions a human made. Propose a rule change with
   examples of roles it would add or drop; don't land it on your own judgment.
3. **Every rule bug gets a regression test that fails on the old code.** Use the real title,
   location or JD snippet that went wrong, name the date in the docstring, and confirm the test
   fails before your fix and passes after it.
4. **Uncertain means bucket, not drop.** If a rule is unsure, the role goes to the review / QA /
   giant bucket with a reason tag. A silent drop is the bug class this project exists to avoid.
5. **Adapters never raise.** Wrap every network call, return partial results on failure, print a
   per-board or per-page count, and return the canonical row shape.
6. **State writes are atomic.** Write state and pages with `jobscan.atomic_write`. A corrupt state
   file must stop the run (`cloud_run._load_json` raises `SystemExit`), never be overwritten with
   an empty default.
7. **Never lose an alert.** Undelivered alerts are queued in the registry and retried; only a
   single-role message the channel rejects (a non-429 4xx) is logged and dropped. Keep that contract when touching `send_alerts`,
   `send_ref_digest` or `notify.py`.
8. **Match words, not substrings.** Short tokens go through `_has_word`, `company_is` or
   `_loc_re` (Hebrew letters may carry one or two prefix letters). `'sap'` must not match
   `Sapiens`, `'intern'` must not match `internal`, `'עכו'` must not match inside another word.
9. **Student is judged from the title only**, never from JD or company text.
10. **Comments say why.** Rule data carries the date and the reason it was added; follow that style.

## Adding a source adapter

1. Create `sources/<name>.py` with `def src_<name>():`. Use `requests` + `bs4` like the other
   adapters, a browser User-Agent, timeouts on every call, and polite sleeps between pages.
2. Keep Israel roles only (or let `region_of` drop the rest), fetch the JD text into `desc` when
   the source allows it, and set `level` only from a structured field.
3. Export it from `sources/__init__.py` (import + `__all__`) and register it in
   `jobscan._EXT_NAMES`.
4. Add a network-free test that fakes the HTTP layer (see `test_hiremetech_abroad_feed_rows_rechecked`
   and `test_linkedin_qa_lane_not_starved`).
5. Run it once live and compare its row count with the site.

## Do not touch

- `notify_config.py` (local secrets, gitignored). Never print, copy or commit tokens.
- The private-repo guard and the commit/push retry loop in `.github/workflows/scan.yml`.
- `config.REFERRAL_COMPANIES`, `config.CV` and the `config.PAY_*` table beyond placeholders: the real
  values are private.
- Generated files: `docs/index.html` comes from `tools/build_demo.py` in this repo.
