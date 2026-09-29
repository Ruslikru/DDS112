"""Real loopback discovery tests, including foreign servers and unavailable saved URLs."""
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'packaging'))
from lan_discovery import DiscoveryServer, discover, verify, APP

@pytest.fixture
def server():
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            data=json.dumps(getattr(http,'payload',{'app':APP,'name':'Учебный класс','token':'test-server-unique'})).encode()
            self.send_response(200);self.end_headers();self.wfile.write(data)
    http=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    worker=threading.Thread(target=http.serve_forever,daemon=True);worker.start()
    responder=DiscoveryServer(http.server_port,port=0);responder.start()
    yield http,responder
    responder.stop();http.shutdown();http.server_close();worker.join(2)

def test_discovery_finds_live_server_without_address(server):
    http,responder=server
    http.payload={'app':APP,'name':'Учебный класс','token':'test-server-unique','setup_policy':'confirm-name-each-start'}
    found=discover(timeout=.3,port=responder.port,targets=['127.0.0.1'])
    assert len(found)==1 and found[0]['name']=='Учебный класс'
    assert found[0]['url']==f'http://127.0.0.1:{http.server_port}'
    assert found[0]['setup_policy']=='confirm-name-each-start'

def test_saved_available_server_is_discoverable_without_udp(server):
    http,responder=server
    url=f'http://127.0.0.1:{http.server_port}'
    assert discover(previous=url,timeout=.05,port=responder.port+1,targets=['127.0.0.1'])[0]['url']==url

def test_unavailable_and_invalid_addresses_are_not_offered():
    assert verify('file:///tmp/test') is None
    assert verify('http://user:pass@localhost:8765') is None
    assert verify('http://127.0.0.1:1') is None

def test_discovery_ignores_unrelated_datagram(server):
    import socket
    http,responder=server
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as probe:
        probe.settimeout(.1)
        probe.sendto(b'{"protocol":"another-app","nonce":"00000000000000000000000000000000"}',('127.0.0.1',responder.port))
        with pytest.raises(socket.timeout):probe.recvfrom(2048)


def test_foreign_health_and_non_object_response_are_not_offered(server):
    http,responder=server
    url=f'http://127.0.0.1:{http.server_port}'
    http.payload={'app':'OtherProduct'}
    assert verify(url) is None
    http.payload=[]
    assert verify(url) is None
