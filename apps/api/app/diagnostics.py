"""Bounded technical logs. Request bodies, cookies and authorization are never logged."""
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
import json
import logging
from logging.handlers import RotatingFileHandler
import os
import re
import threading

request_id=ContextVar('request_id',default='')
_lock=threading.Lock()
_logger=None

def scrub(text):
    text=str(text)[:6000]
    text=re.sub(r'(?i)(password|пароль|authorization|api[_-]?key|token|cookie)([\s\"\x27:=]+)[^\s,;\r\n}]+',r'\1\2[REDACTED]',text)
    text=re.sub(r'(?i)Bearer\s+\S+','Bearer [REDACTED]',text)
    text=re.sub(r'(https?://[^\s?]+)\?\S+',r'\1?[REDACTED]',text)
    return text

def log_dir():
    path=Path(os.getenv('DATA_DIR',str(Path(__file__).resolve().parents[3]/'var')))/'logs'
    path.mkdir(parents=True,exist_ok=True)
    return path

def event(event_name,**fields):
    global _logger
    try:
        with _lock:
            if _logger is None:
                _logger=logging.getLogger('training112.diagnostics');_logger.setLevel(logging.INFO);_logger.propagate=False
                handler=RotatingFileHandler(log_dir()/'diagnostics.jsonl',maxBytes=5_000_000,backupCount=5,encoding='utf-8')
                handler.setFormatter(logging.Formatter('%(message)s'));_logger.addHandler(handler)
            record={'at':datetime.now(timezone.utc).isoformat(),'event':event_name,'request_id':request_id.get(),
                    **{k:scrub(v) if isinstance(v,str) else v for k,v in fields.items()}}
            # Alembic's fileConfig may disable existing loggers during startup migrations.
            _logger.disabled=False
            _logger.info(json.dumps(record,ensure_ascii=False,default=str))
    except Exception:
        # Disk failures must not turn a successful training action into a failed one.
        pass
