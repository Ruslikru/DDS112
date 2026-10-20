"""Run only after the separately requested confirmation of this exact database."""
import argparse,datetime,hashlib,json,shutil,sqlite3
from pathlib import Path

TARGET=Path(r'C:\Users\rusli\AppData\Local\Dispetcher112\demo\runs\1e5732aae1074add81d011f7895f7189\dispetcher.db')
KEEP={56,57}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--confirmed',action='store_true');args=parser.parse_args()
    if not TARGET.is_file():raise RuntimeError('Named database is missing')
    with sqlite3.connect('file:'+TARGET.as_posix()+'?mode=ro',uri=True) as db:
        rows=list(db.execute('SELECT id,title FROM tickets ORDER BY id'))
    ids={r[0] for r in rows}
    if ids!=set(range(1,61)):raise RuntimeError('Database contents changed; review a new deletion plan')
    print(json.dumps({'database':str(TARGET),'keep':[r for r in rows if r[0] in KEEP],'remove':[r[0] for r in rows if r[0] not in KEEP]},ensure_ascii=False))
    if not args.confirmed:return
    folder=Path.home()/'Codex Backups/Deleted'/('dds-tickets-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
    folder.mkdir(parents=True,exist_ok=False);files=[]
    for source in [TARGET,Path(str(TARGET)+'-wal'),Path(str(TARGET)+'-shm')]:
        if not source.exists():continue
        dest=folder/source.name;shutil.copy2(source,dest)
        digest=hashlib.sha256(source.read_bytes()).hexdigest()
        if digest!=hashlib.sha256(dest.read_bytes()).hexdigest():raise RuntimeError('Backup verification failed')
        files.append({'source':str(source),'backup':str(dest),'sha256':digest})
    with sqlite3.connect('file:'+TARGET.as_posix()+'?mode=ro',uri=True) as source,sqlite3.connect(folder/'consistent-snapshot.db') as dest:
        source.backup(dest)
        if dest.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise RuntimeError('Snapshot verification failed')
    manifest={'status':'verified','files':files,'keep_ticket_ids':sorted(KEEP)}
    (folder/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    with sqlite3.connect(TARGET) as db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        before={table:list(db.execute('SELECT * FROM '+table)) for table in ('users','groups')}
        attempt_ids='SELECT id FROM attempts WHERE assignment_id IN (SELECT id FROM assignments WHERE version_id IN (SELECT id FROM ticket_versions WHERE ticket_id NOT IN (56,57)))'
        counts={}
        for table in ('approved_answers','attempt_events','scheduled_events'):
            counts[table]=db.execute('DELETE FROM '+table+' WHERE attempt_id IN ('+attempt_ids+')').rowcount
        counts['attempts']=db.execute('DELETE FROM attempts WHERE id IN ('+attempt_ids+')').rowcount
        counts['assignments']=db.execute('DELETE FROM assignments WHERE version_id IN (SELECT id FROM ticket_versions WHERE ticket_id NOT IN (56,57))').rowcount
        counts['ticket_versions']=db.execute('DELETE FROM ticket_versions WHERE ticket_id NOT IN (56,57)').rowcount
        counts['tickets']=db.execute('DELETE FROM tickets WHERE id NOT IN (56,57)').rowcount
        assert db.execute('SELECT COUNT(*) FROM tickets').fetchone()[0]==2
        assert not list(db.execute('PRAGMA foreign_key_check'))
        assert before=={table:list(db.execute('SELECT * FROM '+table)) for table in before}
        db.commit()
    (folder/'cleanup-result.json').write_text(json.dumps(counts,indent=2),encoding='utf-8')
    print(json.dumps({'backup':str(folder),'deleted':counts,'remaining':2}))

if __name__=='__main__':main()
