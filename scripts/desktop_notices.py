"""Collect third-party license notices into the distributable; no user data."""
from importlib.metadata import distributions
from pathlib import Path
import sys
root=Path(__file__).resolve().parents[1]
parts=['Third-party software notices for Dispetcher112 desktop.\n']
for dist in sorted(distributions(),key=lambda d:d.metadata.get('Name','').lower()):
    parts.append('\n'+'='*72+'\n'+dist.metadata.get('Name','')+' '+dist.version+'\n')
    parts.append('Homepage: '+str(dist.metadata.get('Home-page',''))+'\n')
    for file in dist.files or []:
        if any(word in str(file).lower() for word in ['license','copying','notice']) and str(file).lower().endswith(('.txt','.md','license','copying','notice')):
            path=Path(dist.locate_file(file))
            if path.is_file() and path.stat().st_size<500000:
                parts.append(str(file)+'\n'+path.read_text(encoding='utf-8',errors='replace')+'\n')
license=Path(sys.base_prefix)/'LICENSE.txt'
if license.exists(): parts.append('\nPython license\n'+license.read_text(encoding='utf-8',errors='replace'))
(root/'packaging/THIRD_PARTY_NOTICES.txt').write_text(''.join(parts),encoding='utf-8')
