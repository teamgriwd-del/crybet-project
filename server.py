#!/usr/bin/env python3
"""Local FM monitor. Python standard library only; trusted private LAN use."""
import argparse
import collections
from contextlib import contextmanager
import getpass
import hashlib
import hmac
import json
import math
import re
import secrets
import sqlite3
import threading
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / '.fm-monitor'
SESSION_SECONDS = 8 * 60 * 60
PBKDF_ROUNDS = 600_000
lock = threading.Lock()
auth_lock = threading.Lock()
sessions = {}
login_attempts = collections.defaultdict(collections.deque)
DEMO_MODE = False
state = {'threshold_mv': 45.0, 'normal_threshold_mv': 100.0, 'delay_s': 5.0,
         'baseline_mv': 0.0, 'last': None, 'quiet_since': None,
         'history': collections.deque(maxlen=300)}


@contextmanager
def db():
    DATA_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    conn = sqlite3.connect(DATA_DIR / 'accounts.sqlite3')
    conn.execute('CREATE TABLE IF NOT EXISTS users (phone TEXT PRIMARY KEY, salt TEXT, digest TEXT)')
    conn.execute('CREATE TABLE IF NOT EXISTS device (id INTEGER PRIMARY KEY, digest TEXT)')
    conn.commit()
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def normalize_phone(value):
    if not isinstance(value, str):
        raise ValueError('Enter a phone number with country code, e.g. +263…')
    phone = re.sub(r'[\s()\-]', '', value)
    if not re.fullmatch(r'\+[1-9][0-9]{7,14}', phone):
        raise ValueError('Use + followed by country code and phone number (8–15 digits).')
    return phone


def password_digest(password, salt):
    return hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), PBKDF_ROUNDS).hex()


def create_user(phone, password):
    phone = normalize_phone(phone)
    if not isinstance(password, str) or not 12 <= len(password) <= 256:
        raise ValueError('Use a password of 12–256 characters.')
    salt = secrets.token_hex(16)
    with db() as conn:
        # Local CLI also serves as the documented password-reset mechanism.
        conn.execute('INSERT OR REPLACE INTO users VALUES (?,?,?)',
                     (phone, salt, password_digest(password, salt)))


def authenticate(phone, password):
    try:
        phone = normalize_phone(phone)
    except ValueError:
        phone = ''
    with db() as conn:
        row = conn.execute('SELECT salt,digest FROM users WHERE phone=?', (phone,)).fetchone()
    salt, expected = row if row else ('0' * 32, '0' * 64)
    actual = password_digest(password, salt)
    return phone if hmac.compare_digest(actual, expected) and row else None


def create_device_token():
    token = secrets.token_urlsafe(32)
    with db() as conn:
        conn.execute('INSERT OR REPLACE INTO device VALUES (1,?)', (hashlib.sha256(token.encode()).hexdigest(),))
    return token


def device_authorized(header):
    if not header.startswith('Bearer ') or len(header) > 256:
        return False
    with db() as conn:
        row = conn.execute('SELECT digest FROM device WHERE id=1').fetchone()
    return bool(row and hmac.compare_digest(hashlib.sha256(header[7:].encode()).hexdigest(), row[0]))


def ingest(data):
    if isinstance(data.get('envelope_mv'), bool):
        raise ValueError('envelope_mv must be a number')
    level = float(data['envelope_mv'])
    if not math.isfinite(level) or not 0 <= level <= 3300:
        raise ValueError('envelope_mv must be between 0 and 3300')
    carrier = data.get('carrier_present')
    transmitter = data.get('transmitter_on')
    for name, value in [('carrier_present', carrier), ('transmitter_on', transmitter)]:
        if value is not None and type(value) is not bool:
            raise ValueError(name + ' must be true, false or null')
    if transmitter is False and carrier is True:
        raise ValueError('Conflicting telemetry: transmitter off but carrier present')
    rssi = data.get('rssi')
    if rssi is not None and (type(rssi) not in (int, float) or not math.isfinite(rssi) or not 0 <= rssi <= 127):
        raise ValueError('rssi must be a receiver raw value 0–127 or null')
    now = time.time()
    with lock:
        previous = state['last']
        quiet = carrier is True and transmitter is not False and max(0, level-state['baseline_mv']) < state['threshold_mv']
        if not quiet:
            state['quiet_since'] = None
        elif state['quiet_since'] is None or previous is None or now-previous['time'] > 3:
            state['quiet_since'] = now
        state['last'] = dict(time=now, envelope_mv=level, carrier_present=carrier,
                             transmitter_on=transmitter, rssi=rssi,
                             source='SIMULATION' if DEMO_MODE else 'ESP32')
        state['history'].append({'time': now, 'level': level})


