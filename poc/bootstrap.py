#!/usr/bin/env python3
"""Fetch pinned tools, without running their setup scripts or game binaries."""
import json
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[1]
for name, spec in json.loads((root / 'repos.lock.json').read_text()).items():
    path = root / 'vendor' / name
    if not path.exists():
        path.mkdir(parents=True)
        subprocess.run(['git', 'init', str(path)], check=True)
        subprocess.run(['git', '-C', str(path), 'remote', 'add', 'origin', spec['url']], check=True)
        subprocess.run(['git', '-C', str(path), 'fetch', '--depth', '1', 'origin', spec['commit']], check=True)
        subprocess.run(['git', '-C', str(path), 'checkout', '--detach', 'FETCH_HEAD'], check=True)
    head = subprocess.check_output(['git', '-C', str(path), 'rev-parse', 'HEAD'], text=True).strip()
    if head != spec['commit']:
        raise SystemExit(f'{name}: unexpected HEAD {head}; existing checkout left unchanged')
    if subprocess.check_output(['git', '-C', str(path), 'status', '--porcelain'], text=True).strip():
        raise SystemExit(f'{name}: modified checkout; left unchanged')
    print(f'{name}: pinned and clean {head}')
