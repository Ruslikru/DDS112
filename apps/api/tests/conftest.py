import wave
import pytest

@pytest.fixture(autouse=True)
def prepared_seed_speech(monkeypatch,tmp_path):
    monkeypatch.setenv('TRAINING_CATALOG','full')
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


@pytest.fixture(autouse=True)
def legacy_sample_library(monkeypatch):
    """A new classroom ships only the two guided DDS tickets; the workflow tests still exercise the
    original sample scenarios (112 and DDS), so they are seeded here for the test database only."""
    from apps.api.app import main
    from apps.api.app.initial_library import seed as library_seed
    def seed(db):
        library_seed(db)
        from sqlalchemy import select
        from apps.api.app.db import User, Ticket, TicketVersion, Assignment
        from apps.api.app.seed import sample_tasks
        from apps.api.app.schemas import TicketData
        if db.scalar(select(Ticket.id).where(Ticket.title=='Задымление мусоропровода')): return
        admin=db.scalar(select(User).where(User.login=='admin'))
        teacher=db.scalar(select(User).where(User.login=='teacher'))
        students=list(db.scalars(select(User).where(User.role=='student')))
        for i,task in enumerate(sample_tasks()):
            ticket=Ticket(title=task['title'],created_by=admin.id);db.add(ticket);db.flush()
            data=TicketData.model_validate({'title':task['title'],'description':task.get('initial_card',{}).get('description') or task['intro'],'tasks':[task]}).model_dump()
            version=TicketVersion(ticket_id=ticket.id,number=1,published=True,data=data);db.add(version);db.flush()
            for student in students:
                db.add(Assignment(version_id=version.id,student_id=student.id,teacher_id=teacher.id,title=f'Билет {i+1:02d} · {task["title"]}'))
        db.commit()
    monkeypatch.setattr(main,'seed',seed)