def snapshot():
    with lock:
        now = time.time()
        last = state['last']
        stale = last is None or now-last['time'] > 3
        seconds = 0 if stale or state['quiet_since'] is None else now-state['quiet_since']
        rise = None if stale else max(0, last['envelope_mv']-state['baseline_mv'])
        if stale:
            status = 'OFFLINE'
        elif last['transmitter_on'] is False:
            status = 'TRANSMITTER_OFF'
        elif last['carrier_present'] is False:
            status = 'NO_CARRIER'
        elif last['carrier_present'] is None:
            status = 'UNKNOWN'
        elif rise < state['threshold_mv']:
            status = 'CARRIER_NO_AUDIO' if seconds >= state['delay_s'] else 'QUIET_PENDING'
        elif rise < state['normal_threshold_mv']:
            status = 'LOW_AUDIO'
        else:
            status = 'NORMAL'
        return dict(status=status, quiet_seconds=round(seconds, 1), audio_rise_mv=rise,
                    last=last, telemetry_stale=stale, demo=DEMO_MODE,
                    threshold_mv=state['threshold_mv'], normal_threshold_mv=state['normal_threshold_mv'],
                    delay_s=state['delay_s'], baseline_mv=state['baseline_mv'], history=list(state['history']))


def set_settings(data):
    threshold = float(data['threshold_mv'])
    normal = float(data['normal_threshold_mv'])
    delay = float(data['delay_s'])
    baseline = float(data['baseline_mv'])
    if not all(map(math.isfinite, [threshold, normal, delay, baseline])) or not (
            1 <= threshold < normal <= 3300 and 0.5 <= delay <= 120 and 0 <= baseline <= 3300):
        raise ValueError('Require 1 ≤ silence threshold < normal threshold ≤ 3300, delay 0.5–120 s, baseline 0–3300 mV.')
    with lock:
        state.update(threshold_mv=threshold, normal_threshold_mv=normal, delay_s=delay,
                     baseline_mv=baseline, quiet_since=None)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, code, data, content_type='application/json', cookie=None):
        body = data if isinstance(data, bytes) else json.dumps(data).encode()
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'same-origin')
        self.send_header('Content-Length', str(len(body)))
        if cookie:
            self.send_header('Set-Cookie', cookie)
        self.end_headers()
        self.wfile.write(body)

    def session(self):
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get('Cookie', ''))
            token = cookie['fm_session'].value
        except (KeyError, ValueError):
            return None
        now = time.time()
        with auth_lock:
            for key in list(sessions):
                if sessions[key]['expires'] <= now:
                    del sessions[key]
            return sessions.get(token)

    def browser_request(self):
        if self.headers.get('X-FM-Request') != '1':
            return False
        origin = self.headers.get('Origin')
        return not origin or urlsplit(origin).netloc == self.headers.get('Host')

    def do_GET(self):
        if self.path == '/':
            filename = 'index.html' if self.session() else 'login.html'
            self.reply(200, (ROOT / filename).read_bytes(), 'text/html; charset=utf-8')
        elif self.path == '/api/session':
            session = self.session()
            self.reply(200, {'authenticated': bool(session), 'phone': session['phone'] if session else None})
        elif self.path == '/api/status':
            if not self.session():
                self.reply(401, {'error': 'Sign in to continue'}); return
            self.reply(200, snapshot())
        else:
            self.reply(404, {'error': 'Not found'})

    def do_POST(self):
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 4096:
                raise ValueError('Invalid request size')
            if self.path == '/api/readings':
                if DEMO_MODE:
                    self.reply(409, {'error': 'Stop demo mode before sending hardware readings'}); return
                if not device_authorized(self.headers.get('Authorization', '')):
                    self.reply(401, {'error': 'Valid device bearer token required'}); return
            else:
                if not self.browser_request():
                    self.reply(403, {'error': 'Same-origin dashboard request required'}); return
                if self.path != '/api/login' and not self.session():
                    self.reply(401, {'error': 'Sign in to continue'}); return
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict):
                raise ValueError('JSON object required')
            if self.path == '/api/login':
                self.login(data); return
            if self.path == '/api/logout':
                cookie = SimpleCookie(self.headers.get('Cookie', ''))
                with auth_lock:
                    sessions.pop(cookie['fm_session'].value, None)
                self.reply(200, {'ok': True}, cookie='fm_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'); return
            if self.path == '/api/readings':
                ingest(data)
            elif self.path == '/api/settings':
                set_settings(data)
            else:
                self.reply(404, {'error': 'Not found'}); return
            self.reply(200, {'ok': True})
        except (ValueError, KeyError, TypeError, OverflowError):
            self.reply(400, {'error': 'Invalid request. Check required fields, types and allowed ranges.'})

    def login(self, data):
        now = time.time()
        ip = self.client_address[0]
        with auth_lock:
            for key in list(login_attempts):
                if not login_attempts[key] or now-login_attempts[key][-1] >= 60:
                    del login_attempts[key]
            attempts = login_attempts[ip]
            while attempts and now-attempts[0] >= 60:
                attempts.popleft()
            if len(attempts) >= 5:
                self.reply(429, {'error': 'Too many attempts. Wait one minute and retry.'}); return
            attempts.append(now)
        password = data.get('password', '')
        if not isinstance(password, str) or len(password) > 256:
            self.reply(401, {'error': 'Phone number or password is incorrect.'}); return
        phone = authenticate(data.get('phone'), password)
        if not phone:
            self.reply(401, {'error': 'Phone number or password is incorrect.'}); return
        token = secrets.token_urlsafe(32)
        with auth_lock:
            for key in list(sessions):
                if sessions[key]['expires'] <= now:
                    del sessions[key]
            sessions[token] = {'phone': phone, 'expires': now+SESSION_SECONDS}
        self.reply(200, {'ok': True}, cookie=f'fm_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={SESSION_SECONDS}')


