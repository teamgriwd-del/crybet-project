import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
import server


class MonitorTests(unittest.TestCase):
    def setUp(self):
        server.DEMO_MODE = False
        with server.lock:
            server.state.update(threshold_mv=45., normal_threshold_mv=100., delay_s=5.,
                                baseline_mv=650., last=None, quiet_since=None)
            server.state['history'].clear()

    def reading(self, t, level=820, carrier=True, tx=None, **extra):
        with patch('server.time.time', return_value=t):
            server.ingest(dict(envelope_mv=level, carrier_present=carrier, transmitter_on=tx, **extra))
            return server.snapshot()

    def test_four_conditions(self):
        self.assertEqual(self.reading(100)['status'], 'NORMAL')
        self.assertEqual(self.reading(101, 720)['status'], 'LOW_AUDIO')
        self.assertEqual(self.reading(102, 655)['status'], 'QUIET_PENDING')
        for t in range(103, 108):
            result = self.reading(t, 655)
        self.assertEqual(result['status'], 'CARRIER_NO_AUDIO')
        self.assertEqual(self.reading(108, 655, False, False)['status'], 'TRANSMITTER_OFF')
        self.assertEqual(self.reading(109)['status'], 'NORMAL')

    def test_offline_is_not_transmitter_off(self):
        self.assertEqual(server.snapshot()['status'], 'OFFLINE')
        self.reading(100, 655, False, False)
        with patch('server.time.time', return_value=104):
            self.assertEqual(server.snapshot()['status'], 'OFFLINE')
            self.assertIsNone(server.snapshot()['audio_rise_mv'])

    def test_unknown_carrier_and_signal_loss(self):
        self.assertEqual(self.reading(100, carrier=None)['status'], 'UNKNOWN')
        self.assertEqual(self.reading(101, carrier=False)['status'], 'NO_CARRIER')
        self.assertEqual(self.reading(102, carrier=False, tx=True)['status'], 'NO_CARRIER')

    def test_threshold_boundaries(self):
        self.assertEqual(self.reading(100, 695)['status'], 'LOW_AUDIO')
        self.assertEqual(self.reading(101, 750)['status'], 'NORMAL')
        self.assertEqual(self.reading(102, 694.9)['status'], 'QUIET_PENDING')

    def test_confirmation_resets_after_gap_and_carrier_change(self):
        self.reading(100, 655)
        self.assertEqual(self.reading(120, 655)['status'], 'QUIET_PENDING')
        self.reading(121, 655, False)
        self.assertEqual(self.reading(122, 655)['quiet_seconds'], 0)

    def test_settings_reset_timer_and_ordering(self):
        self.reading(100, 655)
        with self.assertRaises(ValueError):
            server.set_settings(dict(threshold_mv=100, normal_threshold_mv=45, delay_s=5, baseline_mv=650))
        server.set_settings(dict(threshold_mv=45, normal_threshold_mv=100, delay_s=8, baseline_mv=650))
        self.assertEqual(self.reading(101, 655)['quiet_seconds'], 0)

    def test_input_validation_and_conflicting_telemetry(self):
        for value in (-1, 3301, True, float('nan'), float('inf')):
            with self.subTest(value=value), self.assertRaises(ValueError):
                server.ingest(dict(envelope_mv=value))
        for field in ('carrier_present', 'transmitter_on'):
            for value in (0, 1, 'false', []):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    server.ingest(dict(envelope_mv=800, **{field: value}))
        with self.assertRaises(ValueError):
            server.ingest(dict(envelope_mv=800, carrier_present=True, transmitter_on=False))
        for value in (True, -1, 128, float('nan')):
            with self.assertRaises(ValueError):
                server.ingest(dict(envelope_mv=800, rssi=value))

    def test_untrusted_source_cannot_claim_simulation(self):
        self.assertEqual(self.reading(100, source='SIMULATION')['last']['source'], 'ESP32')


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.original_dir = server.DATA_DIR
        server.DATA_DIR = Path(cls.temp.name)
        cls.phone = '+263771234567'
        cls.password = 'Only-for-local-test-123'
        server.create_user(cls.phone, cls.password)
        cls.token = server.create_device_token()
        cls.http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        cls.thread = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown(); cls.http.server_close(); cls.thread.join()
        server.DATA_DIR = cls.original_dir
        cls.temp.cleanup()

    def setUp(self):
        server.DEMO_MODE = False
        server.sessions.clear(); server.login_attempts.clear()

    def request(self, method, path, data=None, cookie=None, device=None, browser=True, origin=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.http.server_port, timeout=5)
        headers = {'Content-Type': 'application/json'}
        if browser: headers['X-FM-Request'] = '1'
        if cookie: headers['Cookie'] = cookie
        if device: headers['Authorization'] = 'Bearer ' + device
        if origin: headers['Origin'] = origin
        try:
            conn.request(method, path, body=None if data is None else json.dumps(data), headers=headers)
            res = conn.getresponse(); body = res.read(); content = res.getheader('Content-Type')
            return res.status, json.loads(body) if content == 'application/json' else body.decode(), res.getheader('Set-Cookie')
        finally:
            conn.close()

    def login(self):
        code, body, cookie = self.request('POST', '/api/login', dict(phone=self.phone, password=self.password))
        self.assertEqual(code, 200)
        self.assertIn('HttpOnly', cookie); self.assertIn('SameSite=Strict', cookie)
        return cookie.split(';')[0]

    def test_login_required_and_logout(self):
        self.assertIn('Welcome back', self.request('GET', '/')[1])
        self.assertEqual(self.request('GET', '/api/status')[0], 401)
        self.assertEqual(self.request('POST', '/api/settings', {})[0], 401)
        cookie = self.login()
        self.assertIn('FM transmission', self.request('GET', '/', cookie=cookie)[1])
        self.assertTrue(self.request('GET', '/api/session', cookie=cookie)[1]['authenticated'])
        self.assertEqual(self.request('GET', '/api/status', cookie=cookie)[0], 200)
        self.assertEqual(self.request('POST', '/api/logout', {}, cookie=cookie)[0], 200)
        self.assertEqual(self.request('GET', '/api/status', cookie=cookie)[0], 401)

    def test_wrong_credentials_rate_limit(self):
        for _ in range(5):
            self.assertEqual(self.request('POST', '/api/login', dict(phone=self.phone, password='wrong'))[0], 401)
        self.assertEqual(self.request('POST', '/api/login', dict(phone=self.phone, password=self.password))[0], 429)

    def test_expired_session(self):
        cookie = self.login()
        key = cookie.split('=', 1)[1]
        server.sessions[key]['expires'] = 0
        self.assertEqual(self.request('GET', '/api/status', cookie=cookie)[0], 401)

    def test_csrf_guards(self):
        cookie = self.login()
        self.assertEqual(self.request('POST', '/api/settings', {}, cookie=cookie, browser=False)[0], 403)
        self.assertEqual(self.request('POST', '/api/settings', {}, cookie=cookie, origin='http://untrusted.example')[0], 403)

    def test_device_ingestion_requires_separate_token(self):
        cookie = self.login()
        packet = dict(envelope_mv=820, carrier_present=True)
        self.assertEqual(self.request('POST', '/api/readings', packet, cookie=cookie)[0], 401)
        self.assertEqual(self.request('POST', '/api/readings', packet, device='bad')[0], 401)
        self.assertEqual(self.request('POST', '/api/readings', packet, device=self.token, browser=False)[0], 200)
        self.assertEqual(self.request('GET', '/api/status', cookie=cookie)[1]['status'], 'NORMAL')
        server.DEMO_MODE = True
        self.assertEqual(self.request('POST', '/api/readings', packet, device=self.token)[0], 409)
        server.DEMO_MODE = False

    def test_settings_and_bad_requests(self):
        cookie = self.login()
        settings = dict(baseline_mv=650, threshold_mv=45, normal_threshold_mv=100, delay_s=5)
        self.assertEqual(self.request('POST', '/api/settings', settings, cookie=cookie)[0], 200)
        self.assertEqual(self.request('POST', '/api/settings', {**settings, 'normal_threshold_mv': 20}, cookie=cookie)[0], 400)
        self.assertEqual(self.request('POST', '/api/readings', [], device=self.token)[0], 400)
        self.assertEqual(self.request('POST', '/api/readings', {'envelope_mv': 9000}, device=self.token)[0], 400)
        self.assertEqual(self.request('GET', '/.fm-monitor/accounts.sqlite3')[0], 404)
        self.assertEqual(self.request('GET', '/server.py')[0], 404)

    def test_password_hash_and_phone_normalization(self):
        with server.db() as conn:
            row = conn.execute('SELECT salt,digest FROM users WHERE phone=?', (self.phone,)).fetchone()
        self.assertNotEqual(row[1], self.password)
        self.assertEqual(len(row[0]), 32)
        self.assertEqual(server.authenticate('+263 77 123 4567', self.password), self.phone)
        self.assertIsNone(server.authenticate('+263771234568', self.password))
        with self.assertRaises(ValueError): server.create_user('0771234567', self.password)
        with self.assertRaises(ValueError): server.create_user(self.phone, 'short')


if __name__ == '__main__':
    unittest.main()
