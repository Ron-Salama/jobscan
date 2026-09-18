"""Portable CLI, static export, and a loopback-only dashboard server."""
import argparse
import contextlib
import json
import os
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from . import storage
from .engine import analyze, normalize, regions_of
from .collectors import collect, LEGACY, EXT, WORKDAY

ROOT=storage.ROOT

def initialized():
    prefs=storage.profile(); data=storage.load()
    if not (ROOT/'data/radar.json').exists():
        old=storage.read_json(ROOT/'data/jobs-v1.json',storage.read_json(ROOT/'data/jobs.json',[]))
        data=storage.migrate(data,old,prefs)
    for j in data['jobs']:
        j['regions']=regions_of(j['location'])
        j['analysis']=analyze(j,prefs)
    from .policy import prepare
    prepare(data,prefs)
    return data,prefs

def payload(data,prefs): return {**data,'profile':prefs}

def render_html(data,prefs):
    # Jobs are untrusted input: escape the HTML script boundary too.
    encoded=json.dumps(payload(data,prefs),ensure_ascii=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    return (ROOT/'web/dashboard.html').read_text(encoding='utf-8').replace('__RADAR_DATA__',encoded)

def build(data=None,prefs=None):
    if data is None: data,prefs=initialized()
    target=ROOT/'docs/index.html'; target.parent.mkdir(exist_ok=True)
    tmp=target.with_suffix('.tmp'); tmp.write_text(render_html(data,prefs),encoding='utf-8'); os.replace(tmp,target)
    storage.atomic_json(ROOT/'data/radar.json',data)
    return target

@contextlib.contextmanager
def scan_lock():
    path=ROOT/'data/scan.lock'; path.parent.mkdir(exist_ok=True)
    try: fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    except FileExistsError: raise RuntimeError('A scan lock exists. If no scan is running, remove data/scan.lock and retry.')
    try:
        with os.fdopen(fd,'w') as f: f.write(str(os.getpid()))
        yield
    finally: path.unlink(missing_ok=True)

def validate_sources(names):
    for n in names:
        if n in LEGACY+EXT: continue
        if n.startswith('workday:') and n.split(':',1)[1] in WORKDAY: continue
        if n.startswith('greenhouse:'):
            import re
            if re.fullmatch(r'[a-zA-Z0-9_-]{1,80}',n.split(':',1)[1]): continue
        raise ValueError('Unsupported source: '+n)

def scan(names=None,progress=None,mode='manual',notifications=False):
    with scan_lock():
        data,prefs=initialized(); names=list(dict.fromkeys(names or prefs['sources'])); validate_sources(names)
        tracked={j['id'] for j in data['jobs']}
        batches=collect(names,prefs,progress)
        data,fresh=storage.merge(data,batches,prefs)
        from .policy import apply_scan
        fresh=apply_scan(data,prefs,fresh,mode,tracked)
        if notifications:
            from .alerts import deliver
            deliver(data,prefs,fresh)
        build(data,prefs)
        return data,fresh

def serve(port=8765, open_browser=False):
    # A dashboard opened during a scheduled scan must not overwrite its store.
    if not (ROOT/'data/scan.lock').exists():
        with scan_lock():
            data,prefs=initialized(); build(data,prefs)
    token=secrets.token_urlsafe(32); guard=threading.Lock()
    cache_guard=threading.Lock(); cache={}
    def snapshot():
        # Classifying thousands of saved descriptions on every GET is needless.
        # The scanner owns separate objects; cached snapshots are read-only here.
        key=tuple(p.stat().st_mtime_ns if p.exists() else None for p in (ROOT/'data/radar.json',ROOT/'profile.json'))
        with cache_guard:
            if cache.get('key')!=key:
                cache.update(key=key,value=initialized())
            return cache['value']
    status={'running':False,'completed':0,'total':0,'current':'','message':'Local workspace ready. Refresh checks public listings only.','changed':False}
    def refresh():
        def progress(name,result,done,total):
            with guard: status.update(completed=done,total=total,current=name+' · '+result['status'])
        try:
            data,fresh=scan(progress=progress)
            with guard: status.update(message=f"Refresh complete: {len(fresh)} newly discovered; {len(data['jobs'])} retained. Review source health for coverage.",changed=True)
        except Exception as e:
            with guard: status.update(message='Refresh failed: '+str(e))
        finally:
            with guard: status['running']=False
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def valid_host(self): return self.headers.get('Host') in (f'127.0.0.1:{port}',f'localhost:{port}')
        def reply(self,code,body,kind='application/json'):
            self.send_response(code); self.send_header('Content-Type',kind+'; charset=utf-8'); self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff'); self.send_header('Referrer-Policy','no-referrer'); self.end_headers()
            try: self.wfile.write(body.encode('utf-8'))
            except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError): pass
        def do_GET(self):
            if not self.valid_host(): return self.reply(403,'{}')
            if self.path=='/':
                data,prefs=snapshot(); return self.reply(200,render_html(data,prefs),'text/html')
            if self.path=='/api/status':
                with guard: result={**status,'token':token}
                if (ROOT/'data/scan.lock').exists() and not result['running']:
                    result.update(running=True,total=len(storage.profile()['sources']),current='Command-line scan')
                result['changed']=True
                return self.reply(200,json.dumps(result))
            if self.path=='/api/data':
                data,prefs=snapshot(); return self.reply(200,json.dumps(payload(data,prefs),ensure_ascii=False))
            self.reply(404,'{}')
        def do_POST(self):
            if not self.valid_host() or self.headers.get('X-Radar-Token')!=token: return self.reply(403,'{}')
            origin=self.headers.get('Origin')
            if origin and origin not in (f'http://127.0.0.1:{port}',f'http://localhost:{port}'): return self.reply(403,'{}')
            if self.path=='/api/profile':
                try:
                    length=int(self.headers.get('Content-Length','0'))
                    if not 0<length<=20000: return self.reply(400,'{}')
                    incoming=json.loads(self.rfile.read(length)); prefs=storage.profile()
                    years=float(incoming['experience_years'])
                    if not 0<=years<=30: raise ValueError('Experience must be between 0 and 30 years')
                    prefs['experience_years']=years
                    for key in ('skills','learning','excluded_regions','sources'):
                        values=incoming.get(key,prefs[key])
                        if not isinstance(values,list) or len(values)>100 or any(not isinstance(v,str) or len(v)>100 for v in values): raise ValueError('Invalid profile list')
                        prefs[key]=list(dict.fromkeys(v.strip() for v in values if v.strip()))
                    validate_sources(prefs['sources'])
                    if not prefs['sources']: raise ValueError('Select at least one source')
                    with scan_lock():
                        storage.atomic_json(ROOT/'profile.json',prefs)
                        data,_=initialized(); build(data,prefs)
                    return self.reply(200,json.dumps(payload(data,prefs),ensure_ascii=False))
                except (ValueError,KeyError,TypeError,RuntimeError) as e:
                    return self.reply(400,json.dumps({'error':str(e)}))
            if self.path!='/api/scan': return self.reply(404,'{}')
            with guard:
                if status['running']: return self.reply(409,'{"error":"Scan already running"}')
                status.update(running=True,completed=0,total=len(storage.profile()['sources']),changed=False)
            threading.Thread(target=refresh,daemon=True).start(); self.reply(202,'{"started":true}')
    url=f'http://127.0.0.1:{port}'
    try: server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    except OSError:
        print(f'Port {port} is already in use. An existing Radar may be running at {url}. Use --port to choose another.',flush=True)
        if open_browser:
            import webbrowser
            webbrowser.open(url)
        return
    print(f'Job Radar: {url}  (Ctrl+C to stop)',flush=True)
    if open_browser:
        import webbrowser
        webbrowser.open(url)
    server.serve_forever()

