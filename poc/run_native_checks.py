#!/usr/bin/env python3
"""Reproducible ARM64 investigation. No proprietary game files required.

Unicorn is the x86 reference only. The tested C executes as ARM64 machine code.
All bridge bytes below are original synthetic fixtures, not RA2 functions.
"""
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shlex
import struct
import subprocess
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
KIT = ROOT / 'vendor/pcrecomp'
OUT = ROOT / 'poc/generated'
LOG = ROOT / 'logs'
OUT.mkdir(exist_ok=True)
LOG.mkdir(exist_ok=True)
sys.path.insert(0, str(KIT / 'tools/lift'))
import difftest as dt
from generate import linear_disassemble_function, lift_function_linear
from lift32 import Lifter
from capstone import Cs, CS_ARCH_X86, CS_MODE_32
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn import x86_const as X


def command(args, name, expected=None):
    args = [str(x) for x in args]
    proc = subprocess.run(args, cwd=ROOT, capture_output=True, text=True)
    (LOG / name).write_text('$ ' + shlex.join(args) + '\n' + proc.stdout
                            + proc.stderr + f'\nexit_code={proc.returncode}\n')
    if expected is not None and proc.returncode != expected:
        raise RuntimeError(f'{name}: exit {proc.returncode}; inspect log')
    return proc


def compile_c(sources, output, opt='-O2', extra=()):
    command(['/usr/bin/clang', '-arch', 'arm64', opt, '-g',
             '-fno-strict-aliasing', '-fwrapv', '-ffp-contract=off',
             '-I', KIT / 'runtime/recomp32', *extra, *sources, '-o', output],
            output.name + '-compile.log', expected=0)


def upstream_diff():
    """Use upstream cases and comparison policy without altering its sources."""
    src = OUT / 'upstream_cases.c'
    src.write_text(dt.build_c(dt.CASES))
    references = [dt.run_unicorn(case) for case in dt.CASES]
    results = {}
    for opt in ('-O0', '-O2'):
        binary = OUT / ('upstream_cases_' + opt[1:])
        compile_c([src], binary, opt)
        run = command([binary], binary.name + '-execution.log', expected=0)
        states = dt.parse_output(run.stdout)
        if len(states) != len(dt.CASES):
            raise RuntimeError('upstream case count mismatch')
        failures, known = [], []
        for case, got, want in zip(dt.CASES, states, references):
            delta = dt.diff(case, got, want)
            if delta:
                (known if case.known else failures).append(
                    {'name': case.name, 'differences': delta, 'note': case.known})
        results[opt] = {'total': len(states),
                        'matched': len(states) - len(failures) - len(known),
                        'known': known, 'failures': failures}
        command(['/usr/bin/file', binary], binary.name + '-file.log', expected=0)
    return results


# Original x86 fixtures: virtual thiscall -> native stdcall shim -> guest callback.
FIXTURES = {
    0x00401000: bytes.fromhex('6a07 8b01 ff10 50 ff15 00034300 c3'),
    0x00401100: bytes.fromhex('8b4104 03442404 894108 c20400'),
    0x00401200: bytes.fromhex('8b442404 8d0440 c20400'),
    # Reference-only x86 stand-in for the native shim, calls 0x00401200.
    0x00401300: bytes.fromhex('8b442404 50 e8 f6feffff c20400'),
}


def reference_bridge(value):
    mu = Uc(UC_ARCH_X86, UC_MODE_32)
    mu.mem_map(0x00400000, 0x40000)
    for va, code in FIXTURES.items():
        mu.mem_write(va, code)
    for va, data in {0x00430100: 0x00430200, 0x00430104: value,
                     0x00430200: 0x00401100, 0x00430300: 0x00401300,
                     0x00420000: 0x00403000}.items():
        mu.mem_write(va, struct.pack('<I', data))
    mu.reg_write(X.UC_X86_REG_ESP, 0x00420000)
    mu.reg_write(X.UC_X86_REG_ECX, 0x00430100)
    counts = {'shim_calls': 0, 'callback_calls': 0}

    def hook(_mu, address, _size, _user):
        if address == 0x00401300:
            counts['shim_calls'] += 1
        if address == 0x00401200:
            counts['callback_calls'] += 1

    mu.hook_add(UC_HOOK_CODE, hook)
    mu.emu_start(0x00401000, 0x00403000, count=100)
    if mu.reg_read(X.UC_X86_REG_EIP) != 0x00403000:
        raise RuntimeError('reference did not return')
    return {'eax': mu.reg_read(X.UC_X86_REG_EAX),
            'esp': mu.reg_read(X.UC_X86_REG_ESP),
            'object_result': struct.unpack('<I', mu.mem_read(0x00430108, 4))[0],
            **counts}


