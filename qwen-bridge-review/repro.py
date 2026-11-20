"""Offline reviewer vectors. No sockets, service, credentials or cloud."""
import json, sys, time, threading, unittest
from unittest.mock import patch
sys.path.insert(0, '/home/iveri/work/vindler-e2.SftLYa2R/continuation/coordination-20261119/qwen-standard-bridge')
import bridge
TASK='review-task-key-01234567890123456789'
VENDOR='review-vendor-key-01234567890123456789'
def request(**extra):
    return json.dumps(dict(model=bridge.MODEL,messages=[{'role':'user','content':'fixture'}],stream=False,**extra)).encode()
class Offline(unittest.TestCase):
    def setUp(self):
        p=patch('socket.socket',side_effect=AssertionError('socket forbidden'))
        p.start(); self.addCleanup(p.stop)
        self.calls=[]
        def fake(body,key,deadline):
            self.calls.append((json.loads(body),key,deadline))
            return 200,b'{"choices":[{"message":{"content":"fixture"},"finish_reason":"stop"}]}'
        self.b=bridge.Bridge(TASK,VENDOR,time.time()+300,transport=fake)
    def send(self,p): return self.b.request('POST',bridge.PATH,'Bearer '+TASK,p)
    def test_normal_norma_nonstreaming_shape(self):
        self.send(request(max_tokens=4096,tools=[{'type':'function','function':{'name':'fetch','description':'fixture','parameters':{'type':'object','properties':{'url':{'type':'string'}}}}}],thinking={'type':'disabled'},temperature=0.2))
        sent=self.calls[0][0]
        self.assertEqual(sent['tools'][0]['function']['parameters']['properties']['url']['type'],'string')
        self.assertIs(sent['stream'],False)
    def test_tool_messages_and_results_with_url_data(self):
        p=json.loads(request(max_completion_tokens=4096))
        p['messages'] += [{'role':'assistant','tool_calls':[{'id':'x','type':'function','function':{'name':'fetch','arguments':'{"url":"http://dvwa.invalid"}'}}]},{'role':'tool','tool_call_id':'x','content':'{"url":"http://dvwa.invalid"}'}]
        self.send(json.dumps(p).encode())
        self.assertEqual(self.calls[0][0]['messages'],p['messages'])
    def test_top_level_route_selectors_rejected(self):
        for field in ('url','base_url','endpoint','proxy','headers','authorization','api_key','host','port','fallback','retries','callback_url'):
            with self.subTest(field=field):
                with self.assertRaises(bridge.Denied) as err: self.send(request(**{field:'evil'}))
                self.assertEqual(err.exception.code,'transport_selector')
        self.assertEqual(len(self.calls),0)
    def test_nonstandard_metadata_url_is_rejected(self):
        with self.assertRaises(bridge.Denied) as err:
            self.send(request(metadata={'url':'http://dvwa.invalid'}))
        self.assertEqual(err.exception.code,'transport_selector')
    def test_blocking_transport_deadline_terminal_fence(self):
        gate=threading.Event()
        def stalled(body,key,deadline): gate.wait(2); return 200,b'{}'
        self.b.transport=stalled
        start=time.monotonic()
        try:
            with self.assertRaises(bridge.Denied) as err:
                self.b.request('POST',bridge.PATH,'Bearer '+TASK,request(max_tokens=4096),deadline=time.monotonic()+.03)
            self.assertEqual(err.exception.code,'deadline')
            self.assertTrue(self.b.terminal)
            self.assertLess(time.monotonic()-start,.5)
            with self.assertRaises(bridge.Denied) as again: self.send(request(max_tokens=4096))
            self.assertEqual(again.exception.code,'expired')
        finally: gate.set()
if __name__=='__main__': unittest.main(verbosity=2)
