#!/usr/bin/env python3
"""Check bounded web guest memory independently, natively or with emcc+Node."""
import argparse
import json
import os
from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[1]
ap=argparse.ArgumentParser();ap.add_argument('--emcc',type=Path);args=ap.parse_args()
out=ROOT/'.local/web-memory-checks';out.mkdir(parents=True,exist_ok=True)
src=[str(ROOT/'runtime/web/guest_memory.c'),str(ROOT/'poc/web_memory_checks.c')]
if args.emcc:
    exe=out/'checks.js'
    cmd=[str(args.emcc),'-O1','-pthread','-sINITIAL_MEMORY=570425344','-sMAXIMUM_MEMORY=1073741824','-sALLOW_MEMORY_GROWTH=1','-sENVIRONMENT=node',*src,'-I',str(ROOT/'runtime/arm64'),'-o',str(exe)]
    node=next((p for p in (ROOT/'.local/emsdk/node').glob('*/bin/node') if p.is_file()),None)
    run=[str(node or 'node'),str(exe)]
else:
    exe=out/'checks'
    cmd=['cc','-std=c11','-O1','-pthread',*src,'-I',str(ROOT/'runtime/arm64'),'-o',str(exe)]
    run=[str(exe)]
subprocess.run(cmd,cwd=ROOT,check=True)
p=subprocess.run(run,cwd=ROOT,capture_output=True,text=True,check=True)
report=json.loads(p.stdout.strip().splitlines()[-1]);report['target']='wasm32-node' if args.emcc else 'native'
# Pointer rejection aborts; test in child processes, without crash reporting on macOS.
if not args.emcc:
    import resource
    def no_core():resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    report['invalid_pointers_rejected']=all(subprocess.run([*run,kind],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,preexec_fn=no_core).returncode!=0 for kind in ['low','high'])
    assert report['invalid_pointers_rejected']
path=ROOT/'logs'/('web-memory-wasm-results.json' if args.emcc else 'web-memory-native-results.json')
path.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
