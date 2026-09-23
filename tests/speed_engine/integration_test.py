"""End-to-end x64 TestTarget integration. No NBA process is touched."""
from pathlib import Path
import json
import queue
import re
import statistics
import subprocess
import sys
import threading
import time

PROJECT=Path(__file__).resolve().parents[2]
TARGET=PROJECT/'build'/'speed_engine'/'SpeedEngineTestTarget.exe'
CONTROLLER=PROJECT/'speed_engine'/'controller.py'
PYTHON=PROJECT/'runtime'/'python'/'python.exe'
CREATE_NO_WINDOW=0x08000000

def read_thread(pipe,q):
    for line in pipe:q.put((time.monotonic(),line.strip()))

def wait_line(q,prefix,timeout=10):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        try:stamp,line=q.get(timeout=min(0.5,end-time.monotonic()))
        except queue.Empty:continue
        if line.startswith('ERROR '):raise RuntimeError(line)
        if line.startswith(prefix):return stamp,line
    raise RuntimeError('Timeout waiting for '+prefix)

def main():
    target=subprocess.Popen([str(TARGET),'30'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1,creationflags=CREATE_NO_WINDOW)
    tq=queue.Queue();threading.Thread(target=read_thread,args=(target.stdout,tq),daemon=True).start()
    controller=None
    result=[]
    try:
        _,ready=wait_line(tq,'READY ',5)
        freq=int(re.search(r'qpf=(\d+)',ready).group(1))
        controller=subprocess.Popen([str(PYTHON),'-I','-B',str(CONTROLLER),'--test-pid',str(target.pid)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1,creationflags=CREATE_NO_WINDOW)
        cq=queue.Queue();threading.Thread(target=read_thread,args=(controller.stdout,cq),daemon=True).start()
        _,started=wait_line(cq,'READY ',12)
        info=json.loads(started[6:]);assert info['hook_mask']==15,info
        for multiplier in (1.0,0.75,0.5,0.75,1.0):
            controller.stdin.write(f'SET {multiplier}\n');controller.stdin.flush()
            _,statusline=wait_line(cq,'SET ',4)
            state=json.loads(statusline[4:])
            if state['active']!=multiplier or state['ack']!=state['seq']:
                raise RuntimeError('Multiplier/IPC failed: '+statusline)
            start=time.monotonic();samples=[]
            while time.monotonic()-start<1.2:
                try:stamp,line=tq.get(timeout=.3)
                except queue.Empty:continue
                if stamp<start+.25 or not line.startswith('T '):continue
                numbers=dict((k,int(v)) for k,v in re.findall(r'(qpc|gtc64|gtc|tgt)=(\d+)',line))
                if len(numbers)==4:samples.append(numbers)
            if len(samples)<4:raise RuntimeError('Too few timing samples')
            medians={k:statistics.median(x[k] for x in samples) for k in ('qpc','gtc64','gtc','tgt')}
            expected_qpc=freq*0.1*multiplier
            if abs(medians['qpc']-expected_qpc)>max(0.35*expected_qpc,35000):
                raise RuntimeError('QPC ratio mismatch: '+str((multiplier,medians,expected_qpc)))
            for k in ('gtc64','gtc','tgt'):
                if abs(medians[k]-100*multiplier)>max(0.40*100*multiplier,18):
                    raise RuntimeError(k+' ratio mismatch: '+str((multiplier,medians)))
            result.append(dict(multiplier=multiplier,medians=medians,calls=state['calls']))
        controller.stdin.write('QUIT\n');controller.stdin.flush()
        _,quit_line=wait_line(cq,'QUIT ',4)
        if json.loads(quit_line[5:])['active']!=1.0:raise RuntimeError('QUIT did not restore')
        if controller.wait(timeout=5)!=0:raise RuntimeError('controller exit error')
        report=dict(status='PASS',target_pid=target.pid,frequency=freq,hook_mask=info['hook_mask'],phases=result,quit=json.loads(quit_line[5:]))
        out=PROJECT/'analysis'/'speed_engine'/'TEST_TARGET_INTEGRATION.json'
        out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
        print(json.dumps(report,ensure_ascii=False))
    finally:
        if controller and controller.poll() is None:controller.kill();controller.wait()
        if target.poll() is None:target.kill();target.wait()

if __name__=='__main__':main()
