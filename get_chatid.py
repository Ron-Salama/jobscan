# -*- coding: utf-8 -*-
"""One-click Telegram finisher: reads your token from notify_config.py, finds your chat id,
saves it, and sends a test message. Run AFTER you (1) pasted the token and (2) messaged your bot."""
import re, io, sys, json, urllib.request, urllib.parse
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

PATH = r"D:\jobscan\notify_config.py"

def die(msg):
    print("\n>>> " + msg + "\n"); sys.exit()

try:
    import notify_config as N
except Exception:
    die("Can't find notify_config.py in D:\\jobscan — tell Claude.")

tok = (getattr(N, "TELEGRAM_TOKEN", "") or "").strip()
if not tok:
    die("Paste your bot TOKEN into notify_config.py first (the TELEGRAM_TOKEN line), save, then run this again.")

try:
    raw = urllib.request.urlopen("https://api.telegram.org/bot%s/getUpdates" % tok, timeout=20).read().decode("utf-8")
    d = json.loads(raw)
except Exception as e:
    die("Couldn't reach Telegram. Double-check the token was copied fully. (%s)" % e)

if not d.get("ok"):
    die("Telegram rejected the token — re-copy it from BotFather into notify_config.py (no spaces).")

ids = []
for u in d.get("result", []):
    msg = u.get("message") or u.get("edited_message") or u.get("channel_post") or {}
    ch = (msg.get("chat") or {}).get("id")
    if ch: ids.append(ch)

if not ids:
    die("No messages found yet. Open YOUR bot in Telegram and send it any message (e.g. 'hi'), then run this again.")

chat = str(ids[-1])
txt = open(PATH, encoding="utf-8").read()
txt = re.sub(r'TELEGRAM_CHAT_ID\s*=\s*"[^"]*"', 'TELEGRAM_CHAT_ID = "%s"' % chat, txt)
open(PATH, "w", encoding="utf-8").write(txt)
print("Found your chat id: %s  -> saved to notify_config.py" % chat)

try:
    urllib.request.urlopen("https://api.telegram.org/bot%s/sendMessage?%s" % (tok,
        urllib.parse.urlencode({"chat_id": chat,
        "text": "\u2705 JobScan alerts are live! You'll get pinged here on new giant/referral jobs."})),
        timeout=20)
    print("\n>>> Sent you a test message on Telegram — go check it! You're all set. <<<\n")
except Exception as e:
    print("Saved the chat id, but the test message failed:", e)
