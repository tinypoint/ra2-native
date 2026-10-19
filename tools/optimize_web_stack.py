#!/usr/bin/env python3
"""Reduce native Wasm frames before shipping lifted functions to Safari."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from check_web_stack import bodies, locals_count, sections

ROOT=Path(__file__).resolve().parents[1]
source=ROOT/'.local/web-build/ra2-web.wasm'
optimizer=ROOT/'.local/emsdk/upstream/bin/wasm-opt'
cache=ROOT/'.local/web-optimized';cache.mkdir(parents=True,exist_ok=True)
flags=['--coalesce-locals','--vacuum','--preserve-type-order']
version=subprocess.check_output([str(optimizer),'--version'])
key=hashlib.sha256(source.read_bytes()+version+' '.join(flags).encode()).hexdigest()
optimized=cache/(key+'.wasm')
if not optimized.exists():
    temporary=optimized.with_suffix('.tmp')
    subprocess.run([str(optimizer),str(source),*flags,'-o',str(temporary)],env={**os.environ,'BINARYEN_CORES':'2'},check=True,timeout=1800)
    temporary.replace(optimized)
before=[locals_count(body) for body in bodies(sections(source.read_bytes()))]
after=[locals_count(body) for body in bodies(sections(optimized.read_bytes()))]
assert len(before)==len(after) and max(after)<4096,'Wasm frames remain too large for the mobile build'
report={'functions':len(before),'max_locals_before':max(before),'max_locals_after':max(after),'large_frames_before':sum(n>512 for n in before),'large_frames_after':sum(n>512 for n in after)}
(ROOT/'logs/web-stack-optimization-results.json').write_text(json.dumps(report,indent=2)+'\n')
shutil.copy2(optimized,source)
print('Wasm stack optimization:',json.dumps(report),flush=True)
