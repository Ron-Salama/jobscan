"""Fresh native public-board readers plus isolated compatibility scrapers.

Every reader is bounded. Empty or partial results are never treated as proof
that all jobs have closed. No resume or application information is transmitted.
"""
import concurrent.futures
import contextlib
import io
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from .storage import ROOT, atomic_json

LEGACY=('hiremetech','experis','drushim','amazon')
EXT=('ethosia','dialog','nisha','gotfriends','builtin','linkedin','cps','techjob','alljobs','comeet','apple','camtek')
WORKDAY={'intel':('wd1','External'),'nvidia':('wd5','NVIDIAExternalCareerSite'),'philips':('wd3','jobs-and-careers')}

def session():
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    s=requests.Session()
    s.headers.update({'User-Agent':'JobRadar/2.0 (personal job discovery)','Accept':'application/json'})
    s.mount('https://',HTTPAdapter(max_retries=Retry(total=2,backoff_factor=.5,status_forcelist=[429,500,502,503,504],allowed_methods=['GET','POST'],respect_retry_after_header=False)))
    return s

def greenhouse(board):
    s=session(); r=s.get(f'https://boards-api.greenhouse.io/v1/boards/{board}/jobs',params={'content':'true'},timeout=(10,25)); r.raise_for_status()
    payload=r.json()
    if not isinstance(payload.get('jobs'),list): raise ValueError('Unexpected board response')
    rows=[]
    from .engine import regions_of
    for j in payload['jobs']:
        loc=(j.get('location') or {}).get('name','')
        regions=regions_of(loc)
        # Do not turn a global board into thousands of foreign results. Unknown
        # locations stay visible rather than assuming every city is in Israel.
        if regions==['Outside Israel']: continue
        rows.append({'source':'greenhouse:'+board,'sid':j['id'],'title':j['title'],'company':board,
            'city':loc,'url':j.get('absolute_url'),'desc':j.get('content',''),'posted_at':''})
    return {'jobs':rows,'status':'ok' if rows else 'empty','coverage':'Public board snapshot; known foreign locations omitted. Unknown locations require review.'}

def workday(tenant, checkpoint=None):
    from .engine import clean, regions_of
    wd,site=WORKDAY[tenant]; s=session(); rows={}; details=0; failures=0; capped=False
    root=f'https://{tenant}.{wd}.myworkdayjobs.com'
    api=f'{root}/wday/cxs/{tenant}/{site}'
    # Explicit Israel queries avoid spending the budget on worldwide software
    # results. Bounded searches are labelled as such, never complete coverage.
    for term in ('Israel','Haifa','Yokneam'):
        for offset in range(0,100,20):
            r=s.post(api+'/jobs',json={'appliedFacets':{},'limit':20,'offset':offset,'searchText':term},timeout=(10,25)); r.raise_for_status()
            payload=r.json()
            if not isinstance(payload.get('jobPostings'),list): raise ValueError('Unexpected Workday response')
            postings=payload['jobPostings']
            for j in postings:
                ext=j.get('externalPath','')
                if not ext or ext in rows: continue
                detail={}
                if details<100:
                    details+=1
                    try:
                        d=s.get(api+ext,timeout=(8,15)); d.raise_for_status(); detail=d.json().get('jobPostingInfo',{})
                    except Exception: failures+=1
                else: capped=True
                loc=clean(detail.get('location') or j.get('locationsText'))
                additional=detail.get('additionalLocations') or []
                if additional: loc+='; '+'; '.join(str(x) for x in additional)
                country=detail.get('country') or {}
                country=country.get('descriptor','') if isinstance(country,dict) else str(country)
                if country: loc+='; '+country
                if regions_of(loc)==['Outside Israel']: continue
                rows[ext]={'source':'workday:'+tenant,'sid':ext,'company':tenant.title(),'title':j.get('title',''),
                    'city':loc,'desc':detail.get('jobDescription',''),'url':detail.get('externalUrl') or f'{root}/en-US/{site}{ext}',
                    'posted_at':detail.get('startDate') or j.get('postedOn','')}
            if offset+len(postings)>=payload.get('total',0) or not postings: break
            if offset==80: capped=True
            if checkpoint:
                checkpoint({'jobs':list(rows.values()),'status':'partial','coverage':'Workday scan in progress; partial results retained if the source times out.'})
        if checkpoint:
            checkpoint({'jobs':list(rows.values()),'status':'partial','coverage':'Bounded Workday search; partial results retained if a later query fails.'})
    return {'jobs':list(rows.values()),'status':'partial' if failures or capped else ('ok' if rows else 'empty'),
            'coverage':f'Bounded Israel / Haifa / Yokneam searches, up to 100 results per query and 100 details; {failures} detail failures. Not a full worldwide snapshot.'}

