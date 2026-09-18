import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch
from radar.collectors import collect_one, greenhouse

class SourceTests(unittest.TestCase):
    def test_worker_timeout_retains_checkpoint(self):
        def timed_out(args,**kwargs):
            Path(args[-1]).write_text(json.dumps({'jobs':[{'title':'Found before timeout'}]}),encoding='utf-8')
            raise subprocess.TimeoutExpired(args,1)
        with patch('radar.collectors.subprocess.run',side_effect=timed_out):
            result=collect_one('workday:intel',1)
        self.assertEqual(result['status'],'timeout')
        self.assertEqual(len(result['jobs']),1)
    def test_greenhouse_malformed_response_is_not_empty_success(self):
        class Response:
            def raise_for_status(self): pass
            def json(self): return {'message':'Unexpected response'}
        class Session:
            def get(self,*args,**kwargs): return Response()
        with patch('radar.collectors.session',return_value=Session()):
            self.assertRaises(ValueError,greenhouse,'example')

if __name__=='__main__': unittest.main()
