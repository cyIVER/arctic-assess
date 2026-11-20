"""UNIT ONLY: public synthetic authority, never usable approval/runtime proof."""
import hashlib,json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(HERE),str(HERE.parent/'integration-repair-v4/canary'),str(HERE.parent/'integration-repair-v4'),str(HERE.parent/'integration-repair-v4/guardian')]
import prepare,launch,guest,driver,admission_v3,test_integration as t
from unit_support_v3 import unit_permissions
class LaunchReached(RuntimeError):pass
class Tests(unittest.TestCase):
    def test_stage_actual_pins_and_extra_pycache_denial(self):
        root=HERE/'staged';pin=prepare.sha((root/'stage-manifest.json').read_bytes())
        self.assertEqual(len(prepare.check_stage(root,pin)),690)
        extra=root/'unreviewed.pyc'
        try:
            extra.write_bytes(b'UNIT_ONLY')
            with self.assertRaisesRegex(ValueError,'extras'):prepare.check_stage(root,pin)
        finally:extra.unlink()
    def test_actual_driver_validation_to_first_mutation_boundary(self):
        scratch=HERE/'unit-scratch';scratch.mkdir(exist_ok=True,mode=0o700)
        original_stage=t.tuples.stage
        def resolved(original,*a,**kw):return original_stage(Path(original).resolve(),*a,**kw)
        real_trusted=guest.trusted_directory
        exempt={(p.stat().st_dev,p.stat().st_ino) for p in (HERE.parent,HERE.parent.parent)}
        def trusted(fd):
            s=os.fstat(fd)
            if (s.st_dev,s.st_ino) in exempt:return
            return real_trusted(fd)
        with tempfile.TemporaryDirectory(dir=scratch) as d,unit_permissions(),patch.object(t.tuples,'stage',side_effect=resolved),patch('stage_reviewed.stage',side_effect=resolved),patch.object(guest,'trusted_directory',side_effect=trusted):
            c,context,a=t.tuples.fixture(d);t.bind(c,context,a,t.merged(c))
            result={'alive':True,'provider_state':'RUNNING','vm':c['vm'],'stop_at':c['external_stop'],'controller_id':c['controller_id'],'guard_created':c['guard_created'],'default_docker_quiescent':True,'preflight_checkpoint_sha256':c['preflight']['sha256']}
            class Runner:
                def run(self,*a,**kw):return prepare.canonical(result)
            with patch.object(admission_v3,'PARENT_CONTEXT',str(context)),patch.object(driver.os,'getuid',return_value=0),patch.object(driver,'verify_owner',side_effect=LaunchReached('UNIT_ONLY actual launch seam reached')) as seam:
                # guest owner comparison is an explicit test-only metadata seam.
                c['owner']['socket_uid']=0;a['config_sha256']=admission_v3.canonical(c);context.write_bytes(prepare.canonical(a))
                with self.assertRaises(LaunchReached):driver.run(c,runner=Runner(),clock=lambda:1000)
                self.assertEqual(seam.call_count,1)
                for key,value in [('created',879),('budget_ceiling_usd',.25),('reserve_usd',.25),('external_stop',1601)]:
                    bad=c|{key:value}
                    with self.subTest(key=key),self.assertRaises(guest.Blocked):driver.run(bad,runner=Runner(),clock=lambda:1000)
                self.assertEqual(seam.call_count,1)
                context.unlink()
                with self.assertRaises(guest.Blocked):driver.run(c,runner=Runner(),clock=lambda:1000)
                self.assertEqual(seam.call_count,1)
    def test_bootstrap_is_isolated_no_environment_or_key(self):
        argv=launch.bootstrap_argv(HERE/'staged','a'*64,'/run/artex-parent/canary.json')
        self.assertEqual(argv[:4],['/usr/bin/python3','-I','-B','-c'])
        self.assertNotIn('PYTHONPATH',argv[-1]);self.assertNotIn('transport.key',argv[-1])
if __name__=='__main__':unittest.main(verbosity=2)
