$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path $PSScriptRoot -Parent)
if (-not (Test-Path '.venv/Scripts/python.exe')) { python -m venv .venv }
& .venv/Scripts/python.exe -c 'import fastapi, uvicorn, sqlalchemy, psycopg, alembic, argon2, multipart'
if ($LASTEXITCODE -ne 0) {
  & .venv/Scripts/python.exe -m pip install -r apps/api/requirements.lock.txt
  if ($LASTEXITCODE -ne 0) { throw 'Не удалось установить серверные зависимости' }
}
if (-not (Test-Path 'dist/index.html')) {
  if (-not (Test-Path 'node_modules')) { npm ci }
  npm run build
  if ($LASTEXITCODE -ne 0) { throw 'Не удалось собрать интерфейс' }
}
if ((Test-Path '.env') -and (Select-String -Path '.env' -Pattern '^DATABASE_URL=postgresql' -Quiet)) {
  docker compose --env-file .env -f deploy/compose.yaml up -d db
  if ($LASTEXITCODE -ne 0) { throw 'Запустите Docker Desktop и повторите запуск' }
}
& .venv/Scripts/python.exe run.py
