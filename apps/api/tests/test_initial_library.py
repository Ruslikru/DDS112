from sqlalchemy import select
from test_flows import app,TestClient,SessionLocal
from apps.api.app.db import Ticket,TicketVersion
from apps.api.app.classroom_models import MiniQuestion,ServiceDefinition

def test_new_library_has_only_two_tutorials_after_restart():
    for _ in range(2):
        with TestClient(app):
            with SessionLocal() as db:
                tickets=list(db.scalars(select(Ticket)))
                assert len(tickets)==2
                versions=list(db.scalars(select(TicketVersion)))
                assert {v.data['tasks'][0]['onboarding'] for v in versions}=={'dds-1','dds-2'}
                assert db.get(ServiceDefinition,'ЦОДД')
                assert len(list(db.scalars(select(MiniQuestion))))>10
