#!/usr/bin/env python3
"""Build a local import bundle without loading the game into memory."""
import hashlib
import json
from pathlib import Path
import shutil
import struct
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / '.local/web-preview'
token = (LOCAL / 'access-token').read_text().strip()
with urllib.request.urlopen(f'http://127.0.0.1:8767/{token}/manifest.json') as response:
    manifest = json.load(response)
entries = []
paths = []
for item in [manifest['artifacts']['ra2-web.wasm'], *manifest['files']]:
    path = (LOCAL / 'artifacts' / item['sha256'] / item['name']
            if item['name'] == 'ra2-web.wasm'
            else ROOT / 'game/ra2-upload-41bbcc83' / item['name'])
    hashes = []
    with path.open('rb') as source:
        for block in iter(lambda: source.read(16 * 1024 * 1024), b''):
            hashes.append(hashlib.sha256(block).hexdigest())
    entries.append({**item, 'chunks': hashes})
    paths.append(path)
header = json.dumps({'version': 1, 'files': entries}, separators=(',', ':')).encode()
temporary = LOCAL / 'resource-pack.tmp'
with temporary.open('wb') as output:
    output.write(b'RA2PACK1' + struct.pack('<I', len(header)) + header)
    for path in paths:
        with path.open('rb') as source:
            shutil.copyfileobj(source, output, 1024 * 1024)
temporary.replace(LOCAL / 'resource-pack.ra2pack')
print('Resource pack ready:', (LOCAL / 'resource-pack.ra2pack').stat().st_size, 'bytes')
