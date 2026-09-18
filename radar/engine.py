"""Pure normalization and explainable triage. Never silently discard a listing."""
import hashlib
import html
import re
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

NORTH = ('haifa','חיפה','yokneam','yoqneam','יקנעם','karmiel','carmiel','כרמיאל','migdal ha','מגדל העמק','nazareth','נצרת','krayot','קריות','nesher','נשר','nahariya','נהריה','caesarea','קיסריה','hadera','חדרה','afula','עפולה','tefen','תפן','north','צפון','misgav','משגב','tirat carmel','טירת כרמל')
CENTER = ('tel aviv','tel-aviv','תל אביב','ת"א','השרון','sharon','herzli','הרצליה','petah','petach','פתח תקווה','netanya','נתניה','raanana',"ra'anana",'רעננה','rehovot','רחובות','kfar saba','כפר סבא','ramat gan','רמת גן','holon','חולון','rosh ha','ראש העין','hod hasharon','הוד השרון','modiin',"modi'in",'מודיעין','center','central','מרכז','lod','לוד','yavne','יבנה','or yehuda','אור יהודה','bnei brak','בני ברק','givatayim','גבעתיים')
SOUTH = ('beer sheva',"be'er sheva",'beersheba','באר שבע','ashdod','אשדוד','ashkelon','אשקלון','kiryat gat','קריית גת','eilat','אילת','south','דרום')
JERUSALEM = ('jerusalem','ירושלים','har hotzvim','הר חוצבים')
FOREIGN = ('india','gurugram','bangalore','bengaluru','united states','usa','california','santa clara','new york','germany','berlin','london','united kingdom','poland','warsaw','canada','china','taiwan','singapore')
JUNIOR = r'\b(junior|jr\.?|graduate|entry[ -]level|college grad|new grad)\b|גוניור|ג׳וניור|ללא ניסיון|בוגר'
SENIOR = r'\b(senior|sr\.?|principal|staff|architect|director|manager|head of|team lead(?:er)?|tech lead|lead developer|lead engineer|lead software)\b|בכיר|ראש צוות|מנהל'
DEV = r'\b(software|developer|development engineer|programmer|firmware|embedded|backend|frontend|full[ -]?stack|devops|sdet|automation|validation|integration|data engineer|ai engineer|application engineer|applications engineer|technical artist|gameplay|unity)\b|תוכנה|מפתח|אוטומציה|אינטגרציה'
SKILLS = {
    'Python': r'\bpython\b', 'C#': r'(?<!\w)c#|\.net\b', 'C': r'(?<![\w+])c(?![\w+#])',
    'C++': r'(?<!\w)c\+\+', 'TypeScript': r'\btypescript\b', 'JavaScript': r'\bjavascript\b',
    'Java': r'\bjava\b', 'SQL': r'\bsql\b|mysql|postgres', 'React': r'\breact\b',
    'Next.js': r'\bnext\.?js\b', 'Firebase': r'firebase|firestore', 'Git': r'\bgit\b|github',
    'LLM APIs': r'\bllms?\b|gemini|generative ai|genai|openai', 'RAG': r'\brag\b|retrieval.augmented',
    'MCP': r'\bmcp\b|model context protocol', 'Azure': r'\bazure\b', 'AWS': r'\baws\b|amazon web services',
    'Docker': r'\bdocker\b', 'Kubernetes': r'kubernetes|\bk8s\b', 'CI/CD': r'ci/cd|ci-cd|continuous integration',
    'Linux': r'\blinux\b', 'RTOS': r'\brtos\b|freertos', 'Unity': r'\bunity\b',
    'I2C': r'\bi2c\b', 'SCPI': r'\bscpi\b', 'REST APIs': r'\brest\b|restful',
}

def clean(value):
    text = html.unescape(str(value or ''))
    text = re.sub(r'<\s*(?:br\s*/?|/p|/li|/div|/h\d)\s*>', '\n', text, flags=re.I)
    text = re.sub(r'<[^>]+>', '', text)
    return re.sub(r'[ \t]+', ' ', text).strip()

