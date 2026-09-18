import copy
import json
import tempfile
import unittest
from pathlib import Path
from radar.engine import normalize, experience_evidence, canonical_url, regions_of
from radar.storage import merge, migrate, atomic_json, read_json
from radar.app import render_html

PROFILE={'skills':['Python','C#','TypeScript','LLM APIs'],'learning':['RAG','MCP'],'experience_years':1,'excluded_regions':['South','Jerusalem'],'stale_after_days':14,'sources':[]}

def raw(**kwargs):
    r={'source':'test','sid':'1','title':'Junior Software Engineer','company':'Example','city':'Haifa, Israel','url':'https://example.com/jobs/1','desc':'0-3 years of software development experience. Python and C#.'}
    r.update(kwargs); return r

def empty(): return {'version':2,'jobs':[],'sources':{},'runs':[]}

class EvidenceTests(unittest.TestCase):
    def test_intel_post_silicon_is_not_a_rejection(self):
        j=normalize(raw(title='AI Tools and Cloud Software Developer',level='entry',desc='Develop AI-powered automation and cloud solutions for post-silicon engineering teams. Python, C#, TypeScript, LLM APIs, RAG and MCP.'),PROFILE)
        self.assertEqual(j['analysis']['bucket'],'consider')
        self.assertIn('MCP',j['analysis']['learning'])
    def test_range_lower_bound(self):
        self.assertEqual(experience_evidence('0–3 years of programming experience.')[0]['min'],0)
        self.assertEqual(experience_evidence('ניסיון של 1-2 שנים בתוכנה')[0]['max'],2)
    def test_optional_years_not_required(self):
        j=normalize(raw(desc='0-2 years of professional experience.\nPreferred qualifications\n5 years of cloud experience preferred.'),PROFILE)
        self.assertEqual(j['analysis']['bucket'],'consider')
        self.assertEqual(j['analysis']['experience'][1]['kind'],'preferred')
    def test_low_optional_requirement_does_not_hide_seniority(self):
        j=normalize(raw(desc='5 years of software experience required.\n1 year of Python experience required.'),PROFILE)
        self.assertEqual(j['analysis']['bucket'],'stretch')
        self.assertTrue(j['analysis']['warnings'])
    def test_alternative_qualifications_need_review(self):
        j=normalize(raw(title='Software Engineer',desc='BSc and 3 years of experience or MSc and 1 year of experience.'),PROFILE)
        self.assertEqual(j['analysis']['bucket'],'review')
    def test_company_history_not_experience(self):
        self.assertEqual(experience_evidence('Our company has 20 years of experience in security.'),[])
    def test_unknown_location_retained(self):
        self.assertEqual(normalize(raw(city='Israel'),PROFILE)['regions'],['Unknown'])
    def test_foreign_city_not_center(self):
        self.assertEqual(regions_of('Gurugram, India'),['Outside Israel'])
        self.assertEqual(regions_of('An unfamiliar city'),['Unknown'])
    def test_location_preferences_explain_not_delete(self):
        j=normalize(raw(city='Jerusalem, Israel'),PROFILE)
        self.assertEqual(j['analysis']['bucket'],'outside')
    def test_no_description_does_not_fabricate_skills(self):
        a=normalize(raw(desc='',company='NVIDIA'),PROFILE)['analysis']
        self.assertFalse(a['description_available']); self.assertEqual(a['matched'],[])
        self.assertNotIn('fit',a)
    def test_non_software_domain_words_not_blacklisted(self):
        self.assertEqual(normalize(raw(desc='Develop frontend layout tools for ASIC and post-silicon teams.'),PROFILE)['analysis']['bucket'],'consider')
    def test_team_leader_not_junior_despite_source_label(self):
        self.assertEqual(normalize(raw(title='Full Stack Team Leader',level='junior'),PROFILE)['analysis']['bucket'],'stretch')
    def test_safe_urls_and_query_identity(self):
        self.assertEqual(canonical_url('javascript:alert(1)'), '')
        self.assertEqual(canonical_url('https://x.com/job?id=1&utm_source=hi'),'https://x.com/job?id=1')
        self.assertNotEqual(canonical_url('https://x.com/job?id=1'),canonical_url('https://x.com/job?id=2'))

class StoreTests(unittest.TestCase):
    def test_distinct_same_title_requisitions_survive(self):
        data,ids=merge(empty(),{'test':{'status':'ok','jobs':[raw(),raw(sid='2',url='https://example.com/jobs/2')]}},PROFILE)
        self.assertEqual(len(data['jobs']),2)
    def test_exact_url_merges_sources_but_not_different_jobs(self):
        data,ids=merge(empty(),{'a':{'status':'ok','jobs':[raw()]},'b':{'status':'ok','jobs':[raw(source='b',url='https://example.com/jobs/1?utm_source=b')]}},PROFILE)
        self.assertEqual(len(data['jobs']),1); self.assertEqual(len(data['jobs'][0]['sources']),2)
    def test_source_failure_does_not_close_or_delete(self):
        data,_=merge(empty(),{'test':{'status':'ok','jobs':[raw()]}},PROFILE,'2026-09-01T12:00:00+00:00')
        data,_=merge(data,{'test':{'status':'error','jobs':[]}},PROFILE,'2026-09-02T12:00:00+00:00')
        self.assertEqual(data['jobs'][0]['availability'],'observed')
    def test_staleness_is_not_closure(self):
        data,_=merge(empty(),{'test':{'status':'ok','jobs':[raw()]}},PROFILE,'2026-09-01T12:00:00+00:00')
        data,_=merge(data,{'test':{'status':'error','jobs':[]}},PROFILE,'2026-09-18T12:00:00+00:00')
        self.assertEqual(data['jobs'][0]['availability'],'stale')
    def test_repeat_scan_preserves_first_seen_and_full_description(self):
        data,_=merge(empty(),{'test':{'status':'ok','jobs':[raw()]}},PROFILE,'2026-09-01T12:00:00+00:00')
        data,fresh=merge(data,{'test':{'status':'partial','jobs':[raw(desc='')]}},PROFILE,'2026-09-02T12:00:00+00:00')
        self.assertEqual(fresh,[]); self.assertEqual(data['jobs'][0]['first_seen'],'2026-09-01T12:00:00+00:00'); self.assertIn('Python',data['jobs'][0]['description'])
    def test_migration_is_unverified(self):
        d=migrate(empty(),[{'role':'Junior Developer','company':'Example','loc':'Israel','url':'https://x.com/job','date':'2026-09-01'}],PROFILE)
        self.assertIsNone(d['jobs'][0]['last_seen']); self.assertEqual(d['jobs'][0]['availability'],'unverified')
    def test_atomic_store_and_corruption_visibility(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'state.json'; atomic_json(p,{'x':'שלום'}); self.assertEqual(read_json(p,{}),{'x':'שלום'})
            p.write_text('broken'); self.assertRaises(json.JSONDecodeError,read_json,p,{})
    def test_untrusted_text_cannot_close_embedded_script(self):
        d=empty(); d['jobs']=[normalize(raw(title='Junior </script><script>alert(1)</script> Developer'),PROFILE)]
        # Test the renderer with raw untrusted data too, independent of cleaning.
        d['jobs'][0]['description']='</script><img src=x onerror=alert(1)>'
        h=render_html(d,PROFILE)
        self.assertNotIn('</script><img',h); self.assertIn('\\u003c/script',h)

if __name__=='__main__': unittest.main()
