import threading, unittest
import test_broker as fixtures
from test_broker import BINDING
from hostbroker.broker import Broker, Scope, Refused
from hostbroker.gateway import Budget

class RegistrationTests(unittest.TestCase):
    setUp=fixtures.BrokerTests.setUp
    tearDown=fixtures.BrokerTests.tearDown
    req=fixtures.BrokerTests.req

    def test_current_membership_is_checked_before_each_effect(self):
        # Real old execute entrypoint, admitted positive then revoked membership.
        active=[True]; checks=[]
        def verify(binding):checks.append(binding);return active[0]
        self.scope.membership_verifier=verify
        self.assertEqual(self.b.execute(self.req())['version'],1)
        active[0]=False; count=len(self.fake.calls)
        with self.assertRaises(Refused):self.b.execute(self.req())
        self.assertEqual(len(self.fake.calls),count)
        self.assertGreaterEqual(len(checks),2)

    def test_dynamic_resolve_register_fresh_check_and_no_quota_reset(self):
        checks=[]; active=[True]; resolutions=[]
        def verify(binding):checks.append(binding);return active[0]
        def resolve(binding):resolutions.append(binding);return self.scope,verify
        b=Broker(self.policy,[],driver=self.fake,reviewed=True,scope_resolver=resolve)
        for _ in range(32):b.execute(self.req())
        self.assertEqual(len(resolutions),1)
        self.assertGreaterEqual(len(checks),33)
        work=self.root/'second';work.mkdir(mode=0o700)
        binding=BINDING.copy();binding['IntentID']=4
        second=Scope(binding,str(work),str(self.sockdir),Budget())
        b.register_scope(second,verify)
        self.assertIs(second.quota,self.scope.quota)
        count=len(self.fake.calls)
        req=self.req();req['Binding']=binding
        with self.assertRaises(Refused):b.execute(req)
        self.assertEqual(len(self.fake.calls),count)

    def test_missing_member_registration_has_no_reservation_or_effect(self):
        b=Broker(self.policy,[],driver=self.fake,reviewed=True)
        with self.assertRaises(Refused):b.register_scope(self.scope,lambda _:False)
        self.assertEqual(b.scopes,{})
        self.assertEqual(self.fake.calls,[])
        b.register_scope(self.scope,lambda _:True)
        self.assertEqual(b.execute(self.req())['version'],1)

    def test_tombstone_cancels_inflight_and_rejects_fresh_scope_object(self):
        b=Broker(self.policy,[],driver=self.fake,reviewed=True)
        b.register_scope(self.scope,lambda _:True)
        entered=threading.Event(); resume=threading.Event(); original=self.fake.run
        def run(args,*a,**kw):
            if args[0]=='start':
                entered.set();resume.wait(2)
                if kw['cancel'].is_set():raise Refused('cancelled')
            return original(args,*a,**kw)
        self.fake.run=run; errors=[]
        def execute():
            try:b.execute(self.req())
            except Refused:errors.append(True)
        t=threading.Thread(target=execute);t.start()
        try:
            self.assertTrue(entered.wait(1));b.revoke_scope(BINDING)
            self.assertTrue(self.budget.stopped.is_set())
            replacement=Scope(BINDING.copy(),str(self.work),str(self.sockdir),Budget())
            with self.assertRaises(Refused):b.register_scope(replacement,lambda _:True)
        finally:resume.set();t.join(3)
        self.assertFalse(t.is_alive());self.assertEqual(errors,[True]);self.assertFalse(self.fake.live)
        self.assertIs(b.scopes[b._key(BINDING)],self.scope)
        with self.assertRaises(Refused):b.execute(self.req())

    def test_callback_exception_denies_without_effect_or_registration(self):
        def broken(binding):raise RuntimeError('owned-public-failure')
        b=Broker(self.policy,[],driver=self.fake,reviewed=True,scope_resolver=broken)
        with self.assertRaises(Refused):b.execute(self.req())
        self.assertFalse(b.scopes);self.assertFalse(self.fake.calls)
        with self.assertRaises(Refused):b.register_scope(self.scope,broken)
        self.assertFalse(b.scopes);self.assertFalse(self.fake.calls)

    def test_revoke_while_registration_callback_is_waiting_is_permanent(self):
        entered=threading.Event();resume=threading.Event();revoking=threading.Event()
        def verify(binding):entered.set();resume.wait(2);return True
        b=Broker(self.policy,[],driver=self.fake,reviewed=True);errors=[]
        def register():
            try:b.register_scope(self.scope,verify)
            except Refused:errors.append(True)
        def revoke():revoking.set();b.revoke_scope(BINDING)
        registration=threading.Thread(target=register);registration.start()
        self.assertTrue(entered.wait(1));revocation=threading.Thread(target=revoke);revocation.start()
        self.assertTrue(revoking.wait(1));resume.set();registration.join(3);revocation.join(3)
        self.assertFalse(registration.is_alive());self.assertFalse(revocation.is_alive())
        self.assertTrue(self.budget.stopped.is_set())
        with self.assertRaises(Refused):b.execute(self.req())
        fresh=Scope(BINDING.copy(),str(self.work),str(self.sockdir),Budget())
        with self.assertRaises(Refused):b.register_scope(fresh,lambda _:True)
        self.assertFalse(self.fake.calls)

    def test_revoke_keeps_quarantine_lock_and_workspace_reservation(self):
        b=Broker(self.policy,[],driver=self.fake,reviewed=True)
        b.register_scope(self.scope,lambda _:True)
        original=self.fake.run
        def run(args,*a,**kw):
            if args[0]=='start':b.revoke_scope(BINDING);raise Refused('cancelled')
            if args[0]=='ps':return b'uncertain-live'
            return original(args,*a,**kw)
        self.fake.run=run
        with self.assertRaises(Refused):b.execute(self.req())
        self.assertTrue(self.scope.quarantined);self.assertTrue(self.scope.lock.locked())
        self.assertIn(b._key(BINDING),b._pins)
        binding=BINDING.copy();binding['IntentID']=4
        fresh=Scope(binding,str(self.work),str(self.sockdir),Budget())
        with self.assertRaises(Refused):b.register_scope(fresh,lambda _:True)
        cleanup=next(c for c in self.fake.calls if c[0][0]=='rm')
        self.assertFalse(cleanup[2]['cancel'].is_set());self.assertEqual(cleanup[2]['timeout'],3)

    def test_revoke_unknown_binding_fences_future_registration(self):
        b=Broker(self.policy,[],driver=self.fake,reviewed=True)
        b.revoke_scope(BINDING)
        with self.assertRaises(Refused):b.register_scope(self.scope,lambda _:True)
