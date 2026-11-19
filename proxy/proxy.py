# Logging pass-through proxy to Maven Central. Env/args: port, logfile.
# Paths under /overlay/ ... not used. Paths listed in HIDE (file next to script) return 404 while "hidden".
import sys, urllib.request, urllib.error, http.server, threading, os
PORT=int(sys.argv[1]); LOG=sys.argv[2]
HIDE=os.path.join(os.path.dirname(__file__),'hide.txt')
CENTRAL='https://repo.maven.apache.org/maven2'
lock=threading.Lock()
def log(s):
    with lock, open(LOG,'a') as f: f.write(s+'\n')
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self): self.go(True)
    def do_HEAD(self): self.go(False)
    def go(self, body):
        hidden=[l.strip() for l in open(HIDE)] if os.path.exists(HIDE) else []
        if any(h and h in self.path for h in hidden):
            log(f'{self.command} {self.path} 404(hidden)'); self.send_response(404); self.end_headers(); return
        ov=os.path.join(os.path.dirname(__file__),'overlay',self.path.lstrip('/'))
        if os.path.isfile(ov):
            data=open(ov,'rb').read(); log(f'{self.command} {self.path} 200(overlay)'); self.send_response(200); self.send_header('Content-Length',str(len(data))); self.end_headers()
            if body: self.wfile.write(data)
            return
        try:
            r=urllib.request.urlopen(urllib.request.Request(CENTRAL+self.path,method=self.command),timeout=60)
            data=r.read(); code=r.status
        except urllib.error.HTTPError as e: data=b''; code=e.code
        log(f'{self.command} {self.path} {code}')
        self.send_response(code); self.send_header('Content-Length',str(len(data))); self.end_headers()
        if body: self.wfile.write(data)
    def log_message(self,*a): pass
http.server.ThreadingHTTPServer(('127.0.0.1',PORT),H).serve_forever()
