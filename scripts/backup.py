"""Database snapshot plus immutable local media; no credentials in archive."""
import sys, json, shutil, sqlite3, subprocess, hashlib
from pathlib import Path
from datetime import datetime, timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import run
from apps.api.app.db import DATA, ROOT, engine

target=ROOT/'backups'/datetime.now().strftime('%Y%m%d-%H%M%S')
target.mkdir(parents=True,exist_ok=False)
if engine.dialect.name=='sqlite':
    with sqlite3.connect(engine.url.database) as source, sqlite3.connect(target/'database.sqlite') as destination: source.backup(destination)
    database_file='database.sqlite'
else:
    database_file='database.dump'
    with (target/database_file).open('wb') as output:
        subprocess.run(['docker','compose','--env-file','.env','-f','deploy/compose.yaml','exec','-T','db','pg_dump','-U','dispetcher','-d','dispetcher','-Fc'],stdout=output,check=True)
shutil.copytree(DATA/'media',target/'media')
manifest={'created_at':datetime.now(timezone.utc).isoformat(),'database':engine.dialect.name,'schema':str(engine.connect().exec_driver_sql('SELECT version_num FROM alembic_version').scalar()),'files':{}}
for file in target.rglob('*'):
    if file.is_file(): manifest['files'][file.relative_to(target).as_posix()]=hashlib.sha256(file.read_bytes()).hexdigest()
(target/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print(target)
