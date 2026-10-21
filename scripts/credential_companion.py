#!/usr/bin/env python3
"""Loopback-only server to inject provider keys into GitHub Actions secrets via gh CLI.
No credentials are stored locally or sent to GitHub Pages.
"""
import argparse
import http.server
import json
import pathlib
import re
import secrets
import shutil
import subprocess
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parents[1]
ALLOWED = frozenset({'ANTHROPIC_API_KEY', 'OPENAI_API_KEY', 'CURSOR_API_KEY', 'DEVIN_API_KEY', 'XAI_API_KEY'})
REPO_RE = re.compile(r'^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$')

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, token, **kwargs):
        self.secret_token = token
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def _json(self, code, payload):
        body=json.dumps(payload).encode()
        self.send_response(code)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Security-Policy',"frame-ancestors 'none'")
        self.send_header('Content-Length',str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _same_origin(self):
        origin=self.headers.get('Origin')
        if not origin: return False
        try:
            parsed=urllib.parse.urlsplit(origin)
            host=self.headers.get('Host','')
            return parsed.scheme=='http' and parsed.netloc==host and parsed.hostname in ('localhost','127.0.0.1')
        except ValueError:
            return False

    def do_GET(self):
        if self.path=='/api/health':
            self._json(200,{'service':'basis-credential-companion','token':self.secret_token});return
        if self.path.startswith('/api/'):
            self._json(404,{'error':'Unknown route'});return
        super().do_GET()

    def do_POST(self):
        if self.path!='/api/secrets':self._json(404,{'error':'Unknown route'});return
        if not self._same_origin() or not secrets.compare_digest(self.headers.get('X-Basis-Token',''),self.secret_token):
            self._json(403,{'error':'Denied: open Basis from this local companion.'});return
        if self.headers.get('Content-Type','').split(';')[0].strip()!='application/json':
            self._json(415,{'error':'Expected JSON'});return
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 1<=length<=16000: raise ValueError('Invalid request size')
            item=json.loads(self.rfile.read(length))
            repo, name, value=item['repo'],item['secret'],item['value']
            if not isinstance(repo,str) or not REPO_RE.fullmatch(repo):raise ValueError('Invalid repository')
            if name not in ALLOWED:raise ValueError('Provider not allowed')
            if not isinstance(value,str) or not 8<=len(value)<=8000 or any(c in value for c in '\r\n\x00'):
                raise ValueError('Invalid key (single-line required)')
        except (KeyError,ValueError,TypeError,json.JSONDecodeError):
            self._json(400,{'error':'Invalid repository, provider, or key'});return
        if not shutil.which('gh'):
            self._json(503,{'error':'Install GitHub CLI (gh), then run gh auth login.'});return
        try:
            # -f - reads the NAME=VALUE entry from stdin, avoiding argv exposure and disk writes.
            result=subprocess.run(['gh','secret','set','-f','-','-R',repo],input=f'{name}={value}\n',text=True,
                                  stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=30,check=False)
            if result.returncode: self._json(502,{'error':'GitHub rejected the write. Check gh auth status and repository Secrets permissions.'});return
            self._json(200,{'saved':True,'name':name})
        except subprocess.TimeoutExpired:
            self._json(504,{'error':'GitHub secret upload timed out.'})

    def log_message(self, format, *args):
        # No URLs, keys, request bodies or other potentially sensitive data in logs.
        return

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=8765)
    args=parser.parse_args()
    from functools import partial
    token=secrets.token_urlsafe(32)
    server=http.server.ThreadingHTTPServer(('127.0.0.1',args.port),partial(Handler,token=token))
    print(f'Open http://127.0.0.1:{server.server_port}/ ; localhost only. Press Ctrl+C to stop.',flush=True)
    server.serve_forever()

if __name__=='__main__':main()