def bridge():
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    md.detail = True
    bodies = ['#define RECOMP_GENERATED_CODE\n#include "recomp_types.h"\n']
    for va in (0x00401000, 0x00401100, 0x00401200):
        code = FIXTURES[va]
        instructions, leaders = linear_disassemble_function(md, code, va, va, va + len(code))
        bodies.append(lift_function_linear(Lifter(iat_map={}), f'sub_{va:08X}',
                                           instructions, leaders, va))
    src = OUT / 'synthetic_bridge.c'
    src.write_text('\n'.join(bodies))
    results = []
    for local in (False, True):
        binary = OUT / ('bridge_local' if local else 'bridge_global')
        extra = ['-DRECOMP_LOCAL_REGS'] if local else []
        compile_c([src, ROOT / 'poc/bridge_host.c'], binary, extra=extra)
        command(['/usr/bin/file', binary], binary.name + '-file.log', expected=0)
        for value in (0, 1, 12345, 0x7fffffff, 0xfffffff9, 0xffffffff):
            expected = reference_bridge(value)
            run = command([binary, hex(value)], f'{binary.name}-{value:x}.log', expected=0)
            actual = json.loads(run.stdout)
            delta = {key: (actual.get(key), val) for key, val in expected.items()
                     if actual.get(key) != val}
            if not actual.get('host_above_4g'):
                delta['host_above_4g'] = False
            results.append({'local_registers': local, 'input': value,
                            'actual': actual, 'expected': expected,
                            'passed': not delta, 'differences': delta})
    return results


def main():
    if platform.system() != 'Darwin' or platform.machine() != 'arm64':
        raise SystemExit('This experiment requires an ARM64 macOS host.')
    metadata = {'date': datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
                'platform': platform.platform(), 'machine': platform.machine(),
                'python': sys.version, 'game_files_provided': False,
                'packages': {name: importlib.metadata.version(name)
                             for name in ('capstone', 'pefile', 'unicorn', 'cmake', 'ninja')},
                'commits': {name: subprocess.check_output(
                    ['git', '-C', str(ROOT / 'vendor' / name), 'rev-parse', 'HEAD'],
                    text=True).strip() for name in ('redalert2-recomp', 'pcrecomp')}}
    (LOG / 'environment.json').write_text(json.dumps(metadata, indent=2) + '\n')
    binary = OUT / 'platform_probe'
    compile_c([ROOT / 'poc/platform_probe.c'], binary)
    platform_result = command([binary], 'platform-probe.log', expected=0)
    command(['/usr/bin/otool', '-l', binary], 'platform-probe-load-commands.log', expected=0)
    result = {'scope': 'Synthetic ARM64 feasibility only; no actual RA2/YR game function tested.',
              'platform_probe': platform_result.stdout,
              'upstream_differential': upstream_diff(), 'synthetic_bridge': bridge()}
    (LOG / 'native-results.json').write_text(json.dumps(result, indent=2) + '\n')
    print(platform_result.stdout, end='')
    for opt, item in result['upstream_differential'].items():
        print(f"upstream {opt}: {item['matched']}/{item['total']} match; failures={len(item['failures'])}")
    passed = sum(item['passed'] for item in result['synthetic_bridge'])
    print(f'synthetic bridge: {passed}/{len(result["synthetic_bridge"])} passed')
    # Any reference mismatch stays visible as a failing exit code.
    return int(any(item['failures'] for item in result['upstream_differential'].values())
               or any(not item['passed'] for item in result['synthetic_bridge']))


if __name__ == '__main__':
    sys.exit(main())
