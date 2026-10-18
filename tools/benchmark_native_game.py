#!/usr/bin/env python3
"""Measure the real game with trace off, using previously verified local frames.
Presentation callbacks measure host display updates, not simulation ticks.
"""
import argparse
from contextlib import contextmanager
import fcntl
import re
import hashlib
import json
import os
from pathlib import Path
import signal
import statistics
import struct
import subprocess
import time
ROOT=Path(__file__).resolve().parents[1]


def read_bmp(path):
    b=path.read_bytes();offset=struct.unpack_from('<I',b,10)[0]
    size,w,h,planes,bits,compression=struct.unpack_from('<IiiHHI',b,14)
    if size!=40 or bits!=24 or compression or w!=640 or abs(h)!=480:raise ValueError('Unexpected BMP layout')
    stride=(w*3+3)&~3;rgb=bytearray(w*abs(h)*3)
    for y in range(abs(h)):
        row=b[offset+(y if h<0 else abs(h)-1-y)*stride:][:w*3]
        start=y*w*3
        rgb[start:start+w*3:3]=row[2::3];rgb[start+1:start+w*3:3]=row[1::3];rgb[start+2:start+w*3:3]=row[0::3]
    return bytes(rgb)


def read_ppm(path):
    b=path.read_bytes();head=b.split(b'\n',3)
    if len(head)!=4 or head[:3]!=[b'P6',b'640 480',b'255'] or len(head[3])!=640*480*3:raise ValueError('Incomplete/nonstandard frame')
    return head[3]


def title_mask(rgb):
    return bytes(int(rgb[i]>140 and rgb[i+1]>100 and rgb[i+2]<120)
                 for y in range(0,25) for x in range(490,635) for i in [(y*640+x)*3])


def battle_ui(rgb):
    # Native battlefield has a blue command bar at the bottom left; menu pages do not.
    return sum(rgb[(y*640+x)*3+2]>100 and rgb[(y*640+x)*3+2]>rgb[(y*640+x)*3]+30
               for y in range(455,475,2) for x in range(10,420,4))>80


def references():
    out=ROOT/'.local/performance';out.mkdir(exist_ok=True)
    result={}
    for name,source in [('menu','menu-verified'),('single','single-player-verified'),('skirmish','skirmish-settings-verified')]:
        png=ROOT/f'.local/native-boot/{source}.png';bmp=out/f'{name}.bmp'
        if not png.exists():raise SystemExit(f'Need the previously visually verified local frame: {png}')
        if not bmp.exists() or bmp.stat().st_mtime<png.stat().st_mtime:
            subprocess.run(['sips','-s','format','bmp',str(png),'--out',str(bmp)],capture_output=True,check=True)
        result[name]=title_mask(read_bmp(bmp))
    return result


def classify(rgb,refs):
    if battle_ui(rgb):return 'battle'
    mask=title_mask(rgb);scores={name:sum(a!=b for a,b in zip(mask,ref)) for name,ref in refs.items()}
    best=min(scores,key=scores.get)
    return best if scores[best]<15 and sum(mask)>20 else 'unknown'


def cpu_sample(pid):
    p=subprocess.run(['ps','-p',str(pid),'-o','time=,rss='],capture_output=True,text=True)
    parts=p.stdout.split()
    if len(parts)!=2:return None
    fields=parts[0].split(':');seconds=0.0
    for f in fields:seconds=seconds*60+float(f)
    return seconds,int(parts[1])*1024


@contextmanager
def game_settings(speed):
    path=ROOT/'game/ra2-upload-41bbcc83/RA2.INI';original=path.read_bytes()
    match=re.search(rb'(?ms)^\[Skirmish\]\r?\n(.*?)(?=^\[|\Z)',original)
    if not match:raise ValueError('No Skirmish settings section')
    section,n=re.subn(rb'(?m)^GameSpeed=\d+',b'GameSpeed='+str(speed).encode(),match.group(1),count=1)
    if n!=1:raise ValueError('No GameSpeed field')
    path.write_bytes(original[:match.start(1)]+section+original[match.end(1):])
    try:yield
    finally:path.write_bytes(original)


