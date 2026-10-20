import uuid
from test_flows import app, TestClient, SessionLocal
from apps.api.app import voice


def test_old_engine_restores_standard_line_without_synthesis(monkeypatch):
    with TestClient(app):
        monkeypatch.setattr(voice.runtime,'synthesize',lambda *a,**k: (_ for _ in ()).throw(AssertionError('Unexpected synthesis')))
        with SessionLocal() as db:
            job=voice.VoiceJob(id=uuid.uuid4().hex,status='failed',error='Old engine failed',data={
                'text':'Задерживаемся в пути. Ориентировочное прибытие через десять минут.',
                'gender':'male','speaker_id':'brigade','settings':{'tts':'qwen','tts_device':'gpu'},'owner':1})
            db.add(job);db.flush()
            voice.restore_builtin(db)
            assert voice.recording_ready(job)
            assert job.data['settings']['tts']=='qwen' and not job.error


def test_explicit_current_voice_is_not_replaced_with_another_voice():
    with TestClient(app):
        with SessionLocal() as db:
            job=voice.VoiceJob(id=uuid.uuid4().hex,status='failed',data={
                'text':'Задерживаемся в пути. Ориентировочное прибытие через десять минут.',
                'gender':'male','speaker_id':'brigade','settings':{'tts':'piper-irina'},'owner':1})
            db.add(job);db.flush()
            voice.restore_builtin(db)
            assert job.status=='failed' and job.audio_id is None
