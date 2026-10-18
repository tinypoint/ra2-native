#!/usr/bin/env python3
"""Launch the current local ARM64 research build interactively, without a timer."""
import os
from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[1]
binary=ROOT/'.local/native-boot/ra2-native-boot'
game=ROOT/'game/ra2-upload-41bbcc83/game.exe'
if not binary.exists() or not game.exists():
    raise SystemExit('Prepare the local game assets and run tools/build_native_boot.py first')
env=os.environ.copy();env['RA2_PROBE_SECONDS']='0';env['RA2_TRACE']='0'
for key in ['RA2_PROBE_CLICK','RA2_PROBE_KEY','RA2_PROBE_CONTROL_FILE','RA2_FRAME_PATH']:env.pop(key,None)
log=ROOT/'logs/native-interactive.log'
print('Starting local ARM64 research build. Log:',log,flush=True)
with log.open('w') as out:
    p=subprocess.run([str(binary),str(game),'--with-launcher'],cwd=game.parent,env=env,stdout=out,stderr=subprocess.STDOUT)
raise SystemExit(p.returncode if p.returncode>=0 else 128-p.returncode)
