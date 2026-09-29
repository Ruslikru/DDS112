param([string]$InnoCompiler = '')
$ErrorActionPreference='Stop'
$projectRoot=Split-Path $PSScriptRoot -Parent
Push-Location $projectRoot
try {
    $python=Join-Path $projectRoot '.venv/Scripts/python.exe'
    if (!(Test-Path -LiteralPath $python)) { throw 'Create .venv and install apps/api/requirements.lock.txt first.' }
    if (!$InnoCompiler) {
        $candidates=@((Join-Path $projectRoot 'tmp/installer/inno/ISCC.exe'),'C:/Program Files (x86)/Inno Setup 6/ISCC.exe','C:/Program Files/Inno Setup 6/ISCC.exe')
        $InnoCompiler=$candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    }
    if (!$InnoCompiler) { throw 'Pass -InnoCompiler with the path to ISCC.exe.' }
    & $python -m pip install -r packaging/build-requirements.txt
    if ($LASTEXITCODE) { throw 'Build dependencies failed' }
    npm ci
    if ($LASTEXITCODE) { throw 'npm ci failed' }
    npx tsc --noEmit
    if ($LASTEXITCODE) { throw 'TypeScript failed' }
    npx vite build --outDir tmp/frontend-build
    if ($LASTEXITCODE) { throw 'Vite failed' }
    robocopy tmp/frontend-build dist /E /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -lt 8) { $global:LASTEXITCODE=0 }
    if ($LASTEXITCODE) { throw 'Web build failed' }
    & $python scripts/desktop_notices.py
    if ($LASTEXITCODE) { throw 'License notices failed' }
    & $python -m PyInstaller packaging/desktop.spec --noconfirm --distpath build/desktop-dist --workpath build/desktop-work
    if ($LASTEXITCODE) { throw 'PyInstaller failed' }
    & $InnoCompiler packaging/installer.iss
    if ($LASTEXITCODE) { throw 'Installer compilation failed' }
    $versionLine=Get-Content packaging/installer.iss | Select-String '^#define AppVersion "([^"]+)"$'
    $version=$versionLine.Matches[0].Groups[1].Value
    $setup=Join-Path $projectRoot "release/Dispetcher112-$version-installer/Dispetcher112-Setup-$version-win-x64.exe"
    $checksumLines=Get-ChildItem -LiteralPath (Split-Path $setup) -File | Where-Object { $_.Extension -in '.exe','.bin' } | Sort-Object Name | ForEach-Object { (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()+'  '+$_.Name }
    $checksumLines | Set-Content -Encoding ascii (Join-Path (Split-Path $setup) 'SHA256SUMS.txt')
    Copy-Item packaging/QUICKSTART.txt (Join-Path (Split-Path $setup) 'README.txt') -Force
    Write-Output $setup
} finally { Pop-Location }
