#!/usr/bin/env python3
"""Run the native startup/input probe and retain its real exit code."""
import argparse
import gzip
import os
import json
from pathlib import Path
import re
import subprocess

r=Path(__file__).resolve().parents[1]
ap=argparse.ArgumentParser();ap.add_argument('--attempt',required=True);ap.add_argument('--with-launcher',action='store_true');ap.add_argument('--seconds',type=int,default=20);a=ap.parse_args()
if not 1<=a.seconds<=120:raise SystemExit('Probe seconds must be 1..120')
if not re.fullmatch(r'[A-Za-z0-9_-]+',a.attempt):raise SystemExit('Invalid attempt name')
binary=r/'.local/native-boot/ra2-native-boot';game=r/'game/ra2-upload-41bbcc83/game.exe'
p=subprocess.run([str(binary),str(game),*(['--with-launcher'] if a.with_launcher else [])],cwd=game.parent,capture_output=True,text=True,errors='backslashreplace',timeout=a.seconds+10,env={**os.environ,"RA2_PROBE_SECONDS":str(a.seconds)})
log=p.stdout+p.stderr+f'\nexit_code={p.returncode}\n'
path=r/'logs'/f'native-boot-attempt-{a.attempt}.log'
if len(log)>200_000:
    path=path.with_suffix('.log.gz');path.write_bytes(gzip.compress(log.encode(),mtime=0))
else:path.write_text(log)
calls=re.findall(r'^\[hle\] (.+)$',p.stderr,re.M)
missing=re.findall(r'unimplemented import ([^ ]+)',p.stderr)
report={'attempt':a.attempt,'watchdog_seconds':a.seconds,'exit_code':p.returncode,
        'platform_launcher_objects':a.with_launcher,
        'entered_real_crt':'entering actual game CRT entry' in p.stderr,
        'api_calls':len(calls),'unique_api_names':list(dict.fromkeys(calls)),
        'unimplemented_import':missing[-1] if missing else None,
        'fatal_diagnostics':re.findall(r'^\[win32hle\] FATAL: (.+)$',p.stderr,re.M),
        'game_menu_verified':False,'log':str(path.relative_to(r))}
(r/'logs'/f'native-boot-attempt-{a.attempt}.json').write_text(json.dumps(report,indent=2)+'\n')
print(p.stderr[-4500:]);print(json.dumps(report,indent=2))
raise SystemExit(p.returncode if p.returncode>=0 else 128-p.returncode)
