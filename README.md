# Job Radar 2

A personal search desk for Ron: public job discovery, explainable triage, application tracking, and visible source health. No ATS match percentages, hidden-prompt generation, automatic applications, or automatic recruiter messages.

## Open it

**Cloud tracker: https://ron-salama.github.io/jobscan/**. It updates without this PC. For local development, double-click `start_radar.bat`. It opens http://127.0.0.1:8765 in your browser. Keep the terminal open while using Refresh sources or profile editing. Closing the terminal stops the app, not your saved progress.

This machine already has a project-local Python environment in `.venv`. On a new machine with Python 3.10+, run `setup_radar.bat` first. No Node dependency is needed to use the app.

The static `docs/index.html` also opens directly in a browser and can be hosted on GitHub Pages. Static snapshots support browsing, notes, statuses and export/restore; refreshing sources and editing the shared profile require the local app.

## How to use it

1. Start in **Worth considering**. These listings have an explicit early-career signal or experience requirement near your target. It is a review queue, not a claim that you qualify for everything.
2. Select a role. Read the actual experience excerpts, skills mentioned, uncertainty flags and collected description. Open the original before applying.
3. Use **Needs a look** for ambiguous seniority, **Experience stretch** for higher requirements, or **All relevant roles** to inspect the retained candidates.
4. Save a role, record its stage, and add private notes. Export progress regularly.
5. Check **Source health** after refreshing. A failing source does not mean there are no jobs.
6. In **Your profile**, edit experience, skills, learning topics, location preferences and enabled sources. Save while no scan is running. Missing skills never automatically delete a posting.

## What is different

- The Intel AI/cloud role is no longer discarded because it mentions post-silicon.
- `0-3 years` means a lower bound of zero. Preferred experience is separated where recognizable; alternative degree/experience paths are flagged for review.
- Company size and a possible referral do not inflate suitability.
- Unknown locations remain visible. Known foreign locations are not guessed to be Center.
- An exact posting URL identifies an opening. Same-title requisitions are not merged or permanently suppressed.
- Clearly irrelevant roles are removed from the tracker. Unknown requirements remain for review. Some source adapters also prefilter what they collect; see coverage limits below.
- Old imports start as **unverified**. **Observed** means seen in a source response, not independently confirmed open by the employer. **Stale** means not observed for 14 days; only an explicit source signal says closed.
- Source attempts have independent time budgets. Failures never wipe old listings.
- The dashboard displays full collected descriptions and source provenance.

## Your data

- `data/radar.json`: versioned listings, evidence, source health, scan history.
- `profile.json`: editable search profile and source configuration. RAG/MCP remain marked in progress.
- `web/dashboard.html`: dashboard template; `docs/index.html`: generated portable snapshot.
- Browser local storage: application stages and notes. These are not uploaded to sources or stored in the generated page. Different browsers/origins have separate state; Export/Restore moves it between them.
- `data/jobs-v1.json`, original `data/jobs.json` / `data/seen.json`, and `legacy/`: preserved originals. The new pipeline ignores old seen-title suppression.
- Existing Telegram credentials remain in the ignored `notify_config.py`; they are not served by the local web server.

Browser data is not a substitute for backups. Export progress before clearing browser data or moving to another URL/device.

### Old tracker statuses

When the old and new dashboards run on the same browser origin, existing `st:URL` local-storage statuses are read automatically (`Sent` becomes `Applied`, `Skip` becomes `Dismissed`). If you change origins, open the OLD tracker, open its browser console, and run:

```javascript
const by_url = Object.fromEntries(Object.keys(localStorage).filter(k => k.startsWith('st:')).map(k => [k.slice(3), localStorage.getItem(k)]));
const a = document.createElement('a');
a.href = URL.createObjectURL(new Blob([JSON.stringify({version:1, by_url})], {type:'application/json'}));
a.download = 'old-job-tracker-progress.json'; a.click();
```

Then restore that file using **Export & restore** in the new dashboard. Old URLs must correspond to listings imported into the new app; unmatched entries are reported, not guessed.

## Commands

From this folder, use `.venv\Scripts\python.exe` instead of `python` on this Windows installation:

```text
python jobscan.py serve --open
python jobscan.py build
python jobscan.py scan
python jobscan.py scan --sources workday:intel,greenhouse:similarweb
python jobscan.py sources
python jobscan.py import path/to/raw-listings.json
python -m unittest discover -s tests -v
```