def run(profile,label,hold,timeout,pacing,speed):
    folder=ROOT/f'.local/performance/{label}';folder.mkdir(parents=True,exist_ok=False)
    binary=ROOT/('.local/native-boot' if profile=='debug' else '.local/native-release')/'ra2-native-boot'
    binary_digest=hashlib.sha256(binary.read_bytes()).hexdigest()
    refs=references();frame=folder/'frame.ppm';control=folder/'control.txt';metrics=folder/'frames.jsonl'
    env={**os.environ,'RA2_TRACE':'0','RA2_PROBE_SECONDS':str(timeout),'RA2_CAPTURE_MS':'500',
         'RA2_FRAME_PATH':str(frame),'RA2_PROBE_CONTROL_FILE':str(control),'RA2_METRICS_PATH':str(metrics),
         'RA2_IDLE_PACING':str(pacing),'RA2_GAME_FRAME_VA':'0xA40D2C'}
    for name in ['RA2_PROBE_CLICK','RA2_PROBE_KEY']:env.pop(name,None)
    game=ROOT/'game/ra2-upload-41bbcc83/game.exe'
    if hashlib.sha256(game.read_bytes()).hexdigest()!='fe67fdac5073530a79baec14c4e072b5e7e4c0c462cee9659870c5330e9e6e3e':raise SystemExit('Frame-counter address only audited for this game image')
    transitions=[];samples=[];command=0;stage='menu';since=time.monotonic();started=since
    stages=['menu','single','skirmish','battle'];clicked=set();battle_at=None;last_frame=None;last_cpu=0;usage=None;reason='process_exit'
    with game_settings(speed),(folder/'game.log').open('w') as log:
        proc=subprocess.Popen([str(binary),str(game),'--with-launcher'],cwd=game.parent,stdout=log,stderr=subprocess.STDOUT,env=env)
        try:
            while True:
                pid,status,ru=os.wait4(proc.pid,os.WNOHANG)
                if pid:
                    proc.returncode=os.waitstatus_to_exitcode(status);usage=ru;break
                now=time.monotonic()
                if now-started>timeout+5 or (battle_at and now-battle_at>=hold):
                    reason='battle_observation_complete' if battle_at else 'timeout'
                    proc.send_signal(signal.SIGTERM)
                    _,status,usage=os.wait4(proc.pid,0);proc.returncode=os.waitstatus_to_exitcode(status);break
                if now-last_cpu>=1:
                    sample=cpu_sample(proc.pid)
                    if sample:samples.append({'seconds':now-started,'cpu_seconds':sample[0],'rss_bytes':sample[1],'expected_stage':stage})
                    last_cpu=now
                try:
                    stamp=frame.stat().st_mtime_ns
                    if stamp!=last_frame:
                        last_frame=stamp;rgb=read_ppm(frame);observed=classify(rgb,refs)
                        if observed==stage and stage not in [t['stage'] for t in transitions]:
                            transitions.append({'stage':stage,'seconds':now-started});since=now
                            (folder/f'{stage}.ppm').write_bytes(frame.read_bytes())
                            print(label,stage,f'{now-started:.3f}s',flush=True)
                            if stage=='battle':battle_at=now
                        if observed==stage and stage!='battle' and stage not in clicked and now-since>=1:
                            command+=1;x,y={'menu':(550,220),'single':(550,305),'skirmish':(550,260)}[stage]
                            tmp=control.with_suffix('.tmp');tmp.write_text(f'{command} click {x} {y}\n');tmp.replace(control)
                            clicked.add(stage);stage=stages[stages.index(stage)+1]
                except (FileNotFoundError,ValueError):pass
                time.sleep(.1)
        except BaseException:
            if proc.returncode is None:
                proc.terminate();proc.wait(timeout=10)
            raise
    points=[json.loads(line) for line in metrics.read_text().splitlines()] if metrics.exists() else []
    # hle_ticks_ms is monotonic in an arbitrary epoch; use first callback as origin.
    frame_origin=points[0]['monotonic_ms'] if points else 0
    battle_seconds=next((x['seconds'] for x in transitions if x['stage']=='battle'),None)
    intervals=[x for x in points[1:] if battle_seconds is not None and x['host_elapsed_ms']/1000>=battle_seconds+2]
    rates=[x['interval_frames']*1000/x['interval_ms'] for x in intervals if x['interval_ms']]
    logic_rates=[]
    for prev,nxt in zip(points,points[1:]):
        if battle_seconds is not None and prev['host_elapsed_ms']/1000>=battle_seconds+2:
            dt=nxt['host_elapsed_ms']-prev['host_elapsed_ms'];df=nxt['game_frame']-prev['game_frame']
            if dt>0 and df>=0:logic_rates.append(df*1000/dt)
    cpu_rates=[]
    for prev,nxt in zip(samples,samples[1:]):
        if battle_seconds is not None and prev['seconds']>=battle_seconds+2:
            cpu_rates.append(100*(nxt['cpu_seconds']-prev['cpu_seconds'])/(nxt['seconds']-prev['seconds']))
    report={'label':label,'profile':profile,'idle_pacing':pacing,'skirmish_game_speed_ini':speed,'binary_sha256':binary_digest,
            'trace_enabled':False,'capture_interval_ms':500,'planned_battle_seconds':hold,'stop_reason':reason,
            'process_exit_code':proc.returncode,'stage_detection':'previously inspected title masks and battlefield blue command bar; inspect saved frames',
            'transitions':transitions,'wall_seconds':time.monotonic()-started,
            'cpu_user_seconds':usage.ru_utime if usage else None,'cpu_system_seconds':usage.ru_stime if usage else None,
            'max_rss_bytes':usage.ru_maxrss if usage else None,'battle_present_callback_fps_median':statistics.median(rates) if rates else None,
            'battle_cpu_percent_median':statistics.median(cpu_rates) if cpu_rates else None,
            'samples':samples,'display_metrics':points,'game_logic_fps_measured':True,'game_frame_counter_va':'0xA40D2C','battle_logic_fps_median':statistics.median(logic_rates) if logic_rates else None,'cpu_percent_basis':'100 percent is one logical CPU','image_detection_resolution_seconds':0.6,'game_completed':False}
    (ROOT/f'logs/performance-{label}.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ['samples','display_metrics']},indent=2),flush=True)
    return report

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--profile',choices=['debug','release'],required=True);ap.add_argument('--label',required=True)
    ap.add_argument('--battle-seconds',type=int,default=30);ap.add_argument('--timeout',type=int,default=240);ap.add_argument('--idle-pacing',type=int,choices=[0,1],default=0)
    ap.add_argument('--game-speed',type=int,choices=range(6),default=0)
    a=ap.parse_args()
    if not a.label.replace('-','').replace('_','').isalnum() or not 1<=a.battle_seconds<=300 or not 30<=a.timeout<=3600:raise SystemExit('Invalid benchmark parameters')
    with (ROOT/'.local/performance/benchmark.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise SystemExit('Another benchmark is running; run measurements sequentially')
        run(a.profile,a.label,a.battle_seconds,a.timeout,a.idle_pacing,a.game_speed)
