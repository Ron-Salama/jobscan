"""Versioned store, exact posting identity, atomic writes, conservative freshness."""
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from .engine import normalize, analyze

ROOT=Path(__file__).resolve().parents[1]

def now(): return datetime.now(timezone.utc).isoformat(timespec='seconds')

def atomic_json(path, data):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix=path.name+'.',suffix='.tmp',dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:
            json.dump(data,f,ensure_ascii=False,indent=2); f.flush(); os.fsync(f.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name): os.unlink(name)

def read_json(path, default):
    try: return json.loads(Path(path).read_text(encoding='utf-8-sig'))
    except FileNotFoundError: return default
    # Corrupt state is a visible error, never silently replaced with an empty store.

def profile(): return read_json(ROOT/'profile.json',{})

def load(path=None):
    return read_json(path or ROOT/'data/radar.json',{'version':2,'updated_at':None,'jobs':[], 'sources':{},'runs':[]})

def migrate(store, old_rows, prefs):
    if store['jobs']: return store
    for raw in old_rows:
        raw=dict(raw,imported=True)
        try: item=normalize(raw,prefs)
        except ValueError: continue
        item.update(first_seen=raw.get('date') or now(),last_seen=None,availability='unverified',
                    legacy_url=raw.get('url',''),availability_note='Imported from the previous tracker; not yet observed by this version.')
        store['jobs'].append(item)
    return store

def merge(store, batches, prefs, timestamp=None):
    stamp=timestamp or now(); fresh=[]; rejected=0
    by={j['id']:j for j in store['jobs']}
    for source,batch in batches.items():
        received=set(); valid=0
        for raw in batch.get('jobs',[]):
            try: item=normalize(raw,prefs)
            except (ValueError,TypeError,KeyError): rejected+=1; continue
            received.add(item['id']); valid+=1
            previous=by.get(item['id'])
            if previous:
                item['sources']=sorted(set(item['sources']+previous.get('sources',[])))
                item['source_ids']=sorted(set(item['source_ids']+previous.get('source_ids',[])))
                # A transient listing-only response must not erase a previous full JD.
                if len(item['description'])<len(previous.get('description','')):
                    item['description']=previous['description']; item['description_seen_at']=previous.get('description_seen_at')
                    item['analysis']=analyze(item,prefs)
                else: item['description_seen_at']=stamp if item['description'] else None
                item['first_seen']=previous['first_seen']; item['legacy_url']=previous.get('legacy_url',previous.get('url',''))
                item['daily_basis']=previous.get('daily_basis')
                if not item.get('reported_posted'): item['reported_posted']=previous.get('reported_posted','')
            else:
                item['first_seen']=stamp; item['description_seen_at']=stamp if item['description'] else None
                fresh.append(item['id'])
            item['last_seen']=stamp; item['imported']=False
            # Observed on a listing feed, not independently confirmed open by an employer.
            item['availability']='observed' if item['active_signal'] else 'closed'
            item['availability_note']='Seen in a source response; check the original before applying.' if item['active_signal'] else 'Source explicitly marked the posting inactive.'
            by[item['id']]=item
        health={k:v for k,v in batch.items() if k!='jobs'}
        health.update(last_attempt=stamp,received=valid)
        prior=store['sources'].get(source,{})
        health['last_nonempty']=stamp if valid else prior.get('last_nonempty')
        store['sources'][source]=health
    ref=datetime.fromisoformat(stamp)
    for item in by.values():
        last=item.get('last_seen')
        if item.get('availability')=='observed' and last:
            age=(ref-datetime.fromisoformat(last)).total_seconds()/86400
            if age>=prefs.get('stale_after_days',14):
                item['availability']='stale'; item['availability_note']='Not observed recently. This is not proof that the role closed.'
        item['analysis']=analyze(item,prefs)
    store['jobs']=sorted(by.values(),key=lambda j:j.get('first_seen') or '',reverse=True)
    store['updated_at']=stamp
    store['runs']=(store.get('runs',[])+[{'at':stamp,'sources':len(batches),'new':len(fresh),'invalid':rejected}])[-40:]
    return store,fresh
