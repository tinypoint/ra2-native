#!/usr/bin/env python3
"""Private independent game host with immutable resources and byte-range support."""
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import re
import shutil
from pathlib import Path
import secrets
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
LOCAL=ROOT/'.local/web-preview';LOCAL.mkdir(parents=True,exist_ok=True)
ap=argparse.ArgumentParser();ap.add_argument('--port',type=int,default=8767);args=ap.parse_args()
tokenfile=LOCAL/'access-token'
if not tokenfile.exists():tokenfile.write_text(secrets.token_urlsafe(18));tokenfile.chmod(0o600)
token=tokenfile.read_text().strip();prefix='/'+token+'/'
GAME=ROOT/'game/ra2-upload-41bbcc83';BUILD=ROOT/'.local/web-published'
asset_paths={}
def identity(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
 return h.hexdigest()
def manifest():
 files=[];artifacts={}
 for path in sorted(GAME.iterdir()):
  if not path.is_file() or not (path.suffix.lower() in {'.mix','.mmx','.map'} or path.name in {'game.exe','Blowfish.dll','RA2.INI'}):continue
  digest=identity(path);url='asset/'+digest+'/'+path.name;asset_paths[url]=path
  files.append({'name':path.name,'size':path.stat().st_size,'sha256':digest,'url':url})
 for path in sorted(BUILD.glob('ra2-web.*')):
  if path.suffix not in {'.js','.wasm'}:continue
  digest=identity(path);url='artifact/'+digest+'/'+path.name
  frozen=LOCAL/'artifacts'/digest/path.name;frozen.parent.mkdir(parents=True,exist_ok=True)
  if not frozen.exists():shutil.copy2(path,frozen)
  asset_paths[url]=frozen
  artifacts[path.name]={'name':path.name,'size':path.stat().st_size,'sha256':digest,'url':url}
 result={'ready':'ra2-web.js' in artifacts and 'ra2-web.wasm' in artifacts,'files':files,'script':artifacts.get('ra2-web.js'),'artifacts':artifacts}
 update=LOCAL/'runtime-update.json'
 if update.exists():
  candidate=json.loads(update.read_text())
  if candidate['to']==artifacts.get('ra2-web.wasm',{}).get('sha256'):result['programUpdate']=candidate
 return result
assets={'':('web/index.html','text/html; charset=utf-8'),'index.html':('web/index.html','text/html; charset=utf-8'),'style.css':('web/style.css','text/css; charset=utf-8'),'app.js':('web/app.js','text/javascript; charset=utf-8'),'frame-meter.js':('web/frame-meter.js','text/javascript; charset=utf-8'),'runtime-update.js':('web/runtime-update.js','text/javascript; charset=utf-8')}
manifest_cache=None
manifest_signature=None
class Handler(BaseHTTPRequestHandler):
 def do_POST(self):
  if self.path!=prefix+'diagnostics':self.send_error(404);return
  try:
   length=int(self.headers.get('Content-Length','0'))
   if not 0<length<=32768:self.send_error(413);return
   report=json.loads(self.rfile.read(length))
   if not isinstance(report,dict):raise ValueError('Expected object')
   entry={'time':datetime.now(timezone.utc).isoformat(),**{key:str(report.get(key,''))[:16000] for key in ('kind','error','stage','logs')}}
   with (LOCAL/'browser-errors.jsonl').open('a') as output:output.write(json.dumps(entry,ensure_ascii=False)+'\n')
  except (ValueError,UnicodeError):self.send_error(400);return
  self.send_response(204);self.send_header('Content-Length','0');self.end_headers()
 def do_GET(self):self.respond(False)
 def do_HEAD(self):self.respond(True)
 def respond(self,head):
  path=self.path.split('?',1)[0]
  if path==prefix+'setup.html':self.send_response(302);self.send_header('Location',prefix+'#settings');self.send_header('Cache-Control','no-cache');self.send_header('Content-Length','0');self.end_headers();return
  if path==prefix[:-1]:self.send_response(302);self.send_header('Location',prefix);self.end_headers();return
  if not path.startswith(prefix):self.send_error(404);return
  name=path[len(prefix):]
  file_path=None
  global manifest_cache,manifest_signature
  if name=='manifest.json':
   signature=tuple((p.name,p.stat().st_mtime_ns,p.stat().st_size) for p in [*sorted(BUILD.glob('ra2-web.*')),*LOCAL.glob('runtime-update.json')])
   if manifest_cache is None or signature!=manifest_signature:manifest_cache=manifest();manifest_signature=signature
   data=json.dumps(manifest_cache).encode();mime='application/json';cache='no-store'
  elif (name in {'resource-pack.ra2pack','runtime-update.ra2update','runtime-stack-update.ra2update'} or re.fullmatch(r'ra2-web-v\d+\.\d+\.\d+(?:-full)?\.ra2update',name)) and (LOCAL/name).is_file():
   file_path=LOCAL/name;mime='application/octet-stream';cache='no-cache'
  elif name in asset_paths:
   file_path=asset_paths[name];mime='application/wasm' if file_path.suffix=='.wasm' else 'text/javascript; charset=utf-8' if file_path.suffix=='.js' else 'application/octet-stream';cache='private, max-age=31536000, immutable'
  elif name in assets:
   file,mime=assets[name];data=(ROOT/file).read_bytes();cache='no-cache'
  else:self.send_error(404);return
  total=file_path.stat().st_size if file_path else len(data)
  etag='"'+((str(file_path.stat().st_mtime_ns) if '/' not in name else name.split('/')[1]) if file_path else hashlib.sha256(data).hexdigest())+'"'
  status=304 if self.headers.get('If-None-Match')==etag else 200
  start=0;end=total-1
  range_header=self.headers.get('Range')
  if status==200 and file_path and range_header and self.headers.get('If-Range',etag)==etag:
   match=re.fullmatch(r'bytes=(\d*)-(\d*)',range_header)
   if not match or not any(match.groups()):self.send_error(416);return
   left,right=match.groups()
   if left:start=int(left);end=min(int(right),total-1) if right else total-1
   else:start=max(0,total-int(right))
   if start>=total or end<start:
    self.send_response(416);self.send_header('Content-Range',f'bytes */{total}');self.send_header('Content-Length','0');self.end_headers();return
   status=206
  self.send_response(status);self.send_header('Content-Type',mime);self.send_header('Cache-Control',cache);self.send_header('ETag',etag);self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer');self.send_header('Cross-Origin-Opener-Policy','same-origin');self.send_header('Cross-Origin-Embedder-Policy','require-corp');self.send_header('Cross-Origin-Resource-Policy','same-origin');self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; style-src 'self'; connect-src 'self'; worker-src 'self' blob:; img-src 'self' data: blob:; media-src 'self' blob:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
  if file_path:self.send_header('Accept-Ranges','bytes')
  if file_path and '/' not in name:self.send_header('Content-Disposition',f'attachment; filename="{name}"')
  if status==206:self.send_header('Content-Range',f'bytes {start}-{end}/{total}')
  length=end-start+1 if status!=304 else 0
  self.send_header('Content-Length',str(length));self.end_headers()
  if head or status==304:return
  try:
   if file_path:
    with file_path.open('rb') as source:
     source.seek(start);remaining=length
     while remaining:
      block=source.read(min(256*1024,remaining))
      if not block:break
      self.wfile.write(block);remaining-=len(block)
   else:self.wfile.write(data)
  except (BrokenPipeError,ConnectionResetError):
   self.log_message('Client disconnected during transfer')
 def log_message(self,format,*args):
  # Record resource names without persisting the access token in request logs.
  print(format%args if not args else (format%args).replace(token,'[token]'),flush=True)
(LOCAL/'server.json').write_text(json.dumps({'port':args.port,'path':prefix,'status':'starting'})+'\n')
server=ThreadingHTTPServer(('0.0.0.0',args.port),Handler)
print('Web preview listening on port',args.port,flush=True)
try:server.serve_forever()
except KeyboardInterrupt:pass
finally:server.server_close()
