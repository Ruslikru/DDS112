import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
destination = Path(sys.argv[1]).resolve()
destination.mkdir(parents=True, exist_ok=False)
data = destination / 'check-data'
builtin = destination / 'builtin'
builtin.mkdir()
os.environ.update(DATA_DIR=str(data), DATABASE_URL='sqlite:///' + (data / 'speech.db').as_posix(),
                  TRAINING_CATALOG='two-dds', VOICE_AUTO_GENERATE='false', AI_AUTO_REVIEW='false',
                  DEMO_PASSWORD='Training112!', ENFORCE_SERVER_NAME='0')

from fastapi.testclient import TestClient
from sqlalchemy import select
from apps.api.app.main import app
from apps.api.app import voice
from apps.api.app.db import SessionLocal, TicketVersion

original = ROOT / 'local_ai/voice/builtin'
records = json.loads((original / 'manifest.json').read_text(encoding='utf-8'))
for record in records:
    target = builtin / record['file']
    if not target.exists():
        shutil.copyfile(original / record['file'], target)
generated = []
with TestClient(app):
    with SessionLocal() as db:
        needed = {key for version in db.scalars(select(TicketVersion)) for key in voice.keys(version.data)}
        pending = [job.data for job in db.scalars(select(voice.VoiceJob)) if job.id in needed and job.status != 'ready']
    try:
        for job in pending:
            settings = {**job['settings'], 'tts_device': 'gpu'}
            file, metrics = voice.runtime.synthesize(job['text'], job['gender'], settings=settings)
            raw = file.read_bytes()
            assert raw.startswith(b'RIFF') and metrics['duration'] > 0
            digest = hashlib.sha256(raw).hexdigest()
            target = builtin / (digest + '.wav')
            if not target.exists():
                shutil.copyfile(file, target)
            record = {'text': job['text'], 'gender': job['gender'], 'tts': job['settings']['tts'],
                      'file': target.name, 'duration': metrics['duration']}
            records.append(record)
            generated.append(record)
            print('GENERATED', len(generated), '/', len(pending), job['text'][:85], flush=True)
    finally:
        voice.runtime.stop()
    with (builtin / 'manifest.json').open('x', encoding='utf-8') as output:
        json.dump(records, output, ensure_ascii=False, indent=2)
    voice.runtime.bundle = destination
    with SessionLocal() as db:
        voice.restore_builtin(db)
        db.commit()
        assert all(db.get(voice.VoiceJob, key).status == 'ready' for key in needed)
    with (destination / 'report.json').open('x', encoding='utf-8') as output:
        json.dump({'ready': True, 'needed_keys': len(needed), 'generated': len(generated), 'total_records': len(records),
                   'generation_device': 'gpu', 'playback_requires_gpu': False}, output, indent=2)
print('READY', builtin, flush=True)
