#!/usr/bin/env python3
"""Build and exercise the actual adapted Win32 HLE, including software graphics (no display opened)."""
import json
from pathlib import Path
import shlex
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'.local/arm64-runtime'
OUT.mkdir(exist_ok=True)
report=json.loads((ROOT/'logs/real-game-results.json').read_text())
addresses=sorted(int(f['address'],16) for f in report['functions'])
dispatch=['#include "recomp_types.h"']
dispatch += [f'extern void sub_{va:08X}(void);' for va in addresses]
dispatch += ['extern void runtime_timer_callback(void);']
dispatch += ['extern void runtime_thread_callback(void);','extern void runtime_window_callback(void);']
dispatch += ['const recomp_dispatch_entry_t recomp_dispatch_table[] = {']
dispatch += [f'{{0x{va:08X}u,sub_{va:08X}}},' for va in addresses]
dispatch += ['{0x00ef0000u,runtime_timer_callback},','{0x00ef0010u,runtime_thread_callback},','{0x00ef0020u,runtime_window_callback},','};',f'const uint32_t recomp_dispatch_count={len(addresses)+3};']
(OUT/'dispatch.c').write_text('\n'.join(dispatch)+'\n')
sources=[ROOT/'runtime/arm64/guest_memory.c',ROOT/'runtime/win32hle-arm64/host_lite.c',
         ROOT/'runtime/win32hle-arm64/kernel32.c',ROOT/'runtime/win32hle-arm64/pe_loader.c',
         ROOT/'runtime/win32hle-arm64/kernel32_crt.c',ROOT/'runtime/win32hle-arm64/kernel32_ext.c',
         ROOT/'runtime/win32hle-arm64/hle_path.c',ROOT/'runtime/win32hle-arm64/module.c',ROOT/'runtime/win32hle-arm64/winmm.c',
         ROOT/'runtime/win32hle-arm64/wsock32.c',
         ROOT/'runtime/win32hle-arm64/ole32.c',
         ROOT/'runtime/win32hle-arm64/advapi32.c',
         ROOT/'runtime/ra2/blowfish.c',*[ROOT/'runtime/win32hle-arm64'/n for n in ['user32.c','ddraw.c','gdi32.c','gdidc.c','dsound.c','bink.c']],
         ROOT/'poc/generated_game/real_functions.c',OUT/'dispatch.c',ROOT/'poc/arm64_runtime_checks.c']
args=['/usr/bin/clang','-arch','arm64','-O2','-g','-fno-strict-aliasing','-fwrapv','-ffp-contract=off',
      '-I',str(ROOT/'runtime/win32hle-arm64'),'-I',str(ROOT/'runtime/arm64'),
      '-I',str(ROOT/'vendor/pcrecomp/runtime/recomp32'),'-I',str(ROOT/'poc/generated_game'),
      '-DHLE_WITH_FFMPEG','-I',str(ROOT/'.local/ffmpeg/include'),'-I',str(ROOT/'.local/graphics-include'),'-I',str(ROOT/'.local/Frameworks/SDL2.framework/Headers'),'-F',str(ROOT/'.local/Frameworks'),*map(str,sources),'-L',str(ROOT/'.local/ffmpeg/lib'),'-lavformat','-lavcodec','-lswresample','-lavutil','-framework','CoreFoundation','-framework','Security','-framework','SDL2','-framework','SDL2_ttf','-Wl,-rpath,'+str(ROOT/'.local/Frameworks'),'-o',str(OUT/'runtime_checks')]
def run(args,log):
    p=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=60)
    (ROOT/'logs'/log).write_text('$ '+shlex.join(args)+'\n'+p.stdout+p.stderr+f'\nexit_code={p.returncode}\n')
    print(p.stdout,end='')
    if p.returncode:print(p.stderr);raise SystemExit(p.returncode)
    return p
run(args,'arm64-runtime-compile.log')
run(['/usr/bin/file',str(OUT/'runtime_checks')],'arm64-runtime-file.log')
p=run([str(OUT/'runtime_checks'),str(ROOT/'game/ra2-upload-41bbcc83/game.exe')],'arm64-runtime-execution.log')
data=json.loads(p.stdout.strip().splitlines()[-1])
(ROOT/'logs/arm64-runtime-results.json').write_text(json.dumps(data,indent=2)+'\n')
