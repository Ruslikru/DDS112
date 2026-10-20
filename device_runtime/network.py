"""LAN addresses for discovery and the administrator's connection information."""
import ipaddress
import socket
import os
import time


_cache=(0,[])

def windows_adapters():
    if os.name!='nt':return []
    import ctypes
    from ctypes import wintypes
    class Address(ctypes.Structure):pass
    Address._fields_=[('next',ctypes.POINTER(Address)),('ip',ctypes.c_char*16),('mask',ctypes.c_char*16),('context',wintypes.DWORD)]
    class Adapter(ctypes.Structure):pass
    Adapter._fields_=[('next',ctypes.POINTER(Adapter)),('combo',wintypes.DWORD),('name',ctypes.c_char*260),('description',ctypes.c_char*132),('address_length',wintypes.UINT),('address',ctypes.c_ubyte*8),('index',wintypes.DWORD),('kind',wintypes.UINT),('dhcp',wintypes.UINT),('current',ctypes.POINTER(Address)),('ips',Address),('gateway',Address)]
    size=wintypes.ULONG(0)
    api=ctypes.WinDLL('iphlpapi').GetAdaptersInfo
    if api(None,ctypes.byref(size))!=111 or not 0<size.value<1_000_000:return []
    buffer=ctypes.create_string_buffer(size.value)
    if api(buffer,ctypes.byref(size))!=0:return []
    rows=[];item=ctypes.cast(buffer,ctypes.POINTER(Adapter))
    while item and len(rows)<256:
        adapter=item.contents
        description=bytes(adapter.description).decode('utf-8','replace').casefold()
        virtual=any(word in description for word in ('vpn','virtual','hyper-v','tunnel','wireguard','tap-windows'))
        physical=adapter.kind in (6,71) and not virtual
        gateway=bytes(adapter.gateway.ip).decode('ascii','ignore')
        address=ctypes.pointer(adapter.ips)
        count=0
        while address and count<32:
            value=address.contents
            rows.append({'ip':bytes(value.ip).decode('ascii','ignore'),'mask':bytes(value.mask).decode('ascii','ignore'),'physical':physical,'gateway':gateway not in ('','0.0.0.0')})
            address=value.next;count+=1
        item=adapter.next
    return rows


def lan_addresses():
    global _cache
    if time.monotonic()-_cache[0]<30:return list(_cache[1])
    adapters=windows_adapters()
    found={row['ip'] for row in adapters}
    try:found.update(row[4][0] for row in socket.getaddrinfo(socket.gethostname(),None,socket.AF_INET))
    except OSError:pass
    preferred=None
    try:
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as probe:
            # UDP connect only chooses a local route; it sends no packets.
            probe.connect(('192.0.2.1',9));preferred=probe.getsockname()[0]
            found.add(preferred)
    except OSError:pass
    def usable(value):
        try:
            ip=ipaddress.ip_address(value)
            return ip.version==4 and not (ip.is_loopback or ip.is_link_local or ip.is_unspecified or ip.is_multicast)
        except ValueError:return False
    physical={row['ip'] for row in adapters if row['physical']}
    gateway={row['ip'] for row in adapters if row['physical'] and row['gateway']}
    values=sorted((value for value in found if usable(value)),key=lambda value:(value not in gateway,value not in physical,value!=preferred,not ipaddress.ip_address(value).is_private,int(ipaddress.ip_address(value))))
    _cache=(time.monotonic(),values)
    return list(values)
