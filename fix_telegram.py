# -*- coding: utf-8 -*-
import io, sys, json, re, urllib.request, urllib.parse
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import notify_config as N
tok = N.TELEGRAM_TOKEN.strip()
PATH = r"D:\jobscan\notify_config.py"

def api(method, params=None):
    url = "https://api.telegram.org/bot%s/%s" % (tok, method)
    if params: url += "?" + urllib.parse.urlencode(params)
    return json.loads(urllib.request.urlopen(url, timeout=20).read().decode("utf-8"))

wh = api("getWebhookInfo")
print("webhook url:", repr(wh["result"].get("url","")))
print("pending_update_count:", wh["result"].get("pending_update_count"))
if wh["result"].get("url"):
    print("-> deleting webhook (it was swallowing your messages)...")
    print("   deleteWebhook:", api("deleteWebhook", {"drop_pending_updates": "false"}).get("result"))

u = api("getUpdates", {"timeout": 0})
res = u.get("result", [])
print("updates now:", len(res))
ids = []
for x in res:
    msg = x.get("message") or x.get("edited_message") or x.get("channel_post") or {}
    ch = (msg.get("chat") or {}).get("id")
    if ch: ids.append(ch)

if ids:
    chat = str(ids[-1])
    txt = open(PATH, encoding="utf-8").read()
    txt = re.sub(r'TELEGRAM_CHAT_ID\s*=\s*"[^"]*"', 'TELEGRAM_CHAT_ID = "%s"' % chat, txt)
    open(PATH, "w", encoding="utf-8").write(txt)
    print("FOUND chat id:", chat, "-> saved.")
    api("sendMessage", {"chat_id": chat,
        "text": "\u2705 JobScan alerts are live! You'll get pinged here on new giant/referral jobs."})
    print(">>> Test message sent — check Telegram! <<<")
else:
    print(">>> Webhook cleared. Now send your bot ONE more message ('hi') and tell me — it'll work now. <<<")
