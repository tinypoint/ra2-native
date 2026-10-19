#!/usr/bin/env python3
"""Encode a verified Git binary delta so imported resources can be reused."""
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import zlib
import argparse
import re

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / '.local/web-preview'
parser=argparse.ArgumentParser()
parser.add_argument('--version',required=True,help='Program release number, e.g. 0.1.1')
parser.add_argument('--base-sha',default='05a3d348d53767e6e0bcc85f20f0c02ba6f68ea62e6e10619e8b38d1cbf5b544')
parser.add_argument('--full',action='store_true',help='Write a standalone full compressed program package')
parser.add_argument('--metadata-output',type=Path,default=LOCAL/'runtime-update.json')
args=parser.parse_args()
if not re.fullmatch(r'[0-9a-f]{64}',args.base_sha):parser.error('Invalid base SHA')
if not re.fullmatch(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)',args.version):parser.error('Use a version such as 0.1.1')
filename=f'ra2-web-v{args.version}'+('-full' if args.full else '')+'.ra2update'
old_sha = args.base_sha
old_path = LOCAL / 'artifacts' / old_sha / 'ra2-web.wasm'
new_path = ROOT / '.local/web-build/ra2-web.wasm'
patch = subprocess.run(['git', 'diff', '--no-index', '--binary', '--', str(old_path), str(new_path)], capture_output=True, check=False)
if patch.returncode != 1:
    raise SystemExit('Expected a binary difference')
lines = patch.stdout.split(b'GIT binary patch\n', 1)[1].splitlines()
mode='delta' if lines[0].startswith(b'delta ') else 'wasm'
if not lines[0].startswith((b'delta ',b'literal ')):
    raise SystemExit('Git did not produce a supported update')
alphabet = b'0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz!#$%&()*+-;<=>?@^_`{|}~'
compressed = bytearray()
for line in lines[1:]:
    if not line:
        break
    length = line[0] - 65 + 1 if line[0] <= 90 else line[0] - 97 + 27
    decoded = bytearray()
    for offset in range(1, len(line), 5):
        value = 0
        for char in line[offset:offset+5]:
            value = value * 85 + alphabet.index(char)
        decoded.extend(value.to_bytes(4, 'big'))
    compressed.extend(decoded[:length])
delta = zlib.decompress(compressed)
old = old_path.read_bytes()
new = new_path.read_bytes()
if args.full:
    mode='wasm';delta=new;compressed=zlib.compress(new)
if mode=='wasm':
    assert delta==new
else:
    position = 0
    def integer():
        global position
        value = shift = 0
        while True:
            byte = delta[position]; position += 1
            value |= (byte & 127) << shift
            if not byte & 128:
                return value
            shift += 7
    assert integer() == len(old) and integer() == len(new)
    result = bytearray()
    while position < len(delta):
        command = delta[position]; position += 1
        if command & 128:
            offset = size = 0
            for bit in range(7):
                if command & (1 << bit):
                    value = delta[position]; position += 1
                    if bit < 4: offset |= value << (8 * bit)
                    else: size |= value << (8 * (bit - 4))
            size = size or 65536
            result.extend(old[offset:offset+size])
        else:
            assert command
            result.extend(delta[position:position+command]); position += command
    assert result == new
baseline_sha='05a3d348d53767e6e0bcc85f20f0c02ba6f68ea62e6e10619e8b38d1cbf5b544'
baseline_path=LOCAL/'artifacts'/baseline_sha/'ra2-web.wasm'
metadata = {'resourcePrograms':[{'sha256':baseline_sha,'size':baseline_path.stat().st_size}], 'version':args.version,'mode':mode,'from': old_sha, 'to': hashlib.sha256(new).hexdigest(), 'sourceSize': len(old), 'size': len(new), 'deltaBytes':len(delta),'chunks': [hashlib.sha256(new[i:i+16*1024*1024]).hexdigest() for i in range(0, len(new), 16*1024*1024)]}
header = json.dumps(metadata, separators=(',', ':')).encode()
bundle=b'RA2UPDT1' + struct.pack('<I', len(header)) + header + compressed
target=LOCAL/filename
if target.exists():
    previous=target.read_bytes()
    previous_header=json.loads(previous[12:12+struct.unpack('<I',previous[8:12])[0]])
    if previous_header['to']!=metadata['to']:raise SystemExit('This version already exists for another program. Increase --version.')
target.write_bytes(bundle)
args.metadata_output.write_text(json.dumps({**metadata, 'url': filename,'downloadBytes':len(bundle)}))
(ROOT/'web/runtime-release.json').write_text(json.dumps({'version':args.version,'sha256':metadata['to']},indent=2)+'\n')
print('Verified runtime delta:', len(compressed), 'bytes')
