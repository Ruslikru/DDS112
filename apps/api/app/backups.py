import asyncio
import hashlib
import json
import shutil
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
from .db import DATA, engine, SessionLocal
from .management_models import ManagementSetting

lock=threading.Lock()

def settings(db):
    row=db.get(ManagementSetting,'backup')
    return {'enabled':True,'interval_hours':24,'folder':str(DATA/'backups'/'daily'),**(row.value if row else {})}

def validate_folder(value):
    folder=Path(value).expanduser().resolve()
    if not Path(value).is_absolute():raise ValueError('Укажите абсолютный путь к папке сервера или сетевой папке')
    media=(DATA/'media').resolve()
    if folder==media or media in folder.parents:raise ValueError('Резервные копии нельзя сохранять внутри папки media')
    return folder

def perform():
    if not lock.acquire(False):raise ValueError('Копирование уже выполняется')
    try:
        with SessionLocal() as db:config=settings(db)
        folder=validate_folder(config['folder'])/datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        folder.mkdir(parents=True)
        if engine.dialect.name!='sqlite':raise ValueError('Этот способ копирования поддерживает настольную базу SQLite')
        with sqlite3.connect(engine.url.database) as source,sqlite3.connect(folder/'database.sqlite') as target:source.backup(target)
        if (DATA/'media').exists():shutil.copytree(DATA/'media',folder/'media')
        for name in ('ai-settings.json','classroom.json'):
            if (DATA/name).exists():shutil.copy2(DATA/name,folder/name)
        manifest={'created':time.time(),'database':'sqlite','files':{}}
        for file in folder.rglob('*'):
            if file.is_file():
                with file.open('rb') as f:manifest['files'][file.relative_to(folder).as_posix()]=hashlib.file_digest(f,'sha256').hexdigest()
        (folder/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),'utf-8')
        result={'last_run':time.time(),'last_success':time.time(),'last_folder':str(folder),'error':''}
    except Exception as error:
        result={'last_run':time.time(),'error':str(error)[:1000]}
    finally:lock.release()
    with SessionLocal() as db:
        row=db.get(ManagementSetting,'backup')
        if not row:row=ManagementSetting(key='backup',value={});db.add(row)
        row.value={**row.value,**result};db.commit()
    return result

async def worker():
    while True:
        await asyncio.sleep(30)
        with SessionLocal() as db:config=settings(db)
        if config['enabled'] and time.time()-config.get('last_run',0)>=config['interval_hours']*3600:
            await asyncio.to_thread(perform)
