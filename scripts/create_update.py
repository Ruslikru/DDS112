"""Create an administrator-uploadable update package only when explicitly invoked."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from device_runtime.updates import validate_package

def create(source,output,version):
    source=source.resolve();output=output.resolve()
    if not (source/'Dispetcher112.exe').is_file() or not (source/'_internal').is_dir():raise ValueError('Укажите папку готовой настольной сборки')
    files=[source/'Dispetcher112.exe']+sorted(p for p in (source/'_internal').rglob('*') if p.is_file())
    manifest={'app':'Dispetcher112.Desktop','version':version,'files':{}}
    for p in files:
        with p.open('rb') as f:manifest['files'][p.relative_to(source).as_posix()]=hashlib.file_digest(f,'sha256').hexdigest()
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'x',zipfile.ZIP_DEFLATED) as z:
        for p in files:z.write(p,p.relative_to(source).as_posix())
        z.writestr('update.json',json.dumps(manifest,ensure_ascii=False,indent=2))
    validate_package(output)
    return output

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('source',type=Path);parser.add_argument('output',type=Path);parser.add_argument('--version',required=True)
    args=parser.parse_args();print(create(args.source,args.output,args.version))
