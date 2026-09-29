"""Local launcher; reads .env without an additional dependency."""
import os
from pathlib import Path
root=Path(__file__).resolve().parent
os.chdir(root)
env=root/'.env'
if env.exists():
    for line in env.read_text(encoding='utf-8-sig').splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            k,v=line.split('=',1); os.environ.setdefault(k.strip(),v.strip().strip('"'))
if __name__=='__main__':
    import uvicorn
    uvicorn.run('apps.api.app.main:app',host='0.0.0.0',port=int(os.getenv('PORT','8000')))