def canonical_url(value):
    try:
        u = urlsplit(str(value or '').strip())
        if u.scheme not in ('https', 'http') or not u.hostname or u.username or u.password:
            return ''
        query = [(k,v) for k,v in parse_qsl(u.query, keep_blank_values=True)
                 if not k.lower().startswith('utm_') and k.lower() not in ('source','ref','trk','trackingid')]
        return urlunsplit((u.scheme.lower(), u.netloc.lower(), u.path.rstrip('/'), urlencode(sorted(query)), ''))
    except ValueError:
        return ''

def regions_of(location):
    t = location.lower()
    result = []
    for region, words in [('North',NORTH),('Center',CENTER),('South',SOUTH),('Jerusalem',JERUSALEM)]:
        if any(w in t for w in words): result.append(region)
    if result: return result
    if any(w in t for w in FOREIGN) and not re.search(r'israel|ישראל',t): return ['Outside Israel']
    # Remote is not assumed to mean eligible to work from Israel.
    return ['Unknown']

def experience_evidence(description):
    """Return quoted claims, distinguishing preferred requirements and alternatives.

    A range keeps its lower bound. Multiple distinct requirements remain visible;
    degree alternatives are not reduced to a fabricated universal minimum.
    """
    text = clean(description)
    result = []; preference_section = False
    for line in text.splitlines():
        lower = line.lower().strip()
        if re.search(r'preferred qualifications|nice.to.have|ways to stand out|יתרון',lower): preference_section = True
        if re.search(r'basic qualifications|required qualifications|minimum qualifications|what we need|דרישות חובה',lower): preference_section = False
        pattern = r'(?<!\d)(\d{1,2})(?:\s*(?:[-–—]|to)\s*(\d{1,2}))?\s*(\+)?\s*(?:years?\b|yrs?\b|שנות|שנים|שנה)'
        for m in re.finditer(pattern,line,re.I):
            lo=int(m[1]); hi=int(m[2]) if m[2] else None
            if lo>30 or (hi is not None and hi<lo): continue
            start=max(0,m.start()-70); end=min(len(line),m.end()+110)
            quote=line[start:end].strip()
            context=quote.lower()
            if not re.search(r'experience|ניסיון|נסיון',context): continue
            if re.search(r'over the past|founded|company has|company with|combined experience',context): continue
            sentence_start=max(line.rfind('.',0,m.start()),line.rfind(';',0,m.start()))+1
            sentence_end=line.find('.',m.end())
            sentence=line[sentence_start:sentence_end if sentence_end>=0 else len(line)].lower()
            preferred = preference_section or bool(re.search(r'preferred|nice.to.have|advantage|יתרון',sentence))
            alternative=bool(re.search(r'\bor\b|alternatively|או ',sentence))
            result.append({'min':lo,'max':hi,'plus':bool(m[3]),'kind':'preferred' if preferred else 'stated', 'alternative':alternative,'quote':quote})
    return result

