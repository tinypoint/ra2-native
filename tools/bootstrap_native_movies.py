#!/usr/bin/env python3
"""Build a pinned, LGPL-only Bink decoder locally from official FFmpeg source."""
import hashlib
from pathlib import Path
import subprocess
import tarfile
import urllib.request
ROOT=Path(__file__).resolve().parents[1]
LOCAL=ROOT/'.local';version='7.1.5'
archive=LOCAL/f'graphics-downloads/ffmpeg-{version}.tar.xz'
archive.parent.mkdir(parents=True,exist_ok=True)
if not archive.exists():
    with urllib.request.urlopen(f'https://ffmpeg.org/releases/{archive.name}',timeout=60) as r:
        archive.write_bytes(r.read())
sha=hashlib.sha256(archive.read_bytes()).hexdigest()
if sha!='de668509caf9e35e3cd162473441fdb29538c6d96ed080292b3cf9e6fc5d558f':
    raise SystemExit('FFmpeg archive checksum mismatch')
source=LOCAL/f'ffmpeg-{version}'
if not source.exists():
    with tarfile.open(archive) as tar:tar.extractall(LOCAL,filter='data')
build=LOCAL/'ffmpeg-build';build.mkdir(exist_ok=True)
args=[str(source/'configure'),'--prefix='+str(LOCAL/'ffmpeg'),'--disable-everything',
      '--disable-programs','--disable-doc','--disable-network','--disable-avdevice',
      '--disable-avfilter','--disable-swscale','--disable-autodetect','--enable-static',
      '--disable-shared','--enable-pic','--enable-decoder=bink,binkaudio_dct,binkaudio_rdft',
      '--enable-demuxer=bink','--enable-protocol=file','--enable-swresample']
if not (build/'ffbuild/config.mak').exists():
    with (ROOT/'logs/ffmpeg-configure.log').open('w') as log:
        subprocess.run(args,cwd=build,stdout=log,stderr=subprocess.STDOUT,check=True)
for cmd,name in [(['make','-j4'],'build'),(['make','install'],'install')]:
    with (ROOT/f'logs/ffmpeg-{name}.log').open('w') as log:
        subprocess.run(cmd,cwd=build,stdout=log,stderr=subprocess.STDOUT,check=True)
print('FFmpeg',version,'SHA256',sha,'Bink-only native decoder built')
