"""Load reviewed dependency source bytes, never unchecked __pycache__ artifacts."""
import json
from pathlib import Path
import sys
import types
from guest import HERE,PINS,pinned

def load(c):
    def module(name,path,data,package=False):
        m=types.ModuleType(name);m.__file__=str(path)
        if package:m.__path__=[str(path.parent)]
        m.__package__=name if package else name.rpartition('.')[0]
        sys.modules[name]=m
        exec(compile(data,str(path),'exec'),m.__dict__)
        return m
    manifest=json.loads(pinned(c['reviews']['source']['path'],c['reviews']['source']['sha256']))
    host=Path(c['isolation_root'])/'host'
    for name in ('__init__','broker','gateway','control'):
        rel='hostbroker/'+name+'.py';path=host/rel
        module('hostbroker' if name=='__init__' else 'hostbroker.'+name,path,pinned(str(path),manifest['host'][rel]),name=='__init__')
    own=json.loads(pinned(c['reviews']['orchestrator']['path'],c['reviews']['orchestrator']['sha256']))
    for name in ('runtime','lifecycle'):
        rel='vendor/'+name+'.py';path=HERE/rel
        module(name,path,pinned(str(path),own[rel]))
