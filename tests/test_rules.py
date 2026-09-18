import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from radar.engine import normalize
from radar.policy import company_matches, retain, prepare, apply_scan, recent_basis
from radar.alerts import eligible, deliver
from cloud_run import due
P={'experience_years':1,'skills':['Python'],'learning':[],'excluded_regions':['South','Jerusalem'],'giants':['intel','meta'],'referral_companies':['pwc next'],'relevant_only':True,'timezone':'Asia/Jerusalem'}
def job(**kw):
 d={'title':'Junior Software Engineer','company':'Intel','city':'Haifa','url':'https://example.com/1','desc':'Python software development. '+('Build tools. '*20),'level':'junior'};d.update(kw)
 j=normalize(d,P);j.update(first_seen='2026-09-19T12:00:00+00:00',last_seen='2026-09-19T14:00:00+00:00',availability='observed');return j
class Rules(unittest.TestCase):
 def test_compatibility_adapter_constructs_jobs(self):
  from legacy_sources import job as legacy_job
  self.assertEqual(legacy_job('test','1','Software Engineer',city='Haifa')['region'],'North')
 def test_referral_subsidiary(self):
  self.assertTrue(company_matches('PwC Next Israel',P['referral_companies']))
  self.assertFalse(company_matches('PwC',P['referral_companies']))
  self.assertFalse(company_matches('Metaverse Ltd',['meta']))
 def test_remove_noise(self):
  for j in [job(title='Accountant'),job(title='Senior Software Engineer'),job(city='Jerusalem'),job(desc='5 years of software development experience.')]: self.assertFalse(retain(j))
  self.assertTrue(retain(job(desc='3 years of software development experience.')))
  self.assertTrue(retain(job(title='Software Engineer',desc='Software for post-silicon engineering teams.')))
 def test_recent_labels(self):
  now=datetime(2026,9,19,14,tzinfo=timezone.utc)
  j=job();self.assertIn('unverified',recent_basis(j,now,P))
  j['reported_posted']='2026-09-01';self.assertIsNone(recent_basis(j,now,P))
  j['reported_posted']='September 1, 2026';self.assertIsNone(recent_basis(j,now,P))
  j['reported_posted']='2026-09-19T10:00:00Z';self.assertEqual(recent_basis(j,now,P),'Posted in the last 24 hours')
 def test_daily_and_giants(self):
  j=job(company='Startup');d={'jobs':[j],'updated_at':'2026-09-19T14:00:00+00:00','discovered':{}}
  apply_scan(d,P,[j['id']],'giants',set());self.assertEqual(d['jobs'],[])
  d['jobs']=[j];apply_scan(d,P,[j['id']],'daily',set());self.assertEqual(len(d['jobs']),1);self.assertIn('unverified',d['jobs'][0]['daily_basis'])
 def test_old_first_discovery_stays_old(self):
  j=job(company='Startup');d={'jobs':[j],'updated_at':'2026-09-19T14:00:00+00:00','discovered':{j['id']:'2026-09-01T12:00:00+00:00'}}
  apply_scan(d,P,[j['id']],'daily',set());self.assertEqual(d['jobs'],[])
 def test_summer_winter_schedule(self):
  self.assertEqual(due(datetime(2026,9,19,14,tzinfo=timezone.utc),{}),'daily')
  self.assertEqual(due(datetime(2026,12,19,15,tzinfo=timezone.utc),{}),'daily')
  self.assertEqual(due(datetime(2026,12,19,14,tzinfo=timezone.utc),{}),'giants')
  self.assertIsNone(due(datetime(2026,9,19,15,tzinfo=timezone.utc),{'schedule':{'daily_date':'2026-09-19'}}))
 def test_alert_only_giants_and_no_duplicates(self):
  a=job();b=job(company='Startup',url='https://example.com/2');d={'jobs':[a,b],'updated_at':'2026-09-19T14:00:00+00:00'};prepare(d,P)
  self.assertTrue(eligible(a));self.assertFalse(eligible(b))
  with patch('radar.alerts.atomic_json'),patch('radar.alerts.send',return_value=True) as send:
   deliver(d,P,[a['id'],b['id']]);deliver(d,P,[a['id']]);self.assertEqual(send.call_count,1)
 def test_failed_delivery_retries(self):
  j=job();d={'jobs':[j],'updated_at':'2026-09-19T14:00:00+00:00'};prepare(d,P)
  with patch('radar.alerts.atomic_json'),patch('radar.alerts.send',return_value=False):deliver(d,P,[j['id']])
  self.assertEqual(d['alerts']['pending'],[j['id']])
  with patch('radar.alerts.atomic_json'),patch('radar.alerts.send',return_value=True):deliver(d,P,[])
  self.assertEqual(d['alerts']['pending'],[])
