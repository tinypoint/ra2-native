#!/usr/bin/env python3
"""Prepare content-addressed release assets, without uploading anything."""
import hashlib
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / '.local/github-resources'
CHUNK = 16 * 1024 * 1024


def prepare():
    chunks = OUTPUT / 'chunks'
    chunks.mkdir(parents=True, exist_ok=True)
    files, sizes = [], {}
    with (ROOT / '.local/web-preview/resource-pack.ra2pack').open('rb') as source:
        prefix = source.read(12)
        assert prefix[:8] == b'RA2PACK1'
        length = struct.unpack('<I', prefix[8:])[0]
        assert 0 < length <= 1024 * 1024
        pack = json.loads(source.read(length))
        assert pack['version'] == 1 and pack['files'][0]['name'] == 'ra2-web.wasm'
        source.seek(pack['files'][0]['size'], 1)
        for entry in pack['files'][1:]:
            total, whole, hashes = 0, hashlib.sha256(), []
            for expected in entry['chunks']:
                block = source.read(min(CHUNK, entry['size'] - total))
                actual = hashlib.sha256(block).hexdigest()
                if actual != expected:
                    raise ValueError('Resource chunk failed verification: ' + entry['name'])
                whole.update(block)
                total += len(block)
                hashes.append(actual)
                target = chunks / (actual + '.bin')
                if not target.exists() or hashlib.sha256(target.read_bytes()).hexdigest() != actual:
                    target.write_bytes(block)
                sizes[actual] = len(block)
            if total != entry['size'] or whole.hexdigest() != entry['sha256']:
                raise ValueError('Resource file failed verification: ' + entry['name'])
            files.append({**{key: entry[key] for key in ('name', 'size', 'sha256')},
                          'chunkHashes': hashes,
                          'chunkUrls': ['resources/' + value + '.bin' for value in hashes]})
        if source.read(1):
            raise ValueError('Unexpected trailing resource data')
    identity = hashlib.sha256(json.dumps(files, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    manifest = {'releaseTag': 'resources-' + identity[:16], 'resourceSet': identity,
                'chunkSize': CHUNK, 'files': files,
                'assets': [{'name': value + '.bin', 'size': sizes[value], 'sha256': value} for value in sorted(sizes)]}
    (OUTPUT / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'releaseTag': manifest['releaseTag'], 'files': len(files),
                      'releaseAssets': len(sizes), 'downloadBytes': sum(sizes.values()),
                      'uploaded': False, 'output': str(OUTPUT)}, ensure_ascii=False))


if __name__ == '__main__':
    prepare()