`build` is offline. `scan` requests public job feeds only and does not upload a CV. Raw imports are JSON arrays with title, company, city, url and desc fields; they remain unverified.

`scan --notify` uses Telegram only and only for newly discovered, relevant giant-company roles with a collected JD, early-career/three-year experience evidence and a known target location. Failed deliveries remain queued; successful receipts prevent repeat alerts. An interrupted run between Telegram accepting a message and its receipt being saved can still duplicate that message.

## Scheduling and hosting

GitHub Actions runs independently of your PC. Every two hours it scans configured sources but only new relevant giants enter the tracker and trigger Telegram alerts. At 17:00 Asia/Jerusalem (DST-aware), the daily scan admits relevant openings from the last 24 hours. Unknown posting dates use first discovery and are labelled unverified; calendar-only dates are labelled as imprecise. GitHub can delay scheduled runs; 17:00 is the target, not a guaranteed exact delivery time. Missed daily slots are caught up on the next run that evening.

The original giant list remains in `profile.json`; referral companies are NVIDIA, Philips, Camtek, Palo Alto Networks, Apple, and **PwC Next**, not all PwC. Matching uses company names, not mentions in job descriptions. Referral flags indicate a company on your contact list, not a verified introduction. Tailoring flags indicate a plausible role with a substantial description and a skill overlap, not an automatically rewritten resume.

Clearly unrelated roles, explicit senior roles, unambiguous requirements above three years, specialist hardware-design titles, and excluded locations are removed from the active tracker. Unknown seniority stays in Needs a look. Existing relevant listings are retained; the Latest daily update view isolates the most recent daily selection. Historical discovery IDs prevent removed results from becoming new alerts repeatedly.

The workflow publishes the generated dashboard to GitHub Pages. Profile and listings are public there; browser-only notes/statuses and Telegram secrets are not part of the page. The local Windows task remains disabled to avoid duplicate scanning. A local dashboard is an independent snapshot, not a synchronized editor of the cloud profile.

Concurrent scans are prevented with `data/scan.lock`. If a process is forcibly killed, confirm no scan is still running before manually removing that file. Normal completion and handled failures remove it automatically.

## Source coverage and limits

New native collectors handle Greenhouse boards and Intel/NVIDIA/Philips Workday searches. Existing agency/Apple/Comeet collectors are retained behind isolated workers rather than pretending untested rewrites are reliable. These **compatibility scrapers are always labelled partial**, because they use caps/prefilters and sometimes swallow request failures internally.

Workday searches Israel/Haifa/Yokneam with page and detail budgets. It is not complete worldwide-board coverage. Partial checkpoints are retained on timeout when available. Greenhouse known foreign locations are omitted; ambiguous locations remain for review. No source can promise completeness or that an observed agency repost is still hiring.

Same URLs merge; different URLs are intentionally retained. Cross-posts may appear twice rather than distinct requisitions being lost. Experience extraction is a conservative text heuristic, not a semantic assessment. Read quoted evidence and the original JD.

Source labels: **ok** = request/parser completed within that reader's stated scope; **partial** = incomplete or legacy coverage; **empty** = returned no rows, not proof of no openings; **error/timeout** = attempt failed or exhausted its budget.

## Verification

Regression suite covers the Intel post-silicon case, ranges and optional experience, senior titles, unknown/foreign locations, source failures, exact deduplication, freshness, migration, atomic writes and embedded-script safety.

Optional browser checks: install Playwright separately, run a local server, then `node tests/browser.cjs`. Set `PLAYWRIGHT_MODULE` to an existing Playwright module path and `PLAYWRIGHT_CHANNEL` if using a browser other than Edge. Tests use an isolated browser context, never your personal notes.


### September 19 audit fixes

Hebrew developer titles (including מתכנת/ת) and junior spelling variants are recognized. Explicit work-location sentences are checked against source location fields; an excluded location in the actual job description prevents admission. City selectors and incidental office/customer mentions do not count as job locations.

Cloud wake-ups target minute 0 and additionally 17, 37, and 53 each hour. Lightweight due checks skip unnecessary scans. Giant scans use two hours elapsed since the last successful giant/daily scan, rather than even-hour arithmetic. Daily runs catch up if their 17:00 slot was missed, including after midnight, and record target time, actual start, and delay. GitHub still does not guarantee punctual scheduling. Recovered previously filtered Hebrew roles keep their original discovery dates and do not trigger new-job alerts.
