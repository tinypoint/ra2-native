#!/usr/bin/env python3
"""Lift actual RA2 functions and compare ARM64 execution to Unicorn x86.

Never executes the installer or launches the game. Locally generated code,
input states, mapped PE image, and binaries are ignored by Git.
"""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import shlex
import struct
import subprocess
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
KIT=ROOT/'vendor/pcrecomp'
OUT=ROOT/'poc/generated_game'
sys.path.insert(0,str(KIT/'tools/lift'))
from generate import linear_disassemble_function, lift_function_linear
from lift32 import Lifter
from capstone import Cs, CS_ARCH_X86, CS_MODE_32
import pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32
from unicorn import x86_const as X

EXPECTED_SHA='fe67fdac5073530a79baec14c4e072b5e7e4c0c462cee9659870c5330e9e6e3e'
BASE=0x00400000
SCRATCH=0x10000000
OBJECT=SCRATCH+0x1000
OUTPUT=SCRATCH+0x3000
ARRAY=SCRATCH+0x4000
TYPE=SCRATCH+0x5000
STACK=SCRATCH+0xf000
STOP=SCRATCH+0xff00
REGS=('eax','ecx','edx','ebx','esp','ebp','esi','edi')
REG_IDS=[getattr(X,'UC_X86_REG_'+r.upper()) for r in REGS]
FLAGS={'CF':0,'PF':2,'AF':4,'ZF':6,'SF':7,'DF':10,'OF':11}
# Selected through the uploaded executable's RTTI/vtables, not guessed bytes.
FUNCTIONS={
    0x005d4e40: ('UnitClass',18,'copy_three_coordinate_fields'),
    0x0041b320: ('UnitClass',104,'signed_coordinate_to_cell'),
    0x00453c70: ('BuildingClass',42,'coordinate_offset'),
    0x004cda80: ('FootClass',269,'reset_fields'),
    0x005950e0: ('TechnoClass',121,'compare_field_with_minus_one'),
    0x006c16d0: ('TechnoClass',None,'virtual_call_and_type_flag'),
    0x006c12c0: ('UnitClass',32,'virtual_tail_thunk'),
    0x00705020: ('UnitClass',33,'type_pointer_getter'),
    0x0058deb0: ('VectorClass@N',None,'double_element_getter'),
    0x006d3ea0: ('TechnoClass',None,'double_constant_getter'),
}


def command(args,log):
    args=[str(x) for x in args]
    p=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=60)
    (ROOT/'logs'/log).write_text('$ '+shlex.join(args)+'\n'+p.stdout+p.stderr+f'\nexit_code={p.returncode}\n')
    if p.returncode:
        raise RuntimeError(f'{log}: command failed ({p.returncode})')
    return p.stdout


def discover_functions(pe,image,rtti):
    md=Cs(CS_ARCH_X86,CS_MODE_32);md.detail=True
    bodies=[]; metadata=[]
    for va,(cls,slot,label) in FUNCTIONS.items():
        owner=rtti['classes'][cls]
        vt=int(owner['vtable'],16)
        if slot is None:
            slots=[i for i in range(owner['slots'])
                   if struct.unpack_from('<I',image,vt-BASE+i*4)[0]==va]
            if not slots: raise RuntimeError(f'{cls}: entry {va:x} not present in vtable')
            slot=slots[0]
        elif struct.unpack_from('<I',image,vt-BASE+slot*4)[0]!=va:
            raise RuntimeError(f'{cls} slot {slot}: unexpected address')
        decoded=[]
        for ins in md.disasm(image[va-BASE:va-BASE+160],va):
            decoded.append(ins)
            if ins.mnemonic.startswith('ret') or ins.mnemonic=='jmp':break
        if not decoded or not (decoded[-1].mnemonic.startswith('ret') or decoded[-1].mnemonic=='jmp'):
            raise RuntimeError('Could not establish bounded function extent')
        end=decoded[-1].address+decoded[-1].size
        instructions,leaders=linear_disassemble_function(md,image,BASE,va,end)
        lifter=Lifter(iat_map={},lifted=set(FUNCTIONS))
        body=lift_function_linear(lifter,f'sub_{va:08X}',instructions,leaders,va)
        if any(word in body for word in ('RECOMP_TODO','UNIMPLEMENTED')):
            raise RuntimeError('Unimplemented instruction in real function')
        bodies.append(body)
        metadata.append({'address':hex(va),'class':cls,'slot':slot,'vtable':hex(vt),
                         'description':label,'length':end-va,
                         'body_sha256':hashlib.sha256(image[va-BASE:end-BASE]).hexdigest()})
    header=['#pragma once','#include "recomp_types.h"']
    for va in FUNCTIONS:header.append(f'void sub_{va:08X}(void);')
    header.append('static const recomp_dispatch_entry_t game_functions[] = {')
    header += [f'{{0x{va:08X}u,sub_{va:08X}}},' for va in FUNCTIONS]
    header += ['};','#define GAME_FUNCTION_COUNT (sizeof(game_functions)/sizeof(game_functions[0]))']
    (OUT/'game_functions.h').write_text('\n'.join(header)+'\n')
    (OUT/'real_functions.c').write_text('#define RECOMP_GENERATED_CODE\n#include "game_functions.h"\n'+'\n\n'.join(bodies))
    return metadata