def demo():
    start = time.time()
    while True:
        phase = int((time.time()-start) // 12) % 4
        levels = [820, 720, 655, 655]
        ingest({'envelope_mv': levels[phase], 'carrier_present': phase != 3,
                'transmitter_on': phase != 3, 'rssi': 55 if phase != 3 else 0})
        time.sleep(.25)


def main():
    global DEMO_MODE
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--demo', action='store_true')
    parser.add_argument('--create-user', metavar='PHONE')
    parser.add_argument('--create-device-token', action='store_true')
    args = parser.parse_args()
    if args.create_user:
        try:
            password = getpass.getpass('Choose password (12+ characters): ')
            if password != getpass.getpass('Repeat password: '):
                raise ValueError('Passwords do not match')
            create_user(args.create_user, password)
        except ValueError as exc:
            parser.error(str(exc))
        print('Local account saved. Restart the server if resetting an existing password.'); return
    if args.create_device_token:
        print('New device token (copy into local firmware; previous token revoked):')
        print(create_device_token()); return
    with db() as conn:
        if not conn.execute('SELECT 1 FROM users LIMIT 1').fetchone():
            parser.error('First create your account: py -3 server.py --create-user "+COUNTRYCODE_NUMBER"')
    DEMO_MODE = args.demo
    if DEMO_MODE:
        state['baseline_mv'] = 650
        threading.Thread(target=demo, daemon=True).start()
    print(f'FM monitor listening on {args.host}:{args.port}; demo={args.demo}', flush=True)
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == '__main__':
    main()
