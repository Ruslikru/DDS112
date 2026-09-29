"""LAN discovery: only identify live Training112 servers; never trust a supplied URL."""
import json
import secrets
import socket
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit

PORT = 38765
APP = 'Dispetcher112.Desktop'
PROTOCOL = 'training112-discovery-v1'


def verify(url):
    try:
        parts = urlsplit(url)
        if parts.scheme not in ('http', 'https') or not parts.hostname or parts.username or parts.path not in ('', '/'):
            return None
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(url.rstrip('/') + '/desktop-health', timeout=1.2) as response:
            data = json.loads(response.read(4096))
        if not isinstance(data, dict) or data.get('app') != APP:
            return None
        return {'url': url.rstrip('/'), 'name': str(data.get('name') or parts.hostname)[:100],
                'id': str(data.get('token') or url), 'setup_policy': data.get('setup_policy')}
    except (OSError, ValueError):
        return None


class DiscoveryServer:
    def __init__(self, http_port, name=None, port=PORT):
        self.http_port = http_port
        self.name = name or socket.gethostname()
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind(('', port))
        self.socket.settimeout(.3)
        self.port = self.socket.getsockname()[1]
        self.closed = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)

    def start(self):
        self.thread.start()

    def run(self):
        while not self.closed.is_set():
            try:
                packet, address = self.socket.recvfrom(2048)
                query = json.loads(packet)
                if not isinstance(query, dict) or query.get('protocol') != PROTOCOL:
                    continue
                nonce = query.get('nonce')
                if not isinstance(nonce, str) or len(nonce) != 32:
                    continue
                reply = {'protocol': PROTOCOL, 'nonce': nonce, 'port': self.http_port}
                self.socket.sendto(json.dumps(reply).encode(), address)
            except socket.timeout:
                continue
            except (ValueError, OSError):
                continue

    def stop(self):
        self.closed.set()
        self.socket.close()
        if self.thread.is_alive():
            self.thread.join(1)


def discover(previous='', timeout=1.4, port=PORT, targets=None):
    nonce = secrets.token_hex(16)
    query = json.dumps({'protocol': PROTOCOL, 'nonce': nonce}).encode()
    candidates = {previous.rstrip('/')} if previous else set()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        probe.settimeout(.15)
        for host in targets or ['255.255.255.255', '127.0.0.1']:
            try:
                probe.sendto(query, (host, port))
            except OSError:
                pass
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and len(candidates) < 32:
            try:
                packet, address = probe.recvfrom(2048)
                reply = json.loads(packet)
                if not isinstance(reply, dict) or reply.get('protocol') != PROTOCOL or reply.get('nonce') != nonce:
                    continue
                http_port = reply.get('port')
                if isinstance(http_port, int) and 1 <= http_port <= 65535:
                    candidates.add(f'http://{address[0]}:{http_port}')
            except (socket.timeout, ValueError, OSError):
                continue
    with ThreadPoolExecutor(max_workers=8) as pool:
        found = [item for item in pool.map(verify, sorted(candidates)) if item]
    # A server on this PC may answer both broadcast and loopback.
    unique = {}
    for item in found:
        key = item['id']
        if key not in unique or '127.0.0.1' in item['url']:
            unique[key] = item
    return sorted(unique.values(), key=lambda item: (item['name'], item['url']))
