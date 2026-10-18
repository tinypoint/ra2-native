#!/usr/bin/env python3
"""Temporary LAN file drop; Python 3.9 stdlib, no automatic extraction."""
import cgi
import html
import json
import os
from pathlib import Path
import secrets
import shutil
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'incoming'
STATE = ROOT / '.local/upload-state.json'
TOKEN = secrets.token_urlsafe(18)
ROUTE = '/' + TOKEN
MAX_SIZE = 12 * 1024**3
DEST.mkdir(exist_ok=True)


class Handler(BaseHTTPRequestHandler):
    def reply(self, status, body):
        data = body.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if urlsplit(self.path).path.rstrip('/') != ROUTE:
            return self.reply(404, 'Not found')
        self.reply(200, '''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>文件传到 Mac</title><style>body{font:18px system-ui;max-width:620px;margin:50px auto;padding:24px;background:#f5f6f8;color:#18202b}input,button{font-size:18px;margin:18px 0;max-width:100%}button{padding:14px 28px;background:#165ee8;color:white;border:0;border-radius:10px}p{line-height:1.7}</style>
<h1>文件传到 Mac</h1><p>选择手机中的文件，然后点上传。支持 ZIP、7z 等文件，可一次选择多个。</p>
<form method="post" enctype="multipart/form-data"><input type="file" name="files" multiple required><br><button type="submit">开始上传</button></form>
<p>上传时请保持页面打开，完成后会显示接收结果。</p></html>''')

    def do_POST(self):
        if urlsplit(self.path).path.rstrip('/') != ROUTE:
            return self.reply(404, 'Not found')
        try:
            length = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            return self.reply(400, 'Invalid length')
        if length <= 0 or length > MAX_SIZE:
            return self.reply(413, '请选择总大小小于 12 GiB 的文件')
        if not self.headers.get('Content-Type', '').startswith('multipart/form-data'):
            return self.reply(400, 'Invalid upload')
        form = cgi.FieldStorage(fp=self.rfile, headers=self.headers,
                                environ={'REQUEST_METHOD': 'POST',
                                         'CONTENT_TYPE': self.headers['Content-Type'],
                                         'CONTENT_LENGTH': str(length)},
                                keep_blank_values=True)
        saved = []
        for item in form.list or []:
            if not item.filename:
                continue
            name = Path(item.filename.replace('\\', '/')).name
            if name in ('', '.', '..') or '\x00' in name:
                return self.reply(400, '文件名无效')
            target = DEST / name
            try:
                output = target.open('xb')
            except FileExistsError:
                target = DEST / (secrets.token_hex(4) + '-' + name)
                output = target.open('xb')
            try:
                with output:
                    shutil.copyfileobj(item.file, output, 1024 * 1024)
                saved.append((target.name, target.stat().st_size))
            except Exception:
                target.unlink(missing_ok=True)
                raise
        if not saved:
            return self.reply(400, '没有收到文件')
        rows = ''.join('<li>' + html.escape(name) + ' (' + str(size) + ' 字节)</li>'
                       for name, size in saved)
        print(json.dumps({'received': saved}, ensure_ascii=False), flush=True)
        self.reply(200, '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><h1>上传成功</h1><ul>' + rows + '</ul><p>文件已保存到 Mac。</p><a href="' + ROUTE + '">继续上传</a>')


if __name__ == '__main__':
    server = ThreadingHTTPServer(('0.0.0.0', 8765), Handler)
    STATE.write_text(json.dumps({'pid': os.getpid(), 'port': server.server_port,
                                 'route': ROUTE, 'destination': str(DEST)}))
    print('Upload server ready', flush=True)
    server.serve_forever()
