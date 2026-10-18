#!/usr/bin/env python3
"""Bundle the native research build locally; game assets remain outside the app."""
from pathlib import Path
import plistlib
import shutil
import subprocess
ROOT=Path(__file__).resolve().parents[1]
APP=ROOT/'.local/Red Alert 2 ARM64.app';contents=APP/'Contents'
if APP.exists():raise SystemExit(f'App already exists: {APP}; retain it or move it before rebuilding')
for name in ['MacOS','Resources','Frameworks']:(contents/name).mkdir(parents=True,exist_ok=True)
exe=contents/'MacOS/ra2-native-boot'
shutil.copy2(ROOT/'.local/native-boot/ra2-native-boot',exe)
for name in ['SDL2','SDL2_ttf']:
    shutil.copytree(ROOT/f'.local/Frameworks/{name}.framework',contents/f'Frameworks/{name}.framework',symlinks=True)
subprocess.run(['install_name_tool','-delete_rpath',str(ROOT/'.local/Frameworks'),'-add_rpath','@executable_path/../Frameworks',str(exe)],check=True)
(contents/'Resources/game-directory.txt').write_text(str(ROOT/'game/ra2-upload-41bbcc83')+'\n')
launcher=contents/'MacOS/RA2Native'
launcher.write_text('''#!/bin/sh
bundle_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd) || exit 2
IFS= read -r asset_dir < "$bundle_dir/Resources/game-directory.txt" || exit 2
cd "$asset_dir" || exit 2
mkdir -p "$HOME/Library/Logs/RA2Native" || exit 2
export RA2_PROBE_SECONDS="${RA2_PROBE_SECONDS:-0}"
export RA2_TRACE="${RA2_TRACE:-0}"
exec "$bundle_dir/MacOS/ra2-native-boot" "$asset_dir/game.exe" --with-launcher >> "$HOME/Library/Logs/RA2Native/game.log" 2>&1
''')
launcher.chmod(0o755)
(contents/'Info.plist').write_bytes(plistlib.dumps({
    'CFBundleExecutable':'RA2Native','CFBundleIdentifier':'org.ra2native.research',
    'CFBundleName':'Red Alert 2 ARM64','CFBundleDisplayName':'Red Alert 2 ARM64',
    'CFBundleVersion':'0.1','CFBundleShortVersionString':'0.1',
    'CFBundlePackageType':'APPL','LSMinimumSystemVersion':'11.0',
    'NSHighResolutionCapable':True,'LSApplicationCategoryType':'public.app-category.strategy-games',
}))
(contents/'Resources/RESEARCH_BUILD.txt').write_text('Local ARM64 research build. User-provided game assets remain outside this bundle.\nAd-hoc signed for local testing; not notarized. full-match, save and YR validation are pending.\nSDL licenses remain in each framework. FFmpeg 7.1.5 was built LGPL-only; source and configuration are retained in the project .local directory. Do not distribute this research bundle.\n')
subprocess.run(['xattr','-cr',str(APP)],check=True)
subprocess.run(['codesign','--force','--deep','--sign','-',str(APP)],check=True)
subprocess.run(['codesign','--verify','--deep','--strict',str(APP)],check=True)
print(APP)