def worker(name, checkpoint=None):
    if name.startswith('greenhouse:'): return greenhouse(name.split(':',1)[1])
    if name.startswith('workday:'): return workday(name.split(':',1)[1],checkpoint)
    if name in LEGACY:
        import legacy_sources as module
    elif name in EXT:
        import sources_ext as module
    else: raise ValueError('Unknown source')
    capture=io.StringIO()
    with contextlib.redirect_stdout(capture),contextlib.redirect_stderr(capture):
        rows=getattr(module,'src_'+name)()
    # Existing scraper routines may catch individual request failures internally.
    # Do not call these fully healthy even if they return rows.
    return {'jobs':rows or [],'status':'partial' if rows else 'empty',
            'coverage':'Compatibility scraper: bounded / prefiltered results; internal request failures may not be reported. No full-coverage guarantee.'}

def collect_one(name, timeout):
    start=time.monotonic()
    with tempfile.TemporaryDirectory(prefix='jobradar-') as tmp:
        output=Path(tmp)/'result.json'
        try:
            p=subprocess.run([sys.executable,'-m','radar.collectors','--worker',name,str(output)],cwd=ROOT,
                             capture_output=True,timeout=timeout)
            if p.returncode or not output.exists():
                return {'jobs':[],'status':'error','coverage':'Reader failed. Prior listings retained.','error':'Source worker failed; check dependencies or source availability.','duration':round(time.monotonic()-start,1)}
            result=json.loads(output.read_text(encoding='utf-8'))
        except subprocess.TimeoutExpired:
            result=json.loads(output.read_text(encoding='utf-8')) if output.exists() else {'jobs':[]}
            result.update(status='timeout',coverage=f'Exceeded {timeout}s source budget. Any checkpointed results retained; coverage incomplete.')
        result['duration']=round(time.monotonic()-start,1)
        return result

def collect(names, prefs, progress=None):
    results={}
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(prefs.get('workers',4),8)) as pool:
        futures={pool.submit(collect_one,n,prefs.get('source_timeout_seconds',180)):n for n in names}
        for f in concurrent.futures.as_completed(futures):
            name=futures[f]
            try: results[name]=f.result()
            except Exception: results[name]={'jobs':[],'status':'error','coverage':'Reader failed; prior listings retained.'}
            if progress: progress(name,results[name],len(results),len(names))
    return results

if __name__=='__main__':
    if len(sys.argv)!=4 or sys.argv[1]!='--worker': raise SystemExit(2)
    try: result=worker(sys.argv[2],lambda data: atomic_json(sys.argv[3],data))
    except Exception as exc:
        # Never print a request URL, response, or credential from an exception.
        result=json.loads(Path(sys.argv[3]).read_text(encoding='utf-8')) if Path(sys.argv[3]).exists() else {'jobs':[]}
        result.update(status='partial' if result['jobs'] else 'error',coverage='Request or response failed; checkpointed and prior listings retained.',error=type(exc).__name__)
    atomic_json(sys.argv[3],result)
