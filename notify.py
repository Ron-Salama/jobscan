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

# 4xx answers that mean the CHANNEL is misconfigured (bad token -> 401/404, bot blocked -> 403,
# wrong chat id -> 400 'chat not found'), not that this one message is bad: every message would
# get them, so they stay retryable failures (queued; the 3-strike CI alarm still fires).
_CONFIG_4XX = (401, 403, 404)

def _call(url, data=None, tries=2):
    """GET, or POST when `data` (bytes) is given. Returns True on a real success; False on a
    failure worth retrying later (network, 5xx, 429 after its wait, channel misconfiguration);
    None when the server REJECTED this message (any other non-429 4xx, e.g. 400 'message is too
    long') - resending the same text can never succeed. A Telegram 429 is retried once after its
    retry_after (capped at 30s); a Telegram body with ok:false counts as a failure."""
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers={"User-Agent": "JobScan/1.0"})
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
            try:
                info = json.loads(e.read().decode("utf-8", "replace"))
                if not isinstance(info, dict): info = {}
            except Exception:
                info = {}
            desc = str(info.get("description") or "")
            print("  notify send err: HTTP %s%s" % (e.code, (" " + desc) if desc else ""))
            if e.code == 429:
                if attempt + 1 >= tries:
                    return False
                try:
                    wait = int((info.get("parameters") or {}).get("retry_after", 5))
                except Exception:
                    wait = 5
                time.sleep(min(max(wait, 1), 30))
                continue
            if (400 <= e.code < 500 and e.code not in _CONFIG_4XX
                    and "chat not found" not in desc.lower()):
                return None
            return False
        except Exception as e:
            print("  notify send err:", e)
            if attempt + 1 >= tries:
                return False
            time.sleep(2)
    return False

def _send(text):
    """True = delivered on at least one channel; False = a retryable failure; None = every
    configured channel rejected this message (see _call). Telegram goes out as a POST form, so
    the text never rides in a (length-limited, logged) URL."""
    results = []
    tok = _cfg("TELEGRAM_TOKEN"); chat = _cfg("TELEGRAM_CHAT_ID")
    if tok and chat:
        results.append(_call("https://api.telegram.org/bot%s/sendMessage" % tok,
                             data=urllib.parse.urlencode({"chat_id": chat, "text": text,
                                                          "disable_web_page_preview": "false"}).encode("utf-8")))
    phone = _cfg("CALLMEBOT_PHONE"); key = _cfg("CALLMEBOT_APIKEY")
    if phone and key:
        results.append(_call("https://api.callmebot.com/whatsapp.php?%s" % urllib.parse.urlencode(
              {"phone": phone, "text": text, "apikey": key})))
    if any(r is True for r in results):
        return True
    if results and all(r is None for r in results):
        return None
    return False

def notify_text(text):
    """Send one plain message (batch-summary nudge, source-dark warning). No-op if unconfigured."""
    if not configured():
        print("  (notify: no channel configured — message skipped)"); return False
    return bool(_send(text))

def _cv_label(cv):
    """'Hardware_Test_Integration' as-is; the general 'Ron_Salama_CV' -> 'General';
    old 'Ron Salama - CV (Backend & Full-Stack).pdf' -> the part in ()."""
    cv = cv or ""
    m = re.search(r"\((.*?)\)", cv)
    if m:
        return m.group(1)
    base = cv.replace(".pdf", "")
    if base == "Ron_Salama_CV":
        return "General"
    return re.sub(r"^Ron_Salama_(?=.)", "", base) or "?"

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
    `failed` when a list is given, so the caller can queue them for a retry. A single-role
    message the channel REJECTS (non-429 4xx, not a config error) is logged and dropped:
    re-queueing it would fail the same way on every run."""
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
        res = _send("\n\n".join([head] + [_line(r) for r in ch]))
        if res:
            delivered += len(ch)
        elif res is None and len(ch) == 1:
            print("  notify: message REJECTED for %s — %s (dropped, not queued): %s"
                  % (ch[0].get("company", ""), (ch[0].get("role") or "")[:60], ch[0].get("url", "")))
        elif failed is not None:
            failed.extend(ch)
        if i + 1 < len(chunks):
            time.sleep(1.1)   # stay under Telegram's per-chat rate limit
    return delivered
