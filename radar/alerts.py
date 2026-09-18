"""Telegram only. Persist pending alerts and retry failed deliveries."""
import json
import urllib.request
from .storage import atomic_json, ROOT

def eligible(j):
    return (j.get('flags',{}).get('giant') and j['analysis']['bucket'] in ('consider','stretch')
            and len(j.get('description',''))>=200 and j.get('availability')=='observed'
            and any(r in ('North','Center') for r in j.get('regions',[])))

def send(text):
    from notify import _cfg
    token,chat=_cfg('TELEGRAM_TOKEN'),_cfg('TELEGRAM_CHAT_ID')
    if not token or not chat: return False
    req=urllib.request.Request('https://api.telegram.org/bot'+token+'/sendMessage',
        data=json.dumps({'chat_id':chat,'text':text,'disable_web_page_preview':True}).encode(),
        headers={'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(req,timeout=25) as response:
            return bool(json.load(response).get('ok'))
    except Exception as e:
        print('Telegram delivery failed:',type(e).__name__)
        return False

def deliver(data,prefs,fresh):
    state=data.setdefault('alerts',{'pending':[],'sent':{}})
    by={j['id']:j for j in data['jobs']}
    state['pending']=list(dict.fromkeys(state['pending']+[i for i in fresh if i in by and eligible(by[i]) and i not in state['sent']]))
    # Save the queue before any external action. Successful messages are checkpointed.
    atomic_json(ROOT/'data/radar.json',data)
    for key in list(state['pending']):
        j=by.get(key)
        if not j or not eligible(j):
            state['pending'].remove(key); continue
        markers=[]
        if j['flags']['referral']: markers.append('Potential referral')
        if j['flags']['tailor']: markers.append('Tailoring candidate')
        text='New giant-company role\n'+j['company']+' — '+j['title'][:180]+'\n'+j['location']+'\n'+' · '.join(markers)+'\n'+j['url']
        if not send(text): break
        state['sent'][key]=data['updated_at']; state['pending'].remove(key)
        atomic_json(ROOT/'data/radar.json',data)
    atomic_json(ROOT/'data/radar.json',data)
