import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import test_integration as t
class BeforeFix(unittest.TestCase):
 def test_actual_mutual_rejection_after_both_own_positive_controls(self):
  with tempfile.TemporaryDirectory() as d:
   c,context,a=t.tuples.fixture(d)
   with patch.object(t.admission_v3,'PARENT_CONTEXT',str(context)):
    self.assertIs(t.guest.validate(c,1000),c)
    raw=Path(c['preflight']['path']).read_bytes()
    with self.assertRaisesRegex(t.guard.Blocked,'preflight stale/scope'):t.inventory(c,raw)
    ready={'status':'READY','deadline':c['deadline'],'vm':c['vm'],'created':c['created'],'external_stop':c['external_stop'],'default_inventory':{'containers':[],'images':[],'volumes':[]}}
    raw=t.bind(c,context,a,ready)
    result,calls,reads=t.inventory(c,raw)
    self.assertTrue(result['default_docker_quiescent']);self.assertEqual(len([x for x in calls if x[0]=='command']),9)
    with self.assertRaisesRegex(t.guest.Blocked,'parent preflight checkpoint'):t.guest.validate(c,1000)
 def test_actual_final_client_accepts18_virtual_seconds(self):
  result,elapsed,timeouts=t.ClientDeadline().exchange(9,0,9)
  self.assertTrue(result['alive']);self.assertEqual(elapsed,18)
