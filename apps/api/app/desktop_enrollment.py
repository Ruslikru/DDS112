"""Local server identity is not an operator workstation number."""
import hashlib
import secrets
from sqlalchemy import select
from .db import SessionLocal
from .classroom_models import Workstation


def enroll_server(config):
    with SessionLocal() as db:
        row=db.get(Workstation,config.get('station_id',''))
        token=config.get('token','')
        if not row:
            token=secrets.token_urlsafe(32)
            row=Workstation(id=secrets.token_hex(16),number='Сервер '+secrets.token_hex(6),secret_hash=hashlib.sha256(token.encode()).hexdigest(),approved=True)
            db.add(row)
        elif not token or row.secret_hash!=hashlib.sha256(token.encode()).hexdigest():
            token=secrets.token_urlsafe(32)
            row.secret_hash=hashlib.sha256(token.encode()).hexdigest()
        row.number='Сервер '+row.id[:12];row.approved=True;row.blocked=False
        db.commit()
        return {**config,'token':token,'station_id':row.id,'number':row.number}
