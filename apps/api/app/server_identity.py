"""Persistent classroom name shared by discovery and connected clients."""
import os
import socket
from .db import SessionLocal
from .management_models import ManagementSetting

_activated=False

def reset_activation():
    global _activated
    _activated=False

def activate():
    global _activated
    _activated=True

def is_ready(db=None):
    if os.getenv('ENFORCE_SERVER_NAME')!='1' or _activated:return True
    if os.getenv('DEMO_CLASSROOM')=='1':return False
    if db is not None:return is_named(db)
    with SessionLocal() as session:return is_named(session)

def is_named(db):
    row=db.get(ManagementSetting,'server_identity')
    return bool(row and str(row.value.get('name','')).strip())

def identity():
    with SessionLocal() as db:
        row=db.get(ManagementSetting,'server_identity')
        name=row.value.get('name') if row else None
    return {'name':name or os.getenv('CLASSROOM_NAME') or socket.gethostname(),'named':bool(name)}
