import wave
import pytest

@pytest.fixture(autouse=True)
def prepared_seed_speech(monkeypatch,tmp_path):
    from apps.api.app import voice
    from sqlalchemy import select
    original=voice.recover
    monkeypatch.setattr(voice,"recover_original",original,raising=False)
    def recover():
        original()
        def synthesize(*args):
            path=tmp_path/'seed-speech.wav'
            with wave.open(str(path),'wb') as out:
                out.setparams((1,2,24000,0,'NONE','not compressed'));out.writeframes(b'\0\0'*240)
            return path,{'duration':.01,'voice':'fixture','seconds':0}
        from unittest.mock import patch
        with patch.object(voice.runtime,'synthesize',synthesize):
            for _ in range(1000):
                with voice.SessionLocal() as db:
                    if not db.scalar(select(voice.VoiceJob).where(voice.VoiceJob.status=='pending')):break
                voice.generate_one()
    monkeypatch.setattr(voice,'recover',recover)
