"""Validated, side-by-side Windows application updates."""
import hashlib
import json
import re
import zipfile
from pathlib import PurePosixPath

MAX_SIZE=4*1024**3

def validate_package(path, extract_to=None):
    with zipfile.ZipFile(path) as z:
        infos=z.infolist()
        if len(infos)>25000 or sum(i.file_size for i in infos)>MAX_SIZE:raise ValueError('Пакет слишком большой')
        names=set()
        for info in infos:
            name=info.filename
            p=PurePosixPath(name)
            if (not name or name.startswith('/') or '\\' in name or ':' in name or '..' in p.parts or any(x in ('','.','..') for x in name.rstrip('/').split('/')) or
                any(part.endswith(('.', ' ')) or re.match(r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)',part,re.I) for part in p.parts) or
                (info.external_attr>>16)&0o170000==0o120000):raise ValueError('Недопустимый путь в пакете')
            key=name.rstrip('/').casefold()
            if key in names:raise ValueError('Повторяющийся путь в пакете')
            names.add(key)
        if 'update.json' not in z.namelist() or z.getinfo('update.json').file_size>4*1024**2:raise ValueError('В пакете отсутствует update.json')
        manifest=json.loads(z.read('update.json'))
        if manifest.get('app')!='Dispetcher112.Desktop' or not re.fullmatch(r'[\w.\-]{1,60}',str(manifest.get('version',''))):raise ValueError('Пакет предназначен для другой программы')
        hashes=manifest.get('files',{})
        files={i.filename for i in infos if not i.is_dir() and i.filename!='update.json'}
        if not isinstance(hashes,dict) or set(hashes)!=files or 'Dispetcher112.exe' not in files or not any(n.startswith('_internal/') for n in files):raise ValueError('Неполный состав пакета')
        for name in files:
            digest=hashlib.sha256()
            with z.open(name) as source:
                while block:=source.read(1024*1024):digest.update(block)
            if digest.hexdigest()!=hashes[name]:raise ValueError('Контрольная сумма не совпадает: '+name)
        if extract_to:
            extract_to.mkdir(parents=True,exist_ok=False)
            z.extractall(extract_to)
        return manifest
