#!/usr/bin/env python3
"""Prepare compressed public Blob downloads without changing cache identities."""
import hashlib
import json
from pathlib import Path
import zlib

ROOT = Path(__file__).resolve().parents[1]


def prepare():
    first = json.loads((ROOT / '.local/web-access/vercel-blob-first-upload.json').read_text())
    base = first['url'].split('/program/')[0] + '/'
    resources = json.loads((ROOT / '.local/github-resources/manifest.json').read_text())
    output = ROOT / '.local/blob-assets'
    jobs = {}
    for file in resources['files']:
        for group in file['chunkParts']:
            for part in group:
                sha = part['sha256']
                raw = (ROOT / '.local/github-resources/parts' / (sha + '.bin')).read_bytes()
                packed = zlib.compress(raw, 1)
                compressed = len(packed) < len(raw) * .96
                name = 'resources/' + sha + ('.bin.deflate' if compressed else '.bin')
                target = output / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(packed if compressed else raw)
                part['url'] = base + name
                if compressed:
                    part['compression'] = 'deflate'
                part['wireSize'] = target.stat().st_size
                jobs[name] = {'pathname': name, 'path': str(target.relative_to(ROOT)), 'size': target.stat().st_size}
    for source in (ROOT / '.local/github-runtime').glob('*.bin'):
        name = 'program/' + source.name
        jobs[name] = {'pathname': name, 'path': str(source.relative_to(ROOT)), 'size': source.stat().st_size}
    index = {'baseUrl': base, 'files': resources['files'], 'jobs': list(jobs.values())}
    (output / 'index.json').write_text(json.dumps(index, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'files': len(resources['files']), 'objects': len(jobs), 'uploadBytes': sum(j['size'] for j in jobs.values()), 'baseUrl': base}))


if __name__ == '__main__':
    prepare()
