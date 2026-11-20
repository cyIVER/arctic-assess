import json, unittest
import test_broker as fixtures
from hostbroker.broker import Refused

class VolumeTests(unittest.TestCase):
    setUp=fixtures.BrokerTests.setUp
    tearDown=fixtures.BrokerTests.tearDown
    req=fixtures.BrokerTests.req
    def test_known_inherited_volume_is_readonly_shadowed_and_owned_cleanup_removes_volumes(self):
        self.b.execute(self.req())
        create=next(c[0] for c in self.fake.calls if c[0][0]=='create')
        self.assertIn('/app/data:ro,noexec,nosuid,nodev,size=64k,mode=0555',create)
        cleanup=next(c[0] for c in self.fake.calls if c[0][0]=='rm')
        self.assertIn('--volumes',cleanup)

    def test_unexpected_image_volume_denied_before_container_or_payload(self):
        original=self.fake.run
        def run(args,*a,**kw):
            if args[:2]==['image','inspect']:return b'{"/app/data":{},"/unexpected":{}}'
            return original(args,*a,**kw)
        self.fake.run=run
        with self.assertRaises(Refused):self.b.execute(self.req())
        self.assertEqual(self.fake.calls,[])

    def test_anonymous_or_wrong_mount_refused_before_start(self):
        original=self.fake.run
        def run(args,*a,**kw):
            if args[0]=='inspect':return b'{"mounts":[{"Type":"volume","Destination":"/app/data","RW":true}],"tmpfs":{}}'
            return original(args,*a,**kw)
        self.fake.run=run
        with self.assertRaises(Refused):self.b.execute(self.req())
        self.assertFalse(any(c[0][0]=='start' for c in self.fake.calls))
        self.assertFalse(self.fake.live)
