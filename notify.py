# -*- coding: utf-8 -*-
"""Push notifier for JobScan — alerts ONLY on giants + referral companies.
Supports Telegram (recommended) and/or CallMeBot WhatsApp. No-ops safely if unconfigured."""
import os, re, urllib.request, urllib.parse

try:
    import notify_config as N   # local: holds the secrets (gitignored)
except Exception:
    N = None

def _cfg(key):
    """Prefer environment (GitHub Actions secrets), fall back to local notify_config.py."""
    return os.environ.get(key) or (getattr(N, key, "") if N else "")

def _get(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "JobScan/1.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status == 200
    except Exception as e:
        print("  notify send err:", e); return False

def _send(text):
    ok = False
    tok = _cfg("TELEGRAM_TOKEN"); chat = _cfg("TELEGRAM_CHAT_ID")
    if tok and chat:
        ok = _get("https://api.telegram.org/bot%s/sendMessage?%s" % (tok,
              urllib.parse.urlencode({"chat_id": chat, "text": text, "disable_web_page_preview": "false"}))) or ok
    phone = _cfg("CALLMEBOT_PHONE"); key = _cfg("CALLMEBOT_APIKEY")
    if phone and key:
        ok = _get("https://api.callmebot.com/whatsapp.php?%s" % urllib.parse.urlencode(
              {"phone": phone, "text": text, "apikey": key})) or ok
    return ok

def notify_text(text):
    """Send one plain message (batch-summary nudge, source-dark warning). No-op if unconfigured."""
    if not (_cfg("TELEGRAM_TOKEN") or _cfg("CALLMEBOT_APIKEY")):
        print("  (notify: no channel configured — message skipped)"); return False
    return _send(text)

def notify_jobs(rows):
    """rows = tracker-row dicts already filtered to giants/referrals. Sends ONE batched message."""
    if not rows:
        return
    if not (_cfg("TELEGRAM_TOKEN") or _cfg("CALLMEBOT_APIKEY")):
        print("  (notify: no channel configured — %d giant/referral alerts skipped)" % len(rows))
        return
    lines = ["\U0001F514 JobScan: %d new giant/referral role%s" % (len(rows), "" if len(rows) == 1 else "s")]
    for r in rows[:12]:
        flag = "\U0001F514REF" if "REFERRAL" in r["openings"]["note"] else "★"
        cvm = re.search(r"\((.*?)\)", r.get("cv", "") or "")   # "Ron Salama - CV (Backend & Full-Stack).pdf" -> "Backend & Full-Stack"
        cv = cvm.group(1) if cvm else (r.get("cv", "") or "").replace(".pdf", "")
        lines.append("%s %s — %s [%s]\n\U0001F4C4 CV: %s\n%s" % (flag, r["company"], r["role"][:70], r["region"], cv or "?", r["url"]))
    if len(rows) > 12:
        lines.append("...and %d more (see tracker)" % (len(rows) - 12))
    _send("\n\n".join(lines))
