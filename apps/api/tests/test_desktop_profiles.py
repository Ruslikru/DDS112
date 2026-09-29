import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'packaging'))
from demo_profiles import DEMO_PASSWORD, reserve


def test_demo_reserves_one_server_and_isolated_reusable_clients(tmp_path):
    assert len(DEMO_PASSWORD) >= 8
    held=set();handles={};serial=0
    def acquire(path):
        nonlocal serial
        serial+=1
        busy=path in held
        handles[serial]=(path,not busy)
        if not busy:held.add(path)
        return serial,busy
    def close(handle):
        path,owner=handles.pop(handle)
        if owner:held.remove(path)
    root,c,h=reserve(tmp_path,acquire,close,lambda _:None)
    assert c['mode']=='server' and root.parent==tmp_path/'demo/runs'
    (root/'session-marker').write_text('old')
    p1,c1,h1=reserve(tmp_path,acquire,close,lambda _:None)  # server still starting
    p2,c2,h2=reserve(tmp_path,acquire,close,lambda _:True)
    assert c1['mode']==c2['mode']=='client' and p1!=p2 and c1['number']!=c2['number']
    c1['token']='existing-station'
    (p1/'classroom.json').write_text(json.dumps(c1),'utf-8')
    close(h1)
    reused,config,_=reserve(tmp_path,acquire,close,lambda _:True)
    assert reused==p1 and config['token']=='existing-station' and not config['station_configured'] and not config['server_selected']
    assert not (tmp_path/'classroom.json').exists()
    close(h)
    next_root,next_config,_=reserve(tmp_path,acquire,close,lambda _:None)
    assert next_config['mode']=='server' and next_root!=root
    assert not (next_root/'session-marker').exists()


def test_regular_local_server_is_used(tmp_path):
    handles=[]
    def acquire(path):handles.append(path);return len(handles),False
    root,config,_=reserve(tmp_path,acquire,lambda _:None,lambda _:True)
    assert config['mode']=='client' and root.name=='client-1'
