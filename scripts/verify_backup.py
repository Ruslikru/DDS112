"""Verify hashes and restore into a NEW temporary database; preserve the live database."""
import sys,json,hashlib,subprocess,sqlite3,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import run

folder=Path(sys.argv[1]).resolve(); manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
for name,digest in manifest['files'].items():
    file=(folder/name).resolve()
    if not file.is_relative_to(folder) or hashlib.sha256(file.read_bytes()).hexdigest()!=digest: raise ValueError('Backup checksum failed: '+name)
if manifest['database']=='sqlite':
    with sqlite3.connect('file:'+str(folder/'database.sqlite')+'?mode=ro',uri=True) as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        print('users, attempts:',db.execute('SELECT (SELECT count(*) FROM users), (SELECT count(*) FROM attempts)').fetchone())
else:
    database='verify_'+uuid.uuid4().hex[:12]
    base=['docker','compose','--env-file','.env','-f','deploy/compose.yaml','exec','-T','db']
    subprocess.run(base+['createdb','-U','dispetcher',database],check=True)
    try:
        with (folder/'database.dump').open('rb') as dump: subprocess.run(base+['pg_restore','-U','dispetcher','-d',database,'--exit-on-error'],stdin=dump,check=True)
        subprocess.run(base+['psql','-U','dispetcher','-d',database,'-c','SELECT (SELECT count(*) FROM users) AS users, (SELECT count(*) FROM attempts) AS attempts;'],check=True)
    finally: subprocess.run(base+['dropdb','-U','dispetcher',database],check=True)
print('Backup verified; live database was not changed.')
