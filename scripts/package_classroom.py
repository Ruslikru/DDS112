"""Package the prebuilt desktop app and verified CPU model, excluding user data."""
from pathlib import Path
import hashlib
import json
import shutil
import zipfile

root=Path(__file__).resolve().parents[1]
version='0.8.0'
source=root/'build/desktop-dist/Dispetcher112'
target=root/'release'/f'Dispetcher112-{version}'
manifest=json.loads((root/'local_ai/manifest.json').read_text('utf-8'))
model=root/'local_ai'/manifest['file']
if not (source/'Dispetcher112.exe').is_file():raise SystemExit('Build packaging/desktop.spec first')
if hashlib.file_digest(model.open('rb'),'sha256').hexdigest()!=manifest['sha256']:raise SystemExit('Model checksum mismatch')
shutil.copytree(source,target,dirs_exist_ok=True)
shutil.copytree(root/'dist',target/'_internal/dist',dirs_exist_ok=True)
for name in ('config.json','manifest.json','README.md'):
 (target/'local_ai').mkdir(parents=True,exist_ok=True)
 shutil.copy2(root/'local_ai'/name,target/'local_ai'/name)
for p in (root/'local_ai').glob('LICENSE*'):shutil.copy2(p,target/'local_ai'/p.name)
shutil.copytree(root/'local_ai/runtime/cpu',target/'local_ai/runtime/cpu',dirs_exist_ok=True)
shutil.copytree(root/'local_ai/runtime/vulkan',target/'local_ai/runtime/vulkan',dirs_exist_ok=True)
(target/'local_ai/models').mkdir(parents=True,exist_ok=True)
shutil.copy2(model,target/'local_ai'/manifest['file'])
shutil.copy2(root/'packaging/QUICKSTART.txt',target/'ПРОЧИТАЙТЕ.txt')
shutil.copy2(root/'docs/Учебные_серверы_0.8.md',target/'Изменения_0.8.md')
(target/'Настроить подключение.cmd').write_text('@start "" "%~dp0Dispetcher112.exe" --configure-classroom\n',encoding='ascii')
archive=target.parent/(target.name+'-win-x64.zip')
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=1) as z:
 for p in target.rglob('*'):
  if not p.is_file():continue
  if p.suffix in ('.db','.log') or p.name=='.env':raise RuntimeError(f'Unexpected user data: {p}')
  z.write(p,p.relative_to(target.parent),compress_type=zipfile.ZIP_STORED if p.suffix=='.gguf' else zipfile.ZIP_DEFLATED)
with archive.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
archive.with_suffix('.zip.sha256').write_text(digest+'  '+archive.name+'\n',encoding='ascii')
print(json.dumps({'folder':str(target),'archive':str(archive),'bytes':archive.stat().st_size,'sha256':digest}))
