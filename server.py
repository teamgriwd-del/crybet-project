#!/usr/bin/env python3
"""Local FM monitor: Python standard library only."""
import argparse, collections, json, math, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

lock = threading.Lock()
state = {'threshold_mv': 45.0, 'delay_s': 5.0, 'baseline_mv': 0.0, 'last': None, 'quiet_since': None, 'history': collections.deque(maxlen=300)}

def ingest(data):
    level = float(data['envelope_mv'])
    if not math.isfinite(level) or not 0 <= level <= 3300:
        raise ValueError('envelope_mv must be between 0 and 3300')
    now = time.time()
    with lock:
        quiet = max(0, level-state['baseline_mv']) < state['threshold_mv']
        if not quiet:
            state['quiet_since'] = None
        elif state['quiet_since'] is None or state['last'] is None or now-state['last']['time'] > 3:
            state['quiet_since'] = now
        state['last'] = {'time': now, 'envelope_mv': level, 'source': str(data.get('source','ESP32'))[:40]}
        state['history'].append({'time': now, 'level': level})

def snapshot():
    with lock:
        now=time.time(); last=state['last']
        stale=last is None or now-last['time'] > 3
        seconds=0 if stale or state['quiet_since'] is None else now-state['quiet_since']
        status='OFFLINE' if stale else 'SILENCE' if seconds >= state['delay_s'] else 'QUIET' if state['quiet_since'] is not None else 'AUDIO'
        return dict(status=status, quiet_seconds=round(seconds,1), last=last, threshold_mv=state['threshold_mv'], delay_s=state['delay_s'], baseline_mv=state['baseline_mv'], history=list(state['history']))

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def reply(self, code, data, content_type='application/json'):
        body=data if isinstance(data,bytes) else json.dumps(data).encode()
        self.send_response(code); self.send_header('Content-Type',content_type); self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        if self.path == '/': self.reply(200,Path(__file__).with_name('index.html').read_bytes(),'text/html; charset=utf-8')
        elif self.path == '/api/status': self.reply(200,snapshot())
        else: self.reply(404,{'error':'Not found'})
    def do_POST(self):
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0 < size <= 4096: raise ValueError('Invalid request size')
            data=json.loads(self.rfile.read(size))
            if self.path == '/api/readings': ingest(data)
            elif self.path == '/api/settings':
                threshold=float(data['threshold_mv']); delay=float(data['delay_s']); baseline=float(data['baseline_mv'])
                if not all(map(math.isfinite,[threshold,delay,baseline])) or not (1 <= threshold <= 1000 and 0.5 <= delay <= 120 and 0 <= baseline <= 3300): raise ValueError('Settings out of range')
                with lock:
                    state.update(threshold_mv=threshold,delay_s=delay,baseline_mv=baseline,quiet_since=None)
            else: self.reply(404,{'error':'Not found'}); return
            self.reply(200,{'ok':True})
        except (ValueError,KeyError,TypeError,json.JSONDecodeError) as exc: self.reply(400,{'error':str(exc)})

def demo():
    start=time.time()
    while True:
        t=time.time()-start
        ingest({'envelope_mv':650+(150+35*math.sin(t*3) if t%25 < 15 else 5),'source':'SIMULATION'})
        time.sleep(.25)

if __name__ == '__main__':
    p=argparse.ArgumentParser(); p.add_argument('--host',default='127.0.0.1'); p.add_argument('--port',type=int,default=8000); p.add_argument('--demo',action='store_true'); args=p.parse_args()
    if args.demo:
        state['baseline_mv']=650
        threading.Thread(target=demo,daemon=True).start()
    print(f'FM monitor listening on {args.host}:{args.port}; demo={args.demo}',flush=True)
    ThreadingHTTPServer((args.host,args.port),Handler).serve_forever()
