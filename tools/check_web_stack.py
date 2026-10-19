#!/usr/bin/env python3
"""Measure Wasm locals and optionally retain only large-frame body changes."""
import argparse
import json
from pathlib import Path

def number(data, offset):
    value = shift = 0
    while True:
        byte = data[offset]; offset += 1
        value |= (byte & 127) << shift
        if not byte & 128:
            return value, offset
        shift += 7

def encode(value):
    result = bytearray()
    while value >= 128:
        result.append((value & 127) | 128); value >>= 7
    result.append(value)
    return bytes(result)

def sections(data):
    offset = 8
    result = []
    while offset < len(data):
        kind = data[offset]; offset += 1
        length, offset = number(data, offset)
        result.append((kind, data[offset:offset+length]))
        offset += length
    return result

def bodies(items):
    data = next(data for kind, data in items if kind == 10)
    count, offset = number(data, 0)
    result = []
    for _ in range(count):
        length, offset = number(data, offset)
        result.append(data[offset:offset+length]); offset += length
    return result

def locals_count(body):
    count, offset = number(body, 0)
    total = 0
    for _ in range(count):
        length, offset = number(body, offset)
        total += length; offset += 1
    return total

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('original', type=Path)
    parser.add_argument('optimized', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    original = args.original.read_bytes()
    old_sections, new_sections = sections(original), sections(args.optimized.read_bytes())
    old_bodies, new_bodies = bodies(old_sections), bodies(new_sections)
    assert len(old_bodies) == len(new_bodies)
    before = [locals_count(body) for body in old_bodies]
    after = [locals_count(body) for body in new_bodies]
    compatible = ([(kind, data) for kind, data in old_sections if kind not in (0, 10)] ==
                  [(kind, data) for kind, data in new_sections if kind not in (0, 10)])
    report = {'functions': len(before), 'max_locals_before': max(before), 'max_locals_after': max(after),
              'large_frames_before': sum(n > 512 for n in before), 'large_frames_after': sum(n > 512 for n in after),
              'unchanged_non_code_sections': compatible}
    if args.output:
        assert compatible, 'Cannot splice bodies after import/type/global layout changes'
        selected = [new if count > 512 else old for old, new, count in zip(old_bodies, new_bodies, before)]
        code = encode(len(selected)) + b''.join(encode(len(body)) + body for body in selected)
        result = original[:8] + b''.join(bytes([kind]) + encode(len(code if kind == 10 else data)) + (code if kind == 10 else data) for kind, data in old_sections)
        args.output.write_bytes(result)
        report['output_bytes'] = len(result)
    print(json.dumps(report))
