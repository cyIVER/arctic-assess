"""Second owned process: sentinel rejection only; no Docker/model imports."""
import argparse,json,os,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent/'vendor'))
from lifecycle import Phase
from runtime import Denied

def main():
 p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--deadline',required=True,type=float);a=p.parse_args()
 phase=Phase(a.root,a.deadline,clock=time.time)
 try:phase.start()
 except Denied as e:
  if str(e)!='executor already started; no restart/recovery':return 2
  print(json.dumps({'second_process_denied':True,'reason':'existing-phase-sentinel','docker_calls':0,'model_calls':0}));return 0
 return 2
if __name__=='__main__':sys.exit(main())