def cases(rtti):
    values=[0,1,255,256,0xffffffff,0xffffff00,0x7fffffff,0x80000000]
    for entry in (0x005d4e40,0x0041b320,0x00453c70,0x004cda80,0x005950e0,0x006c16d0):
        for value in values:
            mem=bytearray([0xa5])*0x10000
            def put(va,n):struct.pack_into('<I',mem,va-SCRATCH,n&0xffffffff)
            vt=int(rtti['classes']['UnitClass']['vtable'],16)
            put(OBJECT,vt);put(OBJECT+0x88,value);put(OBJECT+0x8c,(~value)&0xffffffff)
            put(OBJECT+0x90,value^0x12345678);put(OBJECT+0x9c,value)
            put(OBJECT+0x5ac,TYPE);mem[TYPE+0xad9-SCRATCH]=value&255
            put(STACK,STOP);put(STACK+4,OUTPUT)
            regs=[0x12345678,OBJECT,0x87654321,0x10203040,STACK,0x60708090,0x13579bdf,0x2468ace0]
            ignored={'AF'} if entry in (0x004cda80,0x006c16d0) else set()
            if entry==0x0041b320:ignored={'AF','OF'}
            yield {'name':f'{FUNCTIONS[entry][2]}_{value:08x}','entry':entry,
                   'regs':regs,'memory':mem,'ignored_flags':sorted(ignored),
                   'excluded_dead_return_slots':[STACK-4] if entry==0x006c16d0 else []}
    for i,value in enumerate((0.0,-0.0,1.5,-2.25,1e30,1e-30)):
        mem=bytearray([0xa5])*0x10000
        struct.pack_into('<I',mem,OBJECT+4-SCRATCH,ARRAY)
        struct.pack_into('<d',mem,ARRAY+i*8-SCRATCH,value)
        struct.pack_into('<II',mem,STACK-SCRATCH,STOP,i)
        yield {'name':f'double_element_{i}','entry':0x0058deb0,
               'regs':[0x12345678,OBJECT,0x87654321,0x10203040,STACK,0x60708090,0x13579bdf,0x2468ace0],
               'memory':mem,'ignored_flags':[],'excluded_dead_return_slots':[]}
    mem=bytearray([0xa5])*0x10000
    struct.pack_into('<I',mem,STACK-SCRATCH,STOP)
    yield {'name':'double_constant','entry':0x006d3ea0,
           'regs':[0x12345678,OBJECT,0x87654321,0x10203040,STACK,0x60708090,0x13579bdf,0x2468ace0],
           'memory':mem,'ignored_flags':[],'excluded_dead_return_slots':[]}


def reference(case,image):
    mu=Uc(UC_ARCH_X86,UC_MODE_32)
    mu.mem_map(BASE,(len(image)+4095)&~4095);mu.mem_write(BASE,image)
    mu.mem_map(SCRATCH,0x10000);mu.mem_write(SCRATCH,bytes(case['memory']))
    for reg,val in zip(REG_IDS,case['regs']):mu.reg_write(reg,val)
    mu.reg_write(X.UC_X86_REG_EFLAGS,0x202)
    mu.reg_write(X.UC_X86_REG_FPCW,0x027f)
    mu.emu_start(case['entry'],STOP,count=1000)
    if mu.reg_read(X.UC_X86_REG_EIP)!=STOP:raise RuntimeError('Reference did not return')
    regs=[mu.reg_read(r) for r in REG_IDS];flags=mu.reg_read(X.UC_X86_REG_EFLAGS)
    depth=(8-((mu.reg_read(X.UC_X86_REG_FPSW)>>11)&7))&7
    scratch=bytes(mu.mem_read(SCRATCH,0x10000))
    unchanged=int(bytes(mu.mem_read(BASE,len(image)))==image)
    bits=0
    if depth:
        drain=STOP+0x40
        # Reference-only fstp qword [OUTPUT]; no game instructions are modified.
        code=bytes.fromhex('dd1d')+struct.pack('<I',OUTPUT)
        mu.mem_write(drain,code);mu.emu_start(drain,drain+len(code),count=1)
        bits=struct.unpack('<Q',mu.mem_read(OUTPUT,8))[0]
    return {'regs':regs,'flags':flags,'depth':depth,'fp_bits':bits,
            'image_unchanged':unchanged,'memory':scratch}


