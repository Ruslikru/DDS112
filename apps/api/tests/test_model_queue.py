"""Concurrent Qwen requests wait, and foreground requests precede queued reviews."""
import threading,time
import pytest
from local_ai.engine import LocalEngine,AIUnavailable


def test_queued_requests_run_once_in_priority_order(tmp_path):
    engine=LocalEngine(data=tmp_path);engine.lock.acquire();order=[];errors=[]
    def work(name,priority):
        try:
            engine.acquire_request(priority,timeout=2)
            try:order.append(name)
            finally:engine.release_request()
        except Exception as error:errors.append(error)
    threads=[]
    for name,priority in [('review',10),('phone',0),('assistant',0)]:
        thread=threading.Thread(target=work,args=(name,priority));thread.start();threads.append(thread)
        deadline=time.monotonic()+1
        while len(engine.waiters)<len(threads) and time.monotonic()<deadline:time.sleep(.005)
        assert len(engine.waiters)==len(threads)
    engine.release_request()
    for thread in threads:thread.join(3)
    assert not errors and order==['phone','assistant','review']
    assert not engine.waiters and not engine.lock.locked()


def test_timeout_removes_waiter_without_unlocking_active_request(tmp_path):
    engine=LocalEngine(data=tmp_path);engine.lock.acquire()
    with pytest.raises(AIUnavailable,match='Запрос не выполнен'):
        engine.acquire_request(timeout=.01)
    assert not engine.waiters and engine.lock.locked()
    engine.release_request()
    engine.acquire_request(timeout=.01);engine.release_request()
