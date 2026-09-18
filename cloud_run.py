"""Unattended GitHub scans; no PC or assistant required."""
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from radar import storage
from radar.app import scan, build

def due(now,data,manual=False):
    local=now.astimezone(ZoneInfo('Asia/Jerusalem'))
    last=data.get('schedule',{}).get('daily_date')
    if local.hour>=17 and last!=local.date().isoformat(): return 'daily'
    if manual or now.hour%2==0: return 'giants'
    return None

def main():
    now=datetime.now(timezone.utc)
    mode=due(now,storage.load(),os.environ.get('GITHUB_EVENT_NAME')=='workflow_dispatch')
    if not mode:
        print('No scan due at this daylight-saving offset.'); return
    print('Running',mode,'scan',flush=True)
    def report(n,r,d,t): print(f"[{d}/{t}] {n}: {r['status']} ({len(r.get('jobs',[]))})",flush=True)
    data,_=scan(progress=report,mode=mode,notifications=True)
    schedule=data.setdefault('schedule',{})
    schedule[mode+'_at']=storage.now()
    if mode=='daily': schedule['daily_date']=now.astimezone(ZoneInfo('Asia/Jerusalem')).date().isoformat()
    build(data,storage.profile())

if __name__=='__main__': main()
