#!/usr/bin/env python3
"""Resume public Vercel Blob uploads; credentials remain in ignored local files."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import time
import subprocess
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def upload():
    access = ROOT / '.local/web-access'
    token = json.loads((access / 'vercel-blob-auth.json').read_text())['token']
    index = json.loads((ROOT / '.local/blob-assets/index.json').read_text())
    journal = ROOT / '.local/blob-assets/uploaded.json'
    done = json.loads(journal.read_text()) if journal.exists() else {}
    first = json.loads((access / 'vercel-blob-first-upload.json').read_text())
    done[first['pathname']] = first['url']
    jobs = [job for job in index['jobs'] if job['pathname'] not in done]
    jobs.sort(key=lambda job: (not job['pathname'].startswith('program/'), job['size']))
    print('Uploading', len(jobs), 'objects;', sum(j['size'] for j in jobs), 'bytes', flush=True)

    def put(job):
        data = (ROOT / job['path']).read_bytes()
        url = 'https://vercel.com/api/blob/?' + urllib.parse.urlencode({'pathname': job['pathname']})
        headers = {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/octet-stream',
                   'x-api-version': '12', 'x-vercel-blob-access': 'public', 'x-add-random-suffix': '0',
                   'x-allow-overwrite': '1', 'x-content-type': 'application/octet-stream', 'x-cache-control-max-age': '31536000',
                   'x-content-length': str(len(data)), 'User-Agent': 'node'}
        for attempt in range(3):
            try:
                config = ''.join('header = ' + json.dumps(key + ': ' + value) + '\n' for key, value in headers.items())
                response = subprocess.run(['curl', '--config', '-', '--http1.1', '--no-progress-meter',
                    '--connect-timeout', '10', '--max-time', '75', '--limit-rate', '128k',
                    '--upload-file', str(ROOT / job['path']), url], input=config, text=True, capture_output=True)
                if response.returncode:
                    raise TimeoutError('Upload connection interrupted')
                result = json.loads(response.stdout)
                if 'url' not in result:
                    raise ValueError(str(result.get('error', 'Blob upload rejected'))[:150])
                if result['url'] != index['baseUrl'] + job['pathname']:
                    raise ValueError('Unexpected uploaded Blob URL')
                return job['pathname'], result['url']
            except Exception as error:
                reason = type(error).__name__
                if isinstance(error, urllib.error.HTTPError):
                    reason += ':' + str(error.code)
                    raw = error.read().decode(errors='replace')
                    try:
                        info = json.loads(raw);reason += ':' + str(info.get('error', info))[:200]
                    except ValueError:
                        reason += ':non-JSON response'
                if attempt == 0:
                    print('Retry', job['pathname'], reason, flush=True)
                if attempt == 2:
                    raise RuntimeError('Upload failed: ' + job['pathname']) from None
                time.sleep(3 * (attempt + 1))

    errors = []
    with ThreadPoolExecutor(max_workers=16) as pool:
        futures = [pool.submit(put, job) for job in jobs]
        for future in as_completed(futures):
            try:
                pathname, url = future.result()
                done[pathname] = url
                temporary = journal.with_suffix('.tmp')
                temporary.write_text(json.dumps(done))
                temporary.replace(journal)
                if len(done) % 10 == 0:
                    print('Uploaded', len(done), '/', len(index['jobs']), flush=True)
            except Exception as error:
                errors.append(str(error))
                print(str(error), flush=True)
    print('Complete:', len(done), '/', len(index['jobs']), '; errors:', len(errors), flush=True)
    if errors:
        raise SystemExit(1)


if __name__ == '__main__':
    upload()
