"""Fail-closed target checks; does not attach to any game or inject."""
from pathlib import Path
import json
import os
import subprocess
import sys

PROJECT=Path(__file__).resolve().parents[2]
PYTHON=PROJECT/'runtime'/'python'/'python.exe'
SCRIPT=PROJECT/'speed_engine'/'controller.py'
DLL=PROJECT/'release'/'speed_engine'/'SpeedEngine64.dll'

def main():
    command=[str(PYTHON),'-I','-B',str(SCRIPT),'--test-pid',str(os.getpid())]
    result=subprocess.run(command,capture_output=True,text=True,timeout=15,creationflags=0x08000000)
    if result.returncode==0 or 'TARGET_REJECTED: executable path' not in result.stdout:
        raise RuntimeError('Unrelated Python target not rejected: '+result.stdout+' '+result.stderr)
    import pefile
    pe=pefile.PE(str(DLL),fast_load=True)
    if pe.FILE_HEADER.Machine!=0x8664:raise RuntimeError('DLL not x64')
    pe.close()
    outcome=dict(status='PASS',wrong_target_rejected=True,dll_x64=True)
    (PROJECT/'analysis'/'speed_engine'/'SECURITY_TEST.json').write_text(json.dumps(outcome,indent=2),encoding='utf8')
    print(json.dumps(outcome))

if __name__=='__main__':
    sys.path.insert(0,str(PROJECT/'tools'/'vendor'))
    main()
