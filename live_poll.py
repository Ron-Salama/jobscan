# -*- coding: utf-8 -*-
"""Live long-poll: waits up to ~2 min for a fresh message to the bot, then saves chat id + pings."""
import io, sys, json, re, urllib.request, urllib.parse
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import notify_config as N
tok = N.TELEGRAM_TOKEN.strip()
PATH = r"D:\jobscan\notify_config.py"

def api(method, params=None, to=50):
    url = "https://api.telegram.org/bot%s/%s" % (tok, method)
    if params: url += "?" + urllib.parse.urlencode(params)
    return json.loads(urllib.request.urlopen(url, timeout=to).read().decode("utf-8"))

print("listening ~2 min for a fresh message... send your bot 'test' now.")
chat = None
offset = None
for _ in range(3):                       # 3 x 40s long-polls
    p = {"timeout": 40}
    if offset is not None: p["offset"] = offset
    try:
        u = api("getUpdates", p, to=50)
    except Exception as e:
        print("poll err:", e); continue
    for x in u.get("result", []):
        offset = x["update_id"] + 1
        m = x.get("message") or x.get("edited_message") or {}
        ch = (m.get("chat") or {}).get("id")
        if ch:
            chat = str(ch); print("GOT message from chat_id", chat, "text=", repr((m.get("text") or "")[:20]))
    if chat: break

if chat:
    txt = open(PATH, encoding="utf-8").read()
    txt = re.sub(r'TELEGRAM_CHAT_ID\s*=\s*"[^"]*"', 'TELEGRAM_CHAT_ID = "%s"' % chat, txt)
    open(PATH, "w", encoding="utf-8").write(txt)
    api("sendMessage", {"chat_id": chat,
        "text": "\u2705 JobScan alerts are live! You'll get pinged here on new giant/referral jobs."})
    print(">>> SUCCESS: chat id %s saved + test ping sent. Check Telegram! <<<" % chat)
else:
    print(">>> Still nothing after ~2 min. The message isn't reaching THIS bot token. <<<")
