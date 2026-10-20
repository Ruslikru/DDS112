"""Inference destination follows the originating workstation, including background jobs."""
from contextvars import ContextVar
from contextlib import contextmanager

device_id=ContextVar('ai_device_id',default=None)

@contextmanager
def on_device(wid):
    token=device_id.set(wid)
    try:yield
    finally:device_id.reset(token)
