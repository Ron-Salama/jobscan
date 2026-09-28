# JobScan — Ron's automated Israeli tech-job radar

Scans 30+ Israeli job sources (open APIs, scrapers and the big companies' own ATS boards) every
2 hours on GitHub Actions, filters to junior software/dev roles in the North & Center, dedups across
sources, flags referral companies and giants, and publishes a live, filterable tracker on GitHub Pages.
Sends a Telegram alert on new **giant/referral** roles.

- **Rule tests:** the filtering rules are covered by a regression suite (`tests/test_rules.py`, 60+ tests)
  that runs before every scan; a failing test stops the run.
- **AI review step (separate from the pipeline):** Claude Code agents read each shortlisted job
  description and score it against a profile; the verdicts are saved in `data/curation.json` and
  overlaid on the tracker. The Actions pipeline itself calls no AI model.

## Two ways it runs
- **Local:** `python jobscan.py` → writes `C:\Users\User\Desktop\Ron - Job Tracker (AUTO).html`.
  (The Windows Task `RonJobScan` that used to run it is disabled - the cloud run is the source of truth.)
- **Cloud (this repo):** GitHub Actions runs `python cloud_run.py` every 2h → updates
  `data/jobs.json` + a web tracker at `docs/index.html` (served by GitHub Pages) → runs 24/7,
  no PC needed.

## Cloud setup (one-time)
1. **Push this folder** to a GitHub repo.
2. **Settings → Secrets and variables → Actions → New repository secret** — add:
   - `TELEGRAM_TOKEN` = your bot token
   - `TELEGRAM_CHAT_ID` = your chat id
   (Same values as your local `notify_config.py`.)
3. **Settings → Pages → Source: Deploy from a branch → `main` / `/docs`.**
   Your live tracker: `https://<user>.github.io/<repo>/`
4. **Actions tab → JobScan → Run workflow** to test immediately (otherwise it runs on the 2h cron).

## Files
- `config.py` — rules: lanes, locations (drop Jerusalem+South), referral cos, giants, CV map.
- `jobscan.py` — sources + classify/dedup/seniority pipeline + local output.
- `sources_ext.py` — v2/v3 + giants adapters (Ethosia, Dialog, Nisha, GotFriends, BuiltIn,
  LinkedIn, CPS, TechJob, AllJobs, Comeet, Workday, Apple, Camtek).
- `cloud_run.py` — cloud output (jobs.json + docs/index.html).
- `notify.py` — Telegram/WhatsApp alerts (secrets from env or `notify_config.py`).

## Tuning
Edit `config.py`: `REFERRAL_COMPANIES`, `GIANTS`, `GREENHOUSE_SLUGS`, `TITLE_DEV`,
`FOUNDATION_SKIP`. Add Comeet company boards inside `src_comeet` in `sources_ext.py`.

_Not affiliated with any of the scanned sites; personal job-search tool._