def compare(case,got,want):
    delta=[]
    for i,name in enumerate(REGS):
        if got['regs'][i]!=want['regs'][i]:delta.append({'field':name,'native':hex(got['regs'][i]),'x86':hex(want['regs'][i])})
    for name,bit in FLAGS.items():
        if name not in case['ignored_flags'] and (got['flags']^want['flags'])&(1<<bit):
            delta.append({'field':name,'native':(got['flags']>>bit)&1,'x86':(want['flags']>>bit)&1})
    for name in ('depth','fp_bits','image_unchanged'):
        if got[name]!=want[name]:delta.append({'field':name,'native':got[name],'x86':want[name]})
    excluded={va+i-SCRATCH for va in case['excluded_dead_return_slots'] for i in range(4)}
    mismatches=[i for i,(a,b) in enumerate(zip(got['memory'],want['memory'])) if a!=b and i not in excluded]
    if mismatches:delta.append({'field':'memory','mismatched_bytes':len(mismatches),'first_addresses':[hex(SCRATCH+i) for i in mismatches[:16]]})
    if not got['host_above_4g']:delta.append({'field':'host_above_4g','native':False})
    return delta


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--exe',type=Path,default=ROOT/'game/ra2-upload-41bbcc83/game.exe');args=ap.parse_args()
    if platform.system()!='Darwin' or platform.machine()!='arm64':raise SystemExit('ARM64 macOS required')
    data=args.exe.read_bytes();sha=hashlib.sha256(data).hexdigest()
    if sha!=EXPECTED_SHA:raise SystemExit('Input differs from audited upload; audit before selecting addresses')
    OUT.mkdir(exist_ok=True)
    command([sys.executable,KIT/'tools/cpp/rtti.py',args.exe,'-o',OUT/'rtti.json',
             '--seeds',OUT/'rtti-seeds.json'],'real-game-rtti.log')
    rtti=json.loads((OUT/'rtti.json').read_text())
    pe=pefile.PE(data=data);image=pe.get_memory_mapped_image()
    (OUT/'pe_image.bin').write_bytes(image)
    selected=discover_functions(pe,image,rtti)
    all_cases=list(cases(rtti));refs=[reference(c,image) for c in all_cases]
    results=[]
    for local in (False,True):
        name='real_game_local' if local else 'real_game_global'
        binary=OUT/name
        command(['/usr/bin/clang','-arch','arm64','-O2','-g','-fno-strict-aliasing','-fwrapv','-ffp-contract=off',
                 '-I',KIT/'runtime/recomp32','-I',OUT,*(['-DRECOMP_LOCAL_REGS'] if local else []),
                 OUT/'real_functions.c',ROOT/'poc/real_game_host.c','-o',binary],name+'-compile.log')
        command(['/usr/bin/file',binary],name+'-file.log')
        for case,want in zip(all_cases,refs):
            inp=OUT/'case-input.bin';out=OUT/'case-output.bin'
            inp.write_bytes(struct.pack('<8I',*case['regs'])+case['memory'])
            command([binary,OUT/'pe_image.bin',inp,hex(case['entry']),out],name+'-last-execution.log')
            actual=out.read_bytes()
            if len(actual)!=56+0x10000:raise RuntimeError('Invalid native result size')
            fields=struct.unpack_from('<10IQII',actual)
            got={'regs':list(fields[:8]),'flags':fields[8],'depth':fields[9],'fp_bits':fields[10],
                 'image_unchanged':fields[11],'host_above_4g':bool(fields[12]),'memory':actual[56:]}
            delta=compare(case,got,want)
            results.append({'name':case['name'],'entry':hex(case['entry']),'local_registers':local,
                            'passed':not delta,'differences':delta,'ignored_undefined_flags':case['ignored_flags'],
                            'excluded_dead_return_slots':[hex(x) for x in case['excluded_dead_return_slots']],
                            'native_registers':dict(zip(REGS,[hex(x) for x in got['regs']])),
                            'native_fp_bits':hex(got['fp_bits']),'native_fp_depth':got['depth'],
                            'host_above_4g':got['host_above_4g'],'image_unchanged':bool(got['image_unchanged'])})
    report={'date':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),'input_sha256':sha,
            'input_origin':'User-uploaded repack; original distribution provenance unverified.',
            'scope':'Isolated actual executable functions with controlled synthetic states; game not launched.',
            'reserved_guest_va_bytes':2**32,'functions':selected,'total':len(results),
            'passed':sum(r['passed'] for r in results),'cases':results}
    (ROOT/'logs/real-game-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(f"Actual game functions: {len(selected)} lifted; {report['passed']}/{report['total']} differential cases passed")
    for r in results:
        if not r['passed']:print(r['name'],r['local_registers'],r['differences'])
    return int(report['passed']!=report['total'])


if __name__=='__main__':sys.exit(main())
