from pathlib import Path
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

root = Path(SPECPATH).parent
frontend = Path(os.environ['TWO_DDS_FRONTEND_DIR'])
migration_data = [(str(file), str(file.parent.relative_to(root))) for file in (root / 'apps/api/migrations').rglob('*.py')]
data = [(str(root / 'packaging/assets'), 'packaging/assets'), (str(frontend / 'index.html'), 'dist'),
        (str(frontend / 'assets'), 'dist/assets'), (str(root / 'content/classifier.json'), 'content'),
        (str(root / 'alembic.ini'), '.'), (str(root / 'packaging/QUICKSTART.txt'), '.'),
        (str(root / 'packaging/THIRD_PARTY_NOTICES.txt'), '.')]
data += migration_data + collect_data_files('alembic') + collect_data_files('spellchecker') + collect_data_files('reportlab')
analysis = Analysis([str(root / 'packaging/desktop_launcher.py')], pathex=[str(root)], binaries=[], datas=data,
                    hiddenimports=collect_submodules('apps.api.app') + ['local_ai.engine', 'webview', 'webview.platforms.edgechromium',
                    'sqlalchemy.dialects.sqlite', 'uvicorn.logging', 'uvicorn.loops.asyncio', 'uvicorn.protocols.http.h11_impl', 'uvicorn.lifespan.on'],
                    hookspath=[], runtime_hooks=[], excludes=['pytest', 'psycopg', 'psycopg_binary', 'bs4', 'pypdf', 'httpx', 'numpy', 'pandas', 'matplotlib'], noarchive=False)
archive = PYZ(analysis.pure)
executable = EXE(archive, analysis.scripts, [], exclude_binaries=True, name='Dispetcher112',
                 icon=str(root / 'packaging/assets/trainer.ico'), debug=False, bootloader_ignore_signals=False,
                 strip=False, upx=False, console=False, disable_windowed_traceback=False)
collection = COLLECT(executable, analysis.binaries, analysis.datas, strip=False, upx=False, name='Dispetcher112')
