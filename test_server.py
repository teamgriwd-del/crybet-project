import json, threading, unittest, urllib.request, urllib.error
from unittest.mock import patch
import server

class MonitorTests(unittest.TestCase):
    def setUp(self):
        with server.lock:
            server.state.update(threshold_mv=45.,delay_s=5.,baseline_mv=650.,last=None,quiet_since=None)
            server.state['history'].clear()
    def test_quiet_delay_audio_recovery_and_offline(self):
        with patch('server.time.time',return_value=100): server.ingest({'envelope_mv':655})
        with patch('server.time.time',return_value=102): self.assertEqual(server.snapshot()['status'],'QUIET')
        for t in (102,104,106):
            with patch('server.time.time',return_value=t): server.ingest({'envelope_mv':655})
        with patch('server.time.time',return_value=106): self.assertEqual(server.snapshot()['status'],'SILENCE')
        with patch('server.time.time',return_value=107):
            server.ingest({'envelope_mv':820}); self.assertEqual(server.snapshot()['status'],'AUDIO')
        with patch('server.time.time',return_value=111): self.assertEqual(server.snapshot()['status'],'OFFLINE')
    def test_gap_resets_timer(self):
        with patch('server.time.time',return_value=100): server.ingest({'envelope_mv':650})
        with patch('server.time.time',return_value=120):
            server.ingest({'envelope_mv':650}); self.assertEqual(server.snapshot()['status'],'QUIET')
    def test_invalid_voltage(self):
        for value in (-1,3301,float('nan'),float('inf')):
            with self.assertRaises(ValueError): server.ingest({'envelope_mv':value})
    def test_http_routes(self):
        http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
        base='http://127.0.0.1:'+str(http.server_port)
        try:
            self.assertIn(b'FM transmission',urllib.request.urlopen(base+'/').read())
            req=urllib.request.Request(base+'/api/readings',data=b'{"envelope_mv":800}',headers={'Content-Type':'application/json'})
            self.assertEqual(urllib.request.urlopen(req).status,200)
            self.assertEqual(json.load(urllib.request.urlopen(base+'/api/status'))['status'],'AUDIO')
            req=urllib.request.Request(base+'/api/settings',data=b'{"baseline_mv":650,"threshold_mv":45,"delay_s":5}')
            self.assertEqual(urllib.request.urlopen(req).status,200)
            req=urllib.request.Request(base+'/api/readings',data=b'{"envelope_mv":9999}')
            with self.assertRaises(urllib.error.HTTPError) as caught: urllib.request.urlopen(req)
            self.assertEqual(caught.exception.code,400)
        finally: http.shutdown(); http.server_close(); thread.join()
if __name__=='__main__': unittest.main()
