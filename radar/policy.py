"""Ron's company lists, relevant-only tracker, and explicit discovery dates."""
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

def company_matches(company, names):
    def norm(s): return re.sub(r'[^a-z0-9]+', ' ', s.lower()).strip()
    value=' '+norm(company)+' '
    return any(' '+norm(name)+' ' in value for name in names if norm(name))

def flags(job, prefs):
    a=job['analysis']
    return {
        'giant':company_matches(job['company'],prefs.get('giants',[])),
        'referral':company_matches(job['company'],prefs.get('referral_companies',[])),
        'tailor':bool(retain(job) and len(job.get('description',''))>=200 and a.get('matched')),
    }

def retain(job):
    from .engine import SENIOR
    a=job['analysis']
    if a['bucket'] in ('other','outside'): return False
    if re.search(SENIOR,job['title'],re.I) or job.get('level','').lower() in ('senior','lead','principal','staff','manager'): return False
    # Reject specialist titles, not incidental hardware context in software JDs.
    if re.search(r'\b(rtl|asic|vlsi|physical design|analog|rf|design verification|research scientist|mechanical|electrical|process)\b',job['title'],re.I): return False
    required=[e['min'] for e in a.get('experience',[]) if e['kind']=='stated' and not e.get('alternative')]
    return not required or max(required)<=3

def prepare(data,prefs):
    if not prefs.get('relevant_only'): return
    history=data.setdefault('discovered',{})
    for j in data['jobs']:
        history.setdefault(j['id'],j.get('first_seen'))
        j['flags']=flags(j,prefs)
    data['jobs']=[j for j in data['jobs'] if retain(j)]

def parsed_date(value):
    try:
        dt=datetime.fromisoformat(value.replace('Z','+00:00'))
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    except (ValueError,TypeError,AttributeError): return None

def recent_basis(job, now, prefs):
    """Don't pretend a calendar date or first discovery is a precise posting time."""
    raw=job.get('reported_posted','').strip()
    cutoff=now-timedelta(hours=24)
    dt=parsed_date(raw)
    if dt and len(raw)>10:
        return 'Posted in the last 24 hours' if cutoff<=dt<=now else None
    local=now.astimezone(ZoneInfo(prefs.get('timezone','Asia/Jerusalem')))
    if dt:
        if dt.date()<cutoff.astimezone(local.tzinfo).date() or dt.date()>local.date(): return None
        return 'Recent posting date; exact time unverified'
    relative=re.fullmatch(r'(?:posted\s+)?(?:(today)|(yesterday)|(\d+)\+?\s+days?\s+ago)',raw,re.I)
    if relative:
        days=0 if relative[1] else 1 if relative[2] else int(relative[3])
        if days>1: return None
        return 'Source reports today/yesterday; exact time unverified'
    first=parsed_date(job.get('first_seen'))
    if prefs.get('include_undated_new',True) and first and cutoff<=first<=now:
        return 'Newly discovered; posting date unverified'
    return None

def apply_scan(data,prefs,fresh,mode,tracked):
    now=parsed_date(data['updated_at']); history=data.setdefault('discovered',{})
    existing=set(history)
    for j in data['jobs']:
        if j['id'] in history: j['first_seen']=history[j['id']]
    fresh=[i for i in fresh if i not in existing]
    prepare(data,prefs)
    for j in data['jobs']: j['flags']=flags(j,prefs)
    if mode=='giants':
        # Only giants enter the tracker between daily updates.
        data['jobs']=[j for j in data['jobs'] if j['id'] in tracked or j['flags']['giant']]
    elif mode=='daily':
        for j in data['jobs']: j['daily_basis']=recent_basis(j,now,prefs)
        data['daily']={'at':data['updated_at'],'ids':[j['id'] for j in data['jobs'] if j.get('daily_basis')]}
        data['jobs']=[j for j in data['jobs'] if j['id'] in tracked or j.get('daily_basis')]
    return fresh
