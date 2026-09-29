# Build with: .venv/Scripts/python.exe -m PyInstaller packaging/desktop.spec --noconfirm
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules
root=Path(SPECPATH).parent
migration_data=[(str(p),str(p.parent.relative_to(root))) for p in (root/'apps/api/migrations').rglob('*.py')]
data=[(str(root/'packaging/assets'),'packaging/assets'),(str(root/'dist/index.html'),'dist'),(str(root/'dist/assets'),'dist/assets'),(str(root/'content/classifier.json'),'content'),(str(root/'alembic.ini'),'.'),
      (str(root/'packaging/QUICKSTART.txt'),'.'),(str(root/'packaging/THIRD_PARTY_NOTICES.txt'),'.')]+migration_data+collect_data_files('alembic')+collect_data_files('spellchecker')+collect_data_files('reportlab')
a=Analysis([str(root/'packaging/desktop_launcher.py')],pathex=[str(root)],binaries=[],datas=data,
    hiddenimports=collect_submodules('apps.api.app')+['local_ai.engine','webview','webview.platforms.edgechromium','sqlalchemy.dialects.sqlite','uvicorn.logging','uvicorn.loops.asyncio','uvicorn.protocols.http.h11_impl','uvicorn.lifespan.on'],
    hookspath=[],runtime_hooks=[],excludes=['pytest','psycopg','psycopg_binary','bs4','pypdf','httpx','numpy','pandas','matplotlib'],noarchive=False)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='Dispetcher112',icon=str(root/'packaging/assets/trainer.ico'),debug=False,bootloader_ignore_signals=False,strip=False,upx=False,console=False,disable_windowed_traceback=False)
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='Dispetcher112')
