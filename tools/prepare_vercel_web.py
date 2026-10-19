#!/usr/bin/env python3
"""Stage a small static Vercel deployment, keeping original assets local-only."""
import hashlib
import json
import argparse
import re
from pathlib import Path
import shutil
import struct
import tempfile
import zlib

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / '.local/web-preview'
OUTPUT = ROOT / '.local/vercel-site'


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def read_header(source, magic, limit):
    prefix = source.read(12)
    if len(prefix) != 12 or prefix[:8] != magic:
        raise ValueError('Invalid package signature')
    length = struct.unpack('<I', prefix[8:])[0]
    if not 0 < length <= limit:
        raise ValueError('Invalid package header size')
    return json.loads(source.read(length))


def prepare(resources_repository=None):
    if resources_repository and not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', resources_repository):
        raise ValueError('Use a GitHub repository in owner/repo form')
    release = json.loads((ROOT / 'web/runtime-release.json').read_text())
    offer = json.loads((LOCAL / 'runtime-update.json').read_text())
    if offer['version'] != release['version'] or offer['to'] != release['sha256']:
        raise ValueError('Published program and version metadata differ')
    full = offer if offer['mode'] == 'wasm' else offer['fallback']
    if full['mode'] != 'wasm' or full['to'] != offer['to']:
        raise ValueError('A complete compressed program is required')
    wasm = ROOT / '.local/web-published/ra2-web.wasm'
    if digest(wasm) != offer['to']:
        raise ValueError('Published Wasm differs from update package')
    with (LOCAL / 'resource-pack.ra2pack').open('rb') as source:
        pack = read_header(source, b'RA2PACK1', 1024 * 1024)
    if pack['version'] != 1 or pack['files'][0]['name'] != 'ra2-web.wasm':
        raise ValueError('Unexpected original resource pack layout')

    def copy_update(metadata, stage):
        source = LOCAL / Path(metadata['url']).name
        if source.stat().st_size != metadata['downloadBytes']:
            raise ValueError('Update download size differs from manifest')
        with source.open('rb') as stream:
            header = read_header(stream, b'RA2UPDT1', 65536)
            for key in ('mode', 'from', 'to', 'size', 'sourceSize', 'chunks'):
                if header[key] != metadata[key]:
                    raise ValueError('Update package header mismatch: ' + key)
            if header['mode'] == 'wasm':
                decompressor = zlib.decompressobj()
                h, count = hashlib.sha256(), 0
                while block := stream.read(64 * 1024):
                    expanded = decompressor.decompress(block)
                    h.update(expanded)
                    count += len(expanded)
                expanded = decompressor.flush()
                h.update(expanded)
                count += len(expanded)
                if not decompressor.eof or decompressor.unused_data or count != metadata['size'] or h.hexdigest() != metadata['to']:
                    raise ValueError('Complete program failed decompression/hash check')
        url = 'updates/' + digest(source) + '/' + source.name
        target = stage / url
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return {**metadata, 'url': url}

    with tempfile.TemporaryDirectory(prefix='vercel-stage-', dir=ROOT / '.local') as directory:
        stage = Path(directory)
        for name in ('index.html', 'style.css', 'app.js', 'frame-meter.js', 'runtime-update.js'):
            shutil.copy2(ROOT / 'web' / name, stage / name)
        js = ROOT / '.local/web-published/ra2-web.js'
        script = {'name': js.name, 'size': js.stat().st_size, 'sha256': digest(js)}
        script['url'] = 'artifact/' + script['sha256'] + '/' + js.name
        target = stage / script['url']
        target.parent.mkdir(parents=True)
        shutil.copy2(js, target)
        program = {'name': 'ra2-web.wasm', 'size': offer['size'], 'sha256': offer['to'],
                   'url': 'local-import-only/ra2-web.wasm', 'localOnly': True}
        update = copy_update(offer, stage)
        if offer['mode'] != 'wasm':
            update['fallback'] = copy_update(full, stage)
        files = [{**{key: item[key] for key in ('name', 'size', 'sha256')},
                  'localOnly': True} for item in pack['files'][1:]]
        resources = None
        if resources_repository:
            resources = json.loads((ROOT / '.local/github-resources/manifest.json').read_text())
            if resources['chunkSize'] != 16 * 1024 * 1024:
                raise ValueError('Resource chunk size differs from browser cache format')
            if [{key: f[key] for key in ('name', 'size', 'sha256')} for f in resources['files']] != [{key: f[key] for key in ('name', 'size', 'sha256')} for f in files]:
                raise ValueError('Release resources differ from the original import pack')
            files = resources['files']
        baseline = pack['files'][0]
        for item in (update, update.get('fallback')):
            if item is None:
                continue
            allowed = item.setdefault('resourcePrograms', [])
            if not any(old['sha256'] == baseline['sha256'] for old in allowed):
                allowed.append({key: baseline[key] for key in ('sha256', 'size')})
        manifest = {'ready': True, 'resourceMode': 'github-releases' if resources else 'local-import', 'diagnostics': False,
                    'files': files, 'script': script,
                    'artifacts': {'ra2-web.js': script, 'ra2-web.wasm': program},
                    'programUpdate': update}
        config = json.loads((ROOT / 'deploy/vercel/vercel.json').read_text())
        if resources:
            manifest['resourcesRelease'] = {'repository': resources_repository, 'tag': resources['releaseTag'], 'viaVercel': True}
            config['rewrites'] = [{'source': '/resources/:chunk([a-f0-9]{64}).bin',
                                   'destination': f'https://github.com/{resources_repository}/releases/download/{resources["releaseTag"]}/:chunk.bin'}]
            config['headers'].append({'source': '/resources/(.*)', 'headers': [{'key': 'Cache-Control', 'value': 'public, max-age=31536000, immutable'}]})
        (stage / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
        (stage / 'vercel.json').write_text(json.dumps(config, indent=2) + '\n')
        (stage / '.vercelignore').write_text('README.md\nverification.json\n')
        deployed = [p for p in stage.rglob('*') if p.is_file()]
        total = sum(p.stat().st_size for p in deployed)
        if total >= 100 * 1024 * 1024:
            raise ValueError('Static upload exceeds the 100 MiB preparation budget')
        if any(p.suffix.lower() in {'.mix', '.exe', '.dll', '.ra2pack', '.wasm'} for p in deployed):
            raise ValueError('Unexpected original asset or uncompressed Wasm in deployment')
        if OUTPUT.exists():
            # Preserve only CLI project association; upload files are rebuilt fresh.
            if (OUTPUT / '.vercel').exists():
                shutil.copytree(OUTPUT / '.vercel', stage / '.vercel')
            shutil.rmtree(OUTPUT)
        OUTPUT.mkdir()
        for source in stage.iterdir():
            shutil.move(str(source), OUTPUT / source.name)
    result = {'version': offer['version'], 'deploymentBytes': total, 'fileCount': len(deployed),
              'originalAssetsIncluded': False, 'completeProgramVerified': True,
              'resourceMode': manifest['resourceMode'], 'deployed': False, 'output': str(OUTPUT)}
    (ROOT / 'logs/web-vercel-preparation.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--resources-repository', help='Public GitHub owner/repo containing prepared resource release assets')
    prepare(parser.parse_args().resources_repository)
