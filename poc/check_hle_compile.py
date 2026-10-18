#!/usr/bin/env python3
"""Compile a selected HLE subset unchanged, without SDL or game assets."""
import json
from pathlib import Path
import shlex
import subprocess

root = Path(__file__).resolve().parents[1]
hle = root / 'vendor/pcrecomp/runtime/win32hle'
results = []
for name in ('host_lite.c', 'pe_loader.c', 'kernel32.c', 'kernel32_ext.c', 'wsock32.c'):
    args = ['/usr/bin/clang', '-arch', 'arm64', '-fsyntax-only',
            '-I', str(hle), '-I', str(hle.parent / 'recomp32'), str(hle / name)]
    result = subprocess.run(args, text=True, capture_output=True)
    log = root / 'logs' / ('hle-' + name + '.log')
    log.write_text('$ ' + shlex.join(args) + '\n' + result.stdout + result.stderr
                   + f'\nexit_code={result.returncode}\n')
    results.append({'file': name, 'exit_code': result.returncode, 'log': str(log.relative_to(root))})
    print(f'{name}: {"syntax accepted" if result.returncode == 0 else "compile failed"}')
(root / 'logs/hle-compile-results.json').write_text(json.dumps(results, indent=2) + '\n')
# A syntax pass says nothing about pointer truncation or runtime correctness.
raise SystemExit(int(any(item['exit_code'] for item in results)))
