#!/usr/bin/env python3
"""Drive pinned upstream whole-game lifting without version-specific remaster
patches/hooks. Generated game code stays under .local and is not distributed.
"""
from pathlib import Path
import hashlib
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
EXE=ROOT/'game/ra2-upload-41bbcc83/game.exe'
if hashlib.sha256(EXE.read_bytes()).hexdigest()!='fe67fdac5073530a79baec14c4e072b5e7e4c0c462cee9659870c5330e9e6e3e':
    raise SystemExit('Input differs from audited upload')
sys.path.insert(0,str(ROOT/'vendor/redalert2-recomp'))
import run_lift

original_targets=run_lift.targets
def targets():
    t=original_targets()
    t['game'].update({'seeds':str(ROOT/'poc/generated_game/rtti-seeds.json'),
                      'stats':str(ROOT/'.local/full-game-lift-stats.json'),
                      'hooks':{},'run_seeds':[], 'patches':lambda code,base:{}})
    return t
run_lift.targets=targets
sys.argv=[sys.argv[0],'--target','game','--exe',str(EXE),
          '--catalog',str(ROOT/'.local/ra2-functions.json'),
          '--out',str(ROOT/'.local/full-game-lift'),'--all', '--split','200']
run_lift.main()
