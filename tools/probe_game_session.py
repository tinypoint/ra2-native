#!/usr/bin/env python3
"""Start an isolated local native UI verification session; no network service."""
import argparse
from contextlib import nullcontext
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
from benchmark_native_game import game_settings
ROOT=Path(__file__).resolve().parents[1]
ap=argparse.ArgumentParser();ap.add_argument('name');ap.add_argument('--seconds',type=int,default=600);ap.add_argument('--game-speed',type=int,choices=range(6));a=ap.parse_args()
if not re.fullmatch(r'[A-Za-z0-9_-]+',a.name) or not 1<=a.seconds<=3600:raise SystemExit('Invalid session parameters')
folder=ROOT/'.local/sessions'/a.name;folder.mkdir(parents=True,exist_ok=False)
game=ROOT/'game/ra2-upload-41bbcc83/game.exe';binary=ROOT/'.local/native-release/ra2-native-boot'
identity=hashlib.sha256(game.read_bytes()).hexdigest()
if identity!='fe67fdac5073530a79baec14c4e072b5e7e4c0c462cee9659870c5330e9e6e3e':raise SystemExit('Unaudited input image')
env={**os.environ,'RA2_TRACE':'0','RA2_IDLE_PACING':'0','HLE_FILETRACE':'1','RA2_PROBE_SECONDS':str(a.seconds),
     'RA2_CAPTURE_MS':'500','RA2_FRAME_PATH':str(folder/'frame.ppm'),'RA2_PROBE_CONTROL_FILE':str(folder/'control.txt'),
     'RA2_METRICS_PATH':str(folder/'frames.jsonl'),'RA2_GAME_FRAME_VA':'0xA40D2C'}
for name in ['RA2_PROBE_CLICK','RA2_PROBE_KEY']:env.pop(name,None)
report={'name':a.name,'input_sha256':identity,'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'configured_game_speed':a.game_speed,'watchdog_seconds':a.seconds,'status':'running'}
with (game_settings(a.game_speed) if a.game_speed is not None else nullcontext()),(folder/'game.log').open('w') as log:
    started=time.monotonic();p=subprocess.Popen([str(binary),str(game),'--with-launcher'],cwd=game.parent,env=env,stdout=log,stderr=subprocess.STDOUT)
    report['pid']=p.pid;(folder/'session.json').write_text(json.dumps(report,indent=2)+'\n');print(folder,'pid',p.pid,flush=True)
    try:code=p.wait()
    except BaseException:
        p.terminate();p.wait(timeout=10);raise
    finally:
        report.update(status='stopped',process_exit_code=p.returncode,wall_seconds=time.monotonic()-started)
        (folder/'session.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
