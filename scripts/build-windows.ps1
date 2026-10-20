param([string]$InnoCompiler = '', [string]$BuildTag = '20261020-r13')
$ErrorActionPreference='Stop'
$projectRoot=Split-Path $PSScriptRoot -Parent
Push-Location $projectRoot
try {
    if ($BuildTag -notmatch '^[a-zA-Z0-9-]+$') { throw 'Invalid BuildTag' }
    $python=Join-Path $projectRoot '.venv/Scripts/python.exe'
    if (!(Test-Path -LiteralPath $python)) { throw 'Create .venv and install apps/api/requirements.lock.txt first.' }
    if (!$InnoCompiler) {
        $candidates=@((Join-Path $projectRoot 'tmp/installer/inno/ISCC.exe'),'C:/Program Files (x86)/Inno Setup 6/ISCC.exe','C:/Program Files/Inno Setup 6/ISCC.exe')
        $InnoCompiler=$candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    }
    if (!$InnoCompiler) { throw 'Pass -InnoCompiler with the path to ISCC.exe.' }
    $versionLine=Get-Content packaging/installer.iss | Select-String '^#define AppVersion "([^"]+)"$'
    $version=$versionLine.Matches[0].Groups[1].Value
    $buildFolder="build/desktop-dist-$version-$BuildTag/Dispetcher112"
    $releaseName="Dispetcher112-fix-bilets-$BuildTag"
    $payload=Join-Path $projectRoot "release/$releaseName"
    $output=Join-Path $projectRoot "release/Dispetcher112-$version-$BuildTag-installer"
    if ((Test-Path -LiteralPath $payload) -or (Test-Path -LiteralPath $output)) { throw 'Use a fresh BuildTag; existing releases are preserved.' }
    & $python scripts/check_starter_audio.py --report "output/starter-audio-$BuildTag.json"
    if ($LASTEXITCODE) { throw 'The six starter tickets must already have complete packaged speech.' }
    npm run build
    if ($LASTEXITCODE) { throw 'Frontend build failed' }
    & $python -m PyInstaller packaging/desktop.spec --noconfirm --distpath "build/desktop-dist-$version-$BuildTag" --workpath "build/desktop-work-$version-$BuildTag"
    if ($LASTEXITCODE) { throw 'PyInstaller failed' }
    & ./scripts/build-portable-folder.ps1 -BuildFolder $buildFolder -ReleaseName $releaseName
    & $python scripts/check_starter_audio.py --bundle $payload
    if ($LASTEXITCODE) { throw 'Packaged starter speech failed verification.' }
    & (Join-Path $payload 'local_ai/voice/runtime/python.exe') -I scripts/check_voice_runtime.py
    if ($LASTEXITCODE) { throw 'Voice runtime is not self-contained.' }
    & $python scripts/check_voice_paths.py --bundle $payload --report "output/voice-paths-$BuildTag.json"
    if ($LASTEXITCODE) { throw 'Packaged speech generation and recognition failed.' }
    & $InnoCompiler /Qp "/DPayloadDir=$payload" "/DBuildTag=$BuildTag" packaging/installer.iss
    if ($LASTEXITCODE) { throw 'Installer compilation failed' }
    $checksumLines=Get-ChildItem -LiteralPath $output -File | Where-Object { $_.Extension -in '.exe','.bin' } | Sort-Object Name | ForEach-Object { (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()+'  '+$_.Name }
    $checksumLines | Set-Content -Encoding ascii (Join-Path $output 'SHA256SUMS.txt')
    Copy-Item -LiteralPath packaging/QUICKSTART.txt -Destination (Join-Path $output 'README.txt')
    Write-Output $output
} finally { Pop-Location }
