#!/usr/bin/env python3
"""Compile the actual lifted game into a separate browser/WebAssembly target."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
import hashlib,json,os,subprocess,time
ROOT=Path(__file__).resolve().parents[1];SDK=ROOT/'.local/emsdk';OUT=ROOT/'.local/web-build';GEN=ROOT/'.local/full-game-lift';HLE=OUT/'hle';OBJ=OUT/'objects'
for p in [HLE,OBJ]:p.mkdir(parents=True,exist_ok=True)
env={**os.environ,'PATH':str(ROOT/'.venv/bin')+':'+str(SDK/'node/24.19.0_64bit/bin')+':'+str(SDK/'upstream/emscripten')+':'+os.environ['PATH']}
emcc=str(SDK/'upstream/emscripten/emcc')
names=['host_lite','kernel32','pe_loader','kernel32_crt','kernel32_ext','hle_path','module','winmm','wsock32','ole32','advapi32','user32','ddraw','gdi32','gdidc','screen','dsound','bink','storage']
# Keep native sources untouched; materialize platform adaptations in ignored build output.
for name in names:
 s=(ROOT/('runtime/web/screen.c' if name=='screen' else f'runtime/win32hle-arm64/{name}.c')).read_text()
 s=s.replace('st_mtimespec','st_mtim').replace('st_atimespec','st_atim')
 s=s.replace('h->sin_len=sizeof *h;','/* Emscripten sockaddr_in has no Darwin sin_len. */')
 if name=='user32':
  from patch_web_user32 import patch as patch_user32
  s=patch_user32(s)
 if name=='gdidc':s=s.replace('/System/Library/Fonts/Supplemental/','/game/fonts/')
 (HLE/(name+'.c')).write_text(s)
s=(ROOT/'runtime/arm64/native_boot.c').read_text().replace('hle_screen_frame_hook=capture_frame;','extern void ra2_web_frame(const uint8_t *,int,int,int,int);\n    hle_screen_frame_hook=ra2_web_frame;')
s=s.replace('host_started_ms=hle_ticks_ms();','chdir("/game");setenv("RA2_TRACE","0",1);setenv("RA2_PROBE_SECONDS","0",1);\n    host_started_ms=hle_ticks_ms();')
(HLE/'web_boot.c').write_text(s)
# Safari has a small native call stack. Keep this reentrant menu callback's
# temporaries on the linear C stack instead of thousands of native Wasm locals.
lift_sources=[]
for src in sorted(GEN.glob('*.c')):
 if src.name=='recomp_0062.c':
  original=src.read_text();needle='void sub_005F6690(void) {'
  assert original.count(needle)==1
  copy=HLE/src.name
  copy.write_text(original.replace(needle,'__attribute__((optnone, noinline)) '+needle))
  src=copy
 lift_sources.append(src)
sources=[*lift_sources,*[HLE/(n+'.c') for n in names],HLE/'web_boot.c',ROOT/'runtime/web/guest_memory.c',ROOT/'runtime/web/input.c',ROOT/'runtime/web/mobile.c',ROOT/'runtime/ra2/blowfish.c']
flags=['-O1','-w','-pthread','-DRECOMP_LOCAL_REGS','-fno-strict-aliasing','-fwrapv','-ffp-contract=off','-include',str(ROOT/'runtime/arm64/guest_cpu.h'),'-I',str(GEN),'-I',str(ROOT/'runtime/win32hle-arm64'),'-I',str(ROOT/'runtime/arm64'),'-I',str(ROOT/'vendor/pcrecomp/runtime/recomp32'),'-DHLE_WITH_FFMPEG','-I',str(ROOT/'.local/ffmpeg-web/include'),'--use-port=sdl2','--use-port=sdl2_ttf']
headers=[*GEN.glob('*.h'),* (ROOT/'runtime/arm64').glob('*.h'),*(ROOT/'runtime/win32hle-arm64').glob('*.h'),ROOT/'vendor/pcrecomp/runtime/recomp32/recomp_types.h']
sig=hashlib.sha256((' '.join(flags)).encode()+b''.join(p.read_bytes() for p in sorted(headers))).digest()
def compile_one(src):
 obj=OBJ/(src.stem+'.o');stamp=obj.with_suffix('.sha');key=hashlib.sha256(src.read_bytes()+sig).hexdigest()
 if obj.exists() and stamp.exists() and stamp.read_text()==key:return obj
 p=subprocess.run([emcc,*flags,'-c',str(src),'-o',str(obj)],env=env,capture_output=True,text=True,timeout=600)
 (OUT/(src.stem+'.log')).write_text(p.stdout+p.stderr)
 if p.returncode:raise RuntimeError(src.name+': '+p.stderr[-1800:])
 stamp.write_text(key);return obj
start=time.monotonic();objects=[];failures=[]
# Build the ports once before parallel compiler jobs to avoid cache mutation races.
p=subprocess.run([emcc,*flags,'-c',str(ROOT/'runtime/web/input.c'),'-o',str(OUT/'ports-probe.o')],env=env,capture_output=True,text=True,timeout=600)
(OUT/'ports.log').write_text(p.stdout+p.stderr)
if p.returncode:raise SystemExit('SDL ports failed: '+p.stderr[-1600:])
# SDL 2.32.10's audio driver creates AudioContext on the UI thread but reads
# sampleRate in the application pthread. Keep that read on its owning thread.
for audio in (SDK/'upstream/emscripten/cache/ports/sdl2').glob('SDL-*/src/audio/emscripten/SDL_emscriptenaudio.c'):
 old=audio.read_text();new=old.replace('this->spec.freq = EM_ASM_INT({','this->spec.freq = MAIN_THREAD_EM_ASM_INT({')
 if new!=old:
  audio.write_text(new)
  lib=SDK/'upstream/emscripten/cache/sysroot/lib/wasm32-emscripten/libSDL2-mt.a'
  lib.unlink(missing_ok=True)
  p=subprocess.run([emcc,*flags,'-c',str(ROOT/'runtime/web/input.c'),'-o',str(OUT/'ports-probe.o')],env=env,capture_output=True,text=True,timeout=600)
  (OUT/'ports-patched.log').write_text(p.stdout+p.stderr)
  if p.returncode:raise SystemExit('Patched SDL build failed: '+p.stderr[-1600:])

with ThreadPoolExecutor(max_workers=3) as pool:
 jobs=[pool.submit(compile_one,s) for s in sources]
 for n,f in enumerate(as_completed(jobs),1):
  try:objects.append(f.result())
  except Exception as e:failures.append(str(e));print('FAIL',e,flush=True)
  if n%10==0:print('Compiled',n,'/',len(sources),'failures',len(failures),flush=True)
if failures:(ROOT/'logs/web-build-errors.json').write_text(json.dumps(failures,indent=2)+'\n');raise SystemExit(1)
objects=[OBJ/(src.stem+'.o') for src in sources]  # Stable link order keeps updates reproducible.
link=[emcc,'-O1','-pthread',*map(str,objects),'-L',str(ROOT/'.local/ffmpeg-web/lib'),'-lavformat','-lavcodec','-lswresample','-lavutil','--use-port=sdl2','--use-port=sdl2_ttf','-sGLOBAL_BASE=65536','-sMODULARIZE=1','-sEXPORT_NAME=createRA2Web','-sPROXY_TO_PTHREAD=1','-sPTHREAD_POOL_SIZE=6','-sINITIAL_MEMORY=67108864','-sMAXIMUM_MEMORY=1610612736','-sALLOW_MEMORY_GROWTH=1','-sSTACK_SIZE=4194304','-sEXPORTED_RUNTIME_METHODS=FS,callMain','-sEXPORTED_FUNCTIONS=_main,_ra2_web_mouse,_ra2_web_key,_ra2_web_cancel','-sENVIRONMENT=web,worker','-sASSERTIONS=1','-sEXIT_RUNTIME=1','-o',str(OUT/'ra2-web.js')]
p=subprocess.run(link,env=env,capture_output=True,text=True,timeout=600);(ROOT/'logs/web-link.log').write_text(p.stdout+p.stderr)
if p.returncode:raise SystemExit(p.stderr[-2500:])
from patch_web_worker_errors import patch
patch(OUT/'ra2-web.js')
subprocess.run([str(ROOT/'.venv/bin/python'),str(ROOT/'tools/optimize_web_stack.py')],check=True,env=env)
print('Full game Wasm built in',round(time.monotonic()-start,1),'seconds',flush=True)
