#!/usr/bin/env python3
"""Fetch pinned official SDL frameworks into .local; no global installation."""
import hashlib
from pathlib import Path
import shutil
import subprocess
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
LOCAL=ROOT/'.local'
PACKAGES=[
    ('SDL','2.32.10','SDL2','4a7ac31640d70214e848f994be8a12849c0f97918a7e6c2e27a40036166d1a7f'),
    ('SDL_ttf','2.24.0','SDL2_ttf','677404e23a1a5f6efcbe64697471c5161283e4af5a6403dcb92235d7d83805cd'),
]
for repo,version,name,digest in PACKAGES:
    archive=LOCAL/'graphics-downloads'/f'{name}-{version}.dmg'
    archive.parent.mkdir(parents=True,exist_ok=True)
    if not archive.exists():
        url=f'https://github.com/libsdl-org/{repo}/releases/download/release-{version}/{archive.name}'
        temporary=archive.with_suffix('.download')
        with urllib.request.urlopen(url,timeout=60) as src,temporary.open('wb') as dest:
            shutil.copyfileobj(src,dest)
        temporary.replace(archive)
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=digest:
        raise SystemExit(f'Checksum mismatch: {archive}')
    framework=LOCAL/'Frameworks'/f'{name}.framework'
    if not framework.exists():
        mount=LOCAL/f'mount-{name}';mount.mkdir(exist_ok=True)
        subprocess.run(['hdiutil','attach','-readonly','-nobrowse','-mountpoint',str(mount),str(archive)],check=True)
        try:
            framework.parent.mkdir(exist_ok=True)
            shutil.copytree(mount/framework.name,framework,symlinks=True)
        finally:
            subprocess.run(['hdiutil','detach',str(mount)],check=True)
    subprocess.run(['lipo','-verify_arch','arm64',str(framework/name)],check=True)
    print(f'{name} {version}: SHA256 verified, ARM64 present')
include=LOCAL/'graphics-include/SDL2';include.mkdir(parents=True,exist_ok=True)
for header,framework in [('SDL.h','SDL2'),('SDL_ttf.h','SDL2_ttf')]:
    link=include/header
    if not link.is_symlink() and not link.exists():
        link.symlink_to(LOCAL/f'Frameworks/{framework}.framework/Headers/{header}')
