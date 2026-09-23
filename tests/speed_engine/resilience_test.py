"""Verify controller death restores 1x and same-session reattach works."""
import json
from pathlib import Path
import queue
import re
import subprocess
import sys
import threading
import time

PROJECT=Path(__file__).resolve().parents[2]
PYTHON=PROJECT/'runtime'/'python'/'python.exe'
CONTROL=PROJECT/'speed_engine'/'controller.py'
TARGET=PROJECT/'build'/'speed_engine'/'SpeedEngineTestTarget.exe'
NO_WINDOW=0x08000000

def start_control(pid):
    p=subprocess.Popen([str(PYTHON),'-I','-B',str(CONTROL),'--test-pid',str(pid)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1,creationflags=NO_WINDOW)
    q=queue.Queue()
    def read():
        for line in p.stdout:q.put(line.strip())
    threading.Thread(target=read,daemon=True).start()
    return p,q

def receive(q,prefix):
    for _ in range(100):
        try:line=q.get(timeout=.1)
        except queue.Empty:continue
        if line.startswith('ERROR '):raise RuntimeError(line)
        if line.startswith(prefix):return json.loads(line[len(prefix):])
    raise RuntimeError('No '+prefix)

def multiplier_samples(target,seconds=1):
    end=time.monotonic()+seconds
    values=[]
    while time.monotonic()<end:
        line=target.stdout.readline()
        m=re.search(r'qpc=(\d+)',line)
        if m:values.append(int(m.group(1)))
    return values[-5:]

def main():
    target=subprocess.Popen([str(TARGET),'20'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1,creationflags=NO_WINDOW)
    one=two=None
    try:
        if not target.stdout.readline().startswith('READY '):raise RuntimeError('Target not ready')
        one,q=start_control(target.pid)
        if receive(q,'READY ')['hook_mask']!=15:raise RuntimeError('Hooks incomplete')
        one.stdin.write('SET 0.10\n');one.stdin.flush()
        if receive(q,'SET ')['active']!=0.1:raise RuntimeError('0.10 not active')
        slow=multiplier_samples(target,1)
        if not all(60000<v<220000 for v in slow):raise RuntimeError('Slow samples '+str(slow))
        one.kill();one.wait()
        normal=multiplier_samples(target,4.5)
        if not all(800000<v<1600000 for v in normal):raise RuntimeError('Death did not restore '+str(normal))
        two,q2=start_control(target.pid)
        if receive(q2,'READY ')['hook_mask']!=15:raise RuntimeError('Reattach hook state lost')
        two.stdin.write('SET 0.50\n');two.stdin.flush()
        if receive(q2,'SET ')['active']!=0.5:raise RuntimeError('Reattach set failed')
        half=multiplier_samples(target,1)
        if not all(350000<v<800000 for v in half):raise RuntimeError('Reattach ratio '+str(half))
        two.stdin.write('SET 0.75\n');two.stdin.flush()
        if receive(q2,'SET ')['active']!=0.75:raise RuntimeError('Reattach 0.75 failed')
        threeq=multiplier_samples(target,1)
        if not all(600000<v<1000000 for v in threeq):raise RuntimeError('Reattach 0.75 ratio '+str(threeq))
        two.stdin.write('QUIT\n');two.stdin.flush()
        if receive(q2,'QUIT ')['active']!=1.0:raise RuntimeError('Quit not normal')
        two.wait(timeout=4)
        out=dict(status='PASS',slow=slow,after_controller_death=normal,reattached_half=half,reattached_075=threeq)
        (PROJECT/'analysis'/'speed_engine'/'TEST_TARGET_RESILIENCE.json').write_text(json.dumps(out,indent=2),encoding='utf8')
        print(json.dumps(out))
    finally:
        for p in (one,two,target):
            if p and p.poll() is None:p.kill();p.wait()

if __name__=='__main__':main()