def main(argv=None):
    parser=argparse.ArgumentParser(description='Job Radar: transparent discovery, no automated applications.')
    sub=parser.add_subparsers(dest='command')
    s=sub.add_parser('scan',help='Collect public listings and rebuild dashboard'); s.add_argument('--sources',help='Comma-separated source names'); s.add_argument('--notify',action='store_true',help='Explicitly send new early-career listings through the configured notification channel')
    s.add_argument('--mode',choices=['manual','giants','daily'],default='manual')
    sub.add_parser('build',help='Rebuild saved listings without network requests')
    s=sub.add_parser('serve',help='Start local dashboard'); s.add_argument('--port',type=int,default=8765); s.add_argument('--open',action='store_true',help='Open dashboard in your browser')
    sub.add_parser('sources',help='Show configured sources')
    s=sub.add_parser('import',help='Import raw JSON listings for offline review'); s.add_argument('file')
    args=parser.parse_args(argv); command=args.command or 'serve'
    if command=='serve': serve(getattr(args,'port',8765),getattr(args,'open',False))
    elif command=='sources': print('\n'.join(storage.profile()['sources']))
    elif command=='build':
        with scan_lock(): print('Built',build())
    elif command=='scan':
        def report(n,r,d,t): print(f"[{d}/{t}] {n}: {r['status']} ({len(r.get('jobs',[]))} listings)",flush=True)
        data,fresh=scan(args.sources.split(',') if args.sources else None,report,args.mode,args.notify)
        print(f"Saved {len(data['jobs'])} listings; {len(fresh)} newly discovered.")
    elif command=='import':
        raw=storage.read_json(Path(args.file),None)
        if not isinstance(raw,list): parser.error('Import must be a JSON list of listings')
        with scan_lock():
            data,prefs=initialized()
            for row in raw:
                item=normalize(dict(row,imported=True),prefs)
                item.update(first_seen=storage.now(),last_seen=None,availability='unverified',availability_note='Manually imported; not observed by a source reader.')
                if not any(j['id']==item['id'] for j in data['jobs']): data['jobs'].append(item)
            build(data,prefs)
        print(f'Imported / retained {len(data["jobs"])} listings.')

if __name__=='__main__': main()
