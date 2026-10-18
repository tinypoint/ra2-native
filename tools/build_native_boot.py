#!/usr/bin/env python3
"""Incrementally compile full lifted game to an ARM64 native game host."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'.local/native-boot'
OBJ=OUT/'objects'
OBJ.mkdir(parents=True,exist_ok=True)
GEN=ROOT/'.local/full-game-lift'
stats=ROOT/'.local/full-game-lift-stats.json'
if not stats.exists() or json.loads(stats.read_text())['errors']:
    raise SystemExit('Complete tools/lift_game_for_arm64.py successfully first')
sources=[*sorted(GEN.glob('*.c')),ROOT/'runtime/arm64/native_boot.c',ROOT/'runtime/arm64/guest_memory.c',
         ROOT/'runtime/win32hle-arm64/host_lite.c',ROOT/'runtime/win32hle-arm64/kernel32.c',ROOT/'runtime/win32hle-arm64/pe_loader.c',
         ROOT/'runtime/win32hle-arm64/kernel32_crt.c',ROOT/'runtime/win32hle-arm64/kernel32_ext.c',
         ROOT/'runtime/win32hle-arm64/hle_path.c',ROOT/'runtime/win32hle-arm64/module.c',ROOT/'runtime/win32hle-arm64/winmm.c',
         ROOT/'runtime/win32hle-arm64/wsock32.c',ROOT/'runtime/win32hle-arm64/ole32.c',ROOT/'runtime/win32hle-arm64/advapi32.c',
         ROOT/'runtime/ra2/blowfish.c',*[ROOT/'runtime/win32hle-arm64'/n for n in ['user32.c','ddraw.c','gdi32.c','gdidc.c','screen.c','dsound.c','bink.c']]]
flags=['/usr/bin/clang','-arch','arm64','-O0','-g','-w','-DRECOMP_LOCAL_REGS','-fno-strict-aliasing','-fwrapv',
       '-ffp-contract=off','-include',str(ROOT/'runtime/arm64/guest_cpu.h'),'-I',str(GEN),
       '-I',str(ROOT/'runtime/win32hle-arm64'),'-I',str(ROOT/'runtime/arm64'),
       '-I',str(ROOT/'vendor/pcrecomp/runtime/recomp32'),'-DHLE_WITH_FFMPEG','-I',str(ROOT/'.local/ffmpeg/include'),'-I',str(ROOT/'.local/graphics-include'),'-I',str(ROOT/'.local/Frameworks/SDL2.framework/Headers'),'-F',str(ROOT/'.local/Frameworks')]
headers=[*GEN.glob('*.h'),* (ROOT/'runtime/arm64').glob('*.h'),
         *(ROOT/'runtime/win32hle-arm64').glob('*.h'),ROOT/'vendor/pcrecomp/runtime/recomp32/recomp_types.h']
signature=hashlib.sha256((' '.join(flags)).encode()+b''.join(p.read_bytes() for p in sorted(headers))).hexdigest()

def compile_one(src):
    obj=OBJ/(src.stem+'.o');stamp=obj.with_suffix('.json')
    key=hashlib.sha256(src.read_bytes()+signature.encode()).hexdigest()
    if obj.exists() and stamp.exists() and stamp.read_text()==key:return obj,False
    args=[*flags,'-c',str(src),'-o',str(obj)]
    p=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=180)
    (OUT/(src.stem+'-compile.log')).write_text('$ '+shlex.join(args)+'\n'+p.stdout+p.stderr+f'\nexit_code={p.returncode}\n')
    if p.returncode:raise RuntimeError(f'{src.name}: {p.stderr[:1500]}')
    stamp.write_text(key);return obj,True

start=time.monotonic();objects=[];failed=[];rebuilt=0
with ThreadPoolExecutor(max_workers=3) as pool:
    jobs={pool.submit(compile_one,s):s for s in sources}
    for n,future in enumerate(as_completed(jobs),1):
        try:
            obj,changed=future.result();objects.append(obj);rebuilt+=changed
        except Exception as exc:failed.append(str(exc));print('FAIL',exc,flush=True)
        if n%10==0:print(f'compiled {n}/{len(jobs)}, failures={len(failed)}',flush=True)
if failed:
    (ROOT/'logs/native-boot-build-errors.json').write_text(json.dumps(failed,indent=2)+'\n')
    raise SystemExit(1)
args=['/usr/bin/clang','-arch','arm64',*map(str,objects),'-L',str(ROOT/'.local/ffmpeg/lib'),'-lavformat','-lavcodec','-lswresample','-lavutil','-framework','CoreFoundation','-framework','Security','-F',str(ROOT/'.local/Frameworks'),'-framework','SDL2','-framework','SDL2_ttf','-Wl,-rpath,'+str(ROOT/'.local/Frameworks'),'-o',str(OUT/'ra2-native-boot')]
p=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=60)
(ROOT/'logs/native-boot-link.log').write_text('$ '+shlex.join(args)+'\n'+p.stdout+p.stderr+f'\nexit_code={p.returncode}\n')
if p.returncode:print(p.stderr);raise SystemExit(p.returncode)
print(f'ARM64 boot probe built; rebuilt={rebuilt}, elapsed={time.monotonic()-start:.1f}s',flush=True)