def analyze(job, profile):
    title=job['title']; desc=job['description']; blob=title+'\n'+desc
    reasons=[]; warnings=[]
    evidence=experience_evidence(desc)
    required=[e['min'] for e in evidence if e['kind']=='stated']
    alternatives=any(e['alternative'] for e in evidence if e['kind']=='stated')
    minimum=max(required) if required and not alternatives else None
    junior=bool(re.search(JUNIOR,title,re.I)) or job.get('level','').lower() in ('junior','entry','entry level','associate') or bool(re.search(r'job type\s*:?\s*college grad|recent graduates? welcome|new graduate role',desc,re.I))
    senior=bool(re.search(SENIOR,title,re.I)) or job.get('level','').lower() in ('senior','lead','principal','staff','manager')
    student=bool(re.search(r'\b(intern|internship|student)\b|סטודנט',title,re.I))
    relevant=bool(re.search(DEV,title,re.I))
    known=set(profile.get('skills',[])); learning=set(profile.get('learning',[]))
    mentions=[name for name,pattern in SKILLS.items() if re.search(pattern,blob,re.I)]
    matched=[s for s in mentions if s in known]
    learning_mentions=[s for s in mentions if s in learning and s not in known]
    unconfirmed=[s for s in mentions if s not in known and s not in learning]
    bucket='review'
    if not relevant:
        bucket='other'; reasons.append('Title does not clearly identify a software or integration role.')
    elif student:
        bucket='other'; reasons.append('Title explicitly targets students or interns; confirm graduate eligibility.')
    elif senior:
        bucket='stretch'; reasons.append('Title explicitly indicates seniority.')
    elif minimum is not None and minimum>profile.get('experience_years',1)+1:
        bucket='stretch'; reasons.append(f'Description states {minimum}+ years of experience; inspect the quoted requirements.')
    elif junior or (minimum is not None and minimum<=profile.get('experience_years',1)+1):
        bucket='consider'; reasons.append('Explicit early-career signal or experience requirement within your target range.')
    else:
        reasons.append('Seniority is not explicit enough to classify confidently.')
    if junior and (senior or (minimum is not None and minimum>=3)):
        warnings.append('Junior label conflicts with the title or stated experience requirement.')
    if alternatives: warnings.append('Alternative qualification paths found; read the experience excerpts.')
    if not desc:
        warnings.append('Description unavailable. Skills and requirements have not been checked.')
    elif len(desc)<200:
        warnings.append('Only a short description was collected; verify the full posting.')
    if not evidence and job.get('reported_years_min') is not None:
        warnings.append(f"Source reports {job['reported_years_min']} years, but no supporting experience excerpt was collected.")
    if job['regions']==['Unknown']: warnings.append('Location or eligibility to work from Israel needs confirmation.')
    if all(r in profile.get('excluded_regions',[]) or r=='Outside Israel' for r in job['regions']):
        bucket='outside'; reasons.append('Location is outside your current search preferences. Listing retained.')
    if matched: reasons.append('Your profile includes: '+', '.join(matched)+'.')
    # Choose by title first, not incidental words in a long company description.
    target=title.lower()
    if re.search(r'firmware|embedded',target): cv='Ron_Salama_Firmware_Embedded.pdf'
    elif re.search(r'game|unity|technical art',target): cv='Ron_Salama_GameTech_TechnicalArt.pdf'
    elif re.search(r'\bai\b|llm|genai',target): cv='Ron_Salama_Software_AI.pdf'
    elif re.search(r'test|automation|validation|integration',target): cv='Ron_Salama_Hardware_Test_Integration.pdf'
    elif re.search(r'\bc\b|systems',target): cv='Ron_Salama_C_Systems.pdf'
    else: cv='Ron_Salama_Backend_FullStack.pdf'
    return {'bucket':bucket,'reasons':reasons,'warnings':warnings,'experience':evidence,
            'matched':matched,'learning':learning_mentions,'unconfirmed':unconfirmed,'cv':cv,
            'description_available':bool(desc)}

def normalize(raw, profile):
    title=clean(raw.get('title') or raw.get('role'))
    if not title: raise ValueError('Missing job title')
    url=canonical_url(raw.get('url'))
    source=clean(raw.get('source') or raw.get('src') or 'import')
    sid=str(raw.get('sid') or '')
    company=clean(raw.get('company')) or 'Undisclosed employer'
    location=clean(raw.get('city') or raw.get('location') or raw.get('loc'))
    # URLs and source IDs represent postings. Same-title openings stay distinct.
    identity=url or source+':'+(sid or hashlib.sha256((company+'|'+title+'|'+location).encode()).hexdigest())
    job={'id':hashlib.sha256(identity.encode()).hexdigest()[:24], 'title':title,'company':company,
         'location':location,'regions':regions_of(location),'url':url,'sources':[source],
         'source_ids':[source+':'+sid] if sid else [],'description':clean(raw.get('description') or raw.get('desc')),
         'level':clean(raw.get('level')),'reported_years_min':raw.get('years_min'),
         'reported_posted':clean(raw.get('posted_at') or raw.get('postedOn')),
         'active_signal':raw.get('active',True),'imported':bool(raw.get('imported'))}
    job['analysis']=analyze(job,profile)
    return job
