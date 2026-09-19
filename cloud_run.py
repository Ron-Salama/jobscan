"""Unattended GitHub scans; no PC or assistant required."""
import os
import sys
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from radar import storage
from radar.app import scan, build

def due(now,data,manual=False):
    local=now.astimezone(ZoneInfo('Asia/Jerusalem'))
    schedule=data.get('schedule',{})
    last=schedule.get('daily_date')
    target=local.date() if local.hour>=17 else local.date()-timedelta(days=1)
    if (last and last<target.isoformat()) or (not last and local.hour>=17): return 'daily'
    previous=[schedule.get('giants_at'),schedule.get('daily_at')]
    times=[datetime.fromisoformat(t) for t in previous if t]
    if manual or not times or now-max(times)>=timedelta(hours=2): return 'giants'
    return None

def main():
    now=datetime.now(timezone.utc)
    mode=due(now,storage.load(),os.environ.get('GITHUB_EVENT_NAME')=='workflow_dispatch')
    if '--check' in sys.argv:
        with open(os.environ['GITHUB_OUTPUT'],'a',encoding='utf-8') as f:
            f.write('due='+str(bool(mode)).lower()+'\n')
        print('Due:',mode or 'nothing'); return
    if not mode:
        print('No scan due at this daylight-saving offset.'); return
    print('Running',mode,'scan',flush=True)
    def report(n,r,d,t): print(f"[{d}/{t}] {n}: {r['status']} ({len(r.get('jobs',[]))})",flush=True)
    data,_=scan(progress=report,mode=mode,notifications=True)
    schedule=data.setdefault('schedule',{})
    schedule[mode+'_at']=storage.now()
    if mode=='daily':
        local=now.astimezone(ZoneInfo('Asia/Jerusalem'))
        target=local.replace(hour=17,minute=0,second=0,microsecond=0)
        if local.hour<17: target-=timedelta(days=1)
        schedule['daily_date']=target.date().isoformat()
        schedule['daily_target_at']=target.isoformat()
        schedule['daily_started_at']=now.isoformat(timespec='seconds')
        schedule['daily_delay_minutes']=round((now-target).total_seconds()/60)
    build(data,storage.profile())

if __name__=='__main__': main()
