#!/usr/bin/env python3
"""Upload only the prepared static site through Vercel's deployment API."""
import hashlib
import json
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
ACCESS = ROOT / '.local/web-access'
SITE = ROOT / '.local/vercel-site'


def deploy():
    token = json.loads((ACCESS / 'vercel-auth.json').read_text())['access_token']
    project = json.loads((ACCESS / 'vercel-project.json').read_text())['project']
    query = '?' + urllib.parse.urlencode({'teamId': project['orgId']})

    def request(path, data, extra=None):
        headers = {'Authorization': 'Bearer ' + token, **(extra or {})}
        try:
            with urllib.request.urlopen(urllib.request.Request('https://api.vercel.com' + path + query, data=data, headers=headers), timeout=180) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            message = json.loads(error.read()).get('error', {})
            raise RuntimeError(str(error.code) + ' ' + str(message.get('message', message.get('code', 'API error')))) from None

    files = []
    for source in sorted(SITE.rglob('*')):
        relative = source.relative_to(SITE)
        if not source.is_file() or any(part.startswith('.') for part in relative.parts):
            continue
        if relative.name in {'README.md', 'verification.json'}:
            continue
        data = source.read_bytes()
        sha = hashlib.sha1(data).hexdigest()
        request('/v2/files', data, {'Content-Type': 'application/octet-stream', 'x-now-digest': sha, 'x-now-size': str(len(data))})
        files.append({'file': relative.as_posix(), 'sha': sha, 'size': len(data)})
        print('Uploaded', relative.as_posix(), len(data), flush=True)
    config = json.loads((SITE / 'vercel.json').read_text())
    body = {'name': project['projectName'], 'project': project['projectId'], 'target': 'production', 'files': files,
            'projectSettings': {key: config[key] for key in ('framework', 'buildCommand', 'installCommand', 'outputDirectory')}}
    body.update({key: config[key] for key in ('headers', 'redirects', 'rewrites') if key in config})
    result = request('/v13/deployments', json.dumps(body).encode(), {'Content-Type': 'application/json'})
    (ACCESS / 'vercel-deployment.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: result.get(key) for key in ('id', 'url', 'readyState', 'alias')}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    deploy()
