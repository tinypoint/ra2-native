#!/usr/bin/env python3
"""Preserve pthread error details instead of throwing an opaque ErrorEvent."""
from pathlib import Path

def patch(path):
    text = path.read_text()
    old = '''      err(`${message} ${e.filename}:${e.lineno}: ${e.message}`);
      throw e;'''
    new = '''      var detail = e.error?.stack || e.error?.message || e.message || "browser worker terminated without details";
      var fullMessage = `${message} ${e.filename || "worker"}:${e.lineno || 0}:${e.colno || 0}: ${detail}`;
      err(fullMessage);
      if (typeof Module["onThreadError"] === "function") Module["onThreadError"](fullMessage);
      throw new Error(fullMessage);'''
    if old in text:
        path.write_text(text.replace(old, new, 1))
    elif 'browser worker terminated without details' not in text:
        raise RuntimeError('Emscripten worker error handler changed; inspect before patching')

if __name__ == '__main__':
    patch(Path(__file__).resolve().parents[1] / '.local/web-build/ra2-web.js')
