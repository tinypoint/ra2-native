#!/usr/bin/env python3
"""Build only FFmpeg's Bink components for the independent pthread Wasm target."""
from pathlib import Path
import os,subprocess
ROOT=Path(__file__).resolve().parents[1];SDK=ROOT/'.local/emsdk';SRC=ROOT/'.local/ffmpeg-7.1.5';OUT=ROOT/'.local/ffmpeg-web-build';PREFIX=ROOT/'.local/ffmpeg-web'
OUT.mkdir(exist_ok=True)
env={**os.environ,'PATH':str(ROOT/'.venv/bin')+':'+str(SDK/'node/24.19.0_64bit/bin')+':'+str(SDK/'upstream/emscripten')+':'+os.environ['PATH']}
flags=['--prefix='+str(PREFIX),'--cc='+str(SDK/'upstream/emscripten/emcc'),'--ar='+str(SDK/'upstream/emscripten/emar'),'--ranlib='+str(SDK/'upstream/emscripten/emranlib'),'--nm='+str(SDK/'upstream/bin/llvm-nm'),'--enable-cross-compile','--target-os=none','--arch=wasm32','--disable-asm','--disable-everything','--disable-programs','--disable-doc','--disable-network','--disable-avdevice','--disable-avfilter','--disable-swscale','--disable-autodetect','--enable-static','--disable-shared','--extra-cflags=-O1 -pthread','--extra-ldflags=-pthread','--enable-decoder=bink,binkaudio_dct,binkaudio_rdft','--enable-demuxer=bink','--enable-protocol=file','--enable-swresample']
for args,name in [([str(SRC/'configure'),*flags],'configure'),(['make','-j3'],'build'),(['make','install'],'install')]:
 if name=='configure' and (OUT/'ffbuild/config.mak').exists():continue
 with (ROOT/f'logs/web-movies-{name}.log').open('w') as log:
  p=subprocess.run(args,cwd=OUT,env=env,stdout=log,stderr=subprocess.STDOUT)
 if p.returncode:raise SystemExit(f'{name} failed: logs/web-movies-{name}.log')
print('Wasm Bink libraries built')
