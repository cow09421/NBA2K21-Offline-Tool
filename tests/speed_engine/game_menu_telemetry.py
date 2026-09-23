"""One bounded 1.00x menu telemetry session; no multiplier change."""
from pathlib import Path
import json
import subprocess
import sys
import time

PROJECT=Path(__file__).resolve().parents[2]
PYTHON=PROJECT/'runtime'/'python'/'python.exe'
CONTROLLER=PROJECT/'speed_engine'/'controller.py'

def main():
    process=subprocess.Popen([str(PYTHON),'-I','-B',str(CONTROLLER),'--game'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1,creationflags=0x08000000)
    lines=[]
    try:
        ready=process.stdout.readline().strip();lines.append(ready)
        if not ready.startswith('READY '):
            raise RuntimeError('Controller not ready: '+ready+' '+process.stderr.read())
        original=json.loads(ready[6:])
        if original['active']!=1.0 or (original['hook_mask']&9)!=9:
            raise RuntimeError('Game hooks incomplete: '+ready)
        time.sleep(5)
        process.stdin.write('STATUS\n');process.stdin.flush()
        response=process.stdout.readline().strip();lines.append(response)
        if not response.startswith('STATUS '):raise RuntimeError(response)
        result=json.loads(response[7:])
        if result['active']!=1.0 or result['error']!=0:raise RuntimeError(response)
        process.stdin.write('QUIT\n');process.stdin.flush()
        quit_line=process.stdout.readline().strip();lines.append(quit_line)
        if not quit_line.startswith('QUIT ') or json.loads(quit_line[5:])['active']!=1.0 or json.loads(quit_line[5:])['ack']!=json.loads(quit_line[5:])['seq']:
            raise RuntimeError('Restore failed: '+quit_line)
        process.wait(timeout=8)
        report=dict(status='PASS' if result['last_virtual_qpc']!=original['last_virtual_qpc'] else 'NO_QPC_HITS',target=original['target'],creation=original['creation'],initial=original,captured=result,restore=json.loads(quit_line[5:]),elapsed_s=5,ui_evidence='User-confirmed UI menu; harness does not inspect UI')
        (PROJECT/'analysis'/'speed_engine'/'NBA_MENU_TELEMETRY.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
        print(json.dumps(report,ensure_ascii=False))
    finally:
        if process.poll() is None:
            try:
                process.stdin.write('QUIT\n');process.stdin.flush();process.wait(timeout=2)
            except Exception:process.kill();process.wait()

if __name__=='__main__':main()
