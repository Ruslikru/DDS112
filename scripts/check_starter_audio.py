"""Verify a clean six-ticket installation without generating any speech."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import wave
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
parser = argparse.ArgumentParser()
parser.add_argument('--bundle', type=Path)
parser.add_argument('--report', type=Path)
args = parser.parse_args()
data = Path(tempfile.mkdtemp(prefix='starter-audio-check-', dir=ROOT / 'build'))
os.environ.update(DATA_DIR=str(data), DATABASE_URL='sqlite:///' + (data / 'check.db').as_posix(),
                  VOICE_AUTO_GENERATE='false', AI_AUTO_REVIEW='false', TRAINING_CATALOG='full',
                  DEMO_PASSWORD='Training112!', ENFORCE_SERVER_NAME='0')
from fastapi.testclient import TestClient
from sqlalchemy import select
from apps.api.app.main import app
from apps.api.app import voice, starter_library, startup_models
from apps.api.app.db import SessionLocal, TicketVersion
from apps.api.app.test_catalog import library_visible
from apps.api.app.scenario_contract import validate_scenario
from local_ai.voice import VoiceRuntime

if args.bundle:
    bundle = args.bundle.resolve()
    assert (bundle / '_internal/content/starter-tickets.json').read_bytes() == (ROOT / 'content/starter-tickets.json').read_bytes()
    voice.runtime.bundle = bundle / 'local_ai/voice'

async def no_warmup():
    pass

with patch.object(startup_models, 'warm_models', no_warmup), \
     patch.object(VoiceRuntime, 'synthesize', side_effect=AssertionError('Startup generated speech')), \
     TestClient(app):
    with SessionLocal() as db:
        versions = list(db.scalars(select(TicketVersion)))
        practice = [v for v in versions if library_visible(v.data)]
        assert len(practice) == 6, len(practice)
        starter_library.seed(db)
        assert len(list(db.scalars(select(TicketVersion)))) == len(versions), 'Duplicate seed tickets'
        needed = set()
        for version in versions:
            assert voice.readiness(version.data, db)['ready'], version.data['title']
            needed.update(voice.keys(version.data))
            if version.data['tasks'][0]['id'].startswith('starter-'):
                assert not validate_scenario(version.data['tasks'][0])
        for key in needed:
            job = db.get(voice.VoiceJob, key)
            assert voice.recording_ready(job)
            file = data / 'media' / job.audio_id
            assert hashlib.sha256(file.read_bytes()).hexdigest() == job.audio_id
            with wave.open(str(file), 'rb') as audio:
                assert audio.getnframes() > 0 and any(audio.readframes(audio.getnframes()))
        report = dict(ready=True, tickets=len(practice), guided_tickets=len(versions)-len(practice),
                      required_recordings=len(needed), generated_on_startup=0,
                      titles=[v.data['title'] for v in practice], data=str(data))
if args.report:
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(report, ensure_ascii=False))
