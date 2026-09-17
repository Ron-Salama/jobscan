# -*- coding: utf-8 -*-
# Copy this file to  notify_config.py  and fill in ONE of the two options.
# (Keep notify_config.py private — it holds your keys.)

# ---- Option A: Telegram (recommended — free, reliable, official) ----
# 1. In Telegram, message @BotFather -> /newbot -> follow prompts -> it gives you a TOKEN.
# 2. Message your new bot once (say "hi") so it can message you back.
# 3. Get your chat id: open https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates in a browser,
#    find  "chat":{"id": <number> ...}  -> that number is TELEGRAM_CHAT_ID.
TELEGRAM_TOKEN   = ""     # e.g. "8123456789:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
TELEGRAM_CHAT_ID = ""     # e.g. "123456789"

# ---- Option B: WhatsApp via CallMeBot (free relay, opt-in once) ----
# 1. Save +34 644 51 95 23 as a contact, then WhatsApp it:  "I allow callmebot to send me messages"
# 2. It replies with your personal apikey.
CALLMEBOT_PHONE  = ""     # your number in intl format, e.g. "9725XXXXXXXX"
CALLMEBOT_APIKEY = ""     # the key CallMeBot sends you
