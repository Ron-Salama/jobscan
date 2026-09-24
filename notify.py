# -*- coding: utf-8 -*-
"""Push notifier for JobScan — alerts ONLY on giants + referral companies.
Supports Telegram (recommended) and/or CallMeBot WhatsApp. No-ops safely if unconfigured.
Every send reports whether it was actually delivered, so jobscan.send_alerts can queue and
retry undelivered roles instead of losing them."""
import os, re, json, time, urllib.request, urllib.parse, urllib.error

try:
    import notify_config as N   # local: holds the secrets (gitignored)
except Exception:
    N = None

CHUNK = 10        # roles per Telegram message when a batch is split
SINGLE_MAX = 12   # up to this many roles go out as ONE message

def _cfg(key):
    """Prefer environment (GitHub Actions secrets), fall back to local notify_config.py."""
    return os.environ.get(key) or (getattr(N, key, "") if N else "")

def configured():
    """True when at least one complete channel (Telegram token+chat, or CallMeBot phone+key) is set."""
    return bool((_cfg("TELEGRAM_TOKEN") and _cfg("TELEGRAM_CHAT_ID")) or
                (_cfg("CALLMEBOT_PHONE") and _cfg("CALLMEBOT_APIKEY")))

def _get(url, tries=2):
    """GET; True only on a real success. A Telegram 429 is retried once after its retry_after
    (capped at 30s); a Telegram body with ok:false counts as a failure."""
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "JobScan/1.0"})
            with urllib.request.urlopen(req, timeout=20) as r:
                body = r.read().decode("utf-8", "replace")
                if r.status != 200:
                    return False
                if "api.telegram.org" in url:
                    try:
                        return bool(json.loads(body).get("ok", True))
                    except Exception:
                        return True
                return True
        except urllib.error.HTTPError as e:
            wait = 0
            if e.code == 429:
                try:
                    wait = int(json.loads(e.read().decode("utf-8", "replace"))
                               .get("parameters", {}).get("retry_after", 5))
                except Exception:
                    wait = 5
            print("  notify send err: HTTP %s" % e.code)
            if e.code != 429 or attempt + 1 >= tries:
                return False
            time.sleep(min(max(wait, 1), 30))
        except Exception as e:
            print("  notify send err:", e)
            if attempt + 1 >= tries:
                return False
            time.sleep(2)
    return False

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
    if not configured():
        print("  (notify: no channel configured — message skipped)"); return False
    return _send(text)

def _cv_label(cv):
    """'Hardware_Test_Integration' as-is; old 'Ron Salama - CV (Backend & Full-Stack).pdf' -> the part in ()."""
    cv = cv or ""
    m = re.search(r"\((.*?)\)", cv)
    if m:
        return m.group(1)
    return re.sub(r"^Ron_Salama_(?=.)", "", cv.replace(".pdf", "")) or "?"

def _is_ref(r):
    return bool(r.get("ref")) or "REFERRAL" in ((r.get("openings") or {}).get("note") or "")

def _line(r):
    flag = "\U0001F514REF" if _is_ref(r) else "★"
    return "%s %s — %s [%s]\n\U0001F4C4 CV: %s\n%s" % (flag, r.get("company", ""), (r.get("role") or "")[:70],
                                                      r.get("region", ""), _cv_label(r.get("cv")), r.get("url", ""))

def notify_jobs(rows, failed=None):
    """rows = giant/referral roles (tracker rows or jobscan alert items). Up to SINGLE_MAX roles
    go out as ONE message; a bigger batch is split into CHUNK-role messages (never truncated to
    a '...and N more'). Returns how many roles were actually delivered; the roles of every
    message that failed (or all of them when no channel is configured) are appended to
    `failed` when a list is given, so the caller can queue them for a retry."""
    if not rows:
        return 0
    if not configured():
        print("  (notify: no channel configured — %d giant/referral alerts not delivered)" % len(rows))
        if failed is not None: failed.extend(rows)
        return 0
    chunks = [rows] if len(rows) <= SINGLE_MAX else [rows[i:i + CHUNK] for i in range(0, len(rows), CHUNK)]
    n = len(rows); delivered = 0
    for i, ch in enumerate(chunks):
        head = "\U0001F514 JobScan: %d new giant/referral role%s" % (n, "" if n == 1 else "s")
        if len(chunks) > 1:
            head += " (%d/%d)" % (i + 1, len(chunks))
        if _send("\n\n".join([head] + [_line(r) for r in ch])):
            delivered += len(ch)
        elif failed is not None:
            failed.extend(ch)
        if i + 1 < len(chunks):
            time.sleep(1.1)   # stay under Telegram's per-chat rate limit
    return delivered
