param([string]$SevenZip = 'C:/Program Files/7-Zip/7z.exe', [string]$PreparedSpeech = '')
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$tag = 'two-dds-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
$work = Join-Path $root "build/$tag"
$release = Join-Path $root "release/Dispetcher112-0.8.20-$tag"
$archive = "$release.exe"
$python = Join-Path $root '.venv/Scripts/python.exe'
if ((Test-Path -LiteralPath $work) -or (Test-Path -LiteralPath $release) -or (Test-Path -LiteralPath $archive)) { throw 'Output already exists; no files were replaced.' }
if (!(Test-Path -LiteralPath $SevenZip)) { throw '7-Zip not found.' }
New-Item -ItemType Directory -Path $work | Out-Null
Push-Location $root
try {
    & npx tsc --noEmit --incremental false
    if ($LASTEXITCODE) { throw 'TypeScript check failed.' }
    & npx vite build --outDir "$work/frontend"
    if ($LASTEXITCODE) { throw 'Frontend build failed.' }
    $env:TWO_DDS_FRONTEND_DIR = Join-Path $work 'frontend'
    & $python -m PyInstaller packaging/two_dds.spec --noconfirm --distpath $release --workpath "$work/pyinstaller"
    if ($LASTEXITCODE) { throw 'PyInstaller failed.' }
    $app = Join-Path $release 'Dispetcher112'
    $ai = Join-Path $app 'local_ai'
    New-Item -ItemType Directory -Path $ai | Out-Null
    foreach ($name in @('config.json','manifest.json','README.md','LICENSE-llama.cpp.txt','LICENSE-Qwen.txt','voice_worker.py','speech_text.py')) {
        Copy-Item -LiteralPath (Join-Path $root "local_ai/$name") -Destination (Join-Path $ai $name)
    }
    foreach ($relative in @('runtime/cpu','runtime/vulkan','voice/runtime','voice/models/gigaam','voice/piper/FINAL_MODELS_29800','voice/builtin','voice/fillers')) {
        $source = Join-Path $root "local_ai/$relative"
        $target = Join-Path $ai $relative
        if (!(Test-Path -LiteralPath $source)) { throw "Missing: $source" }
        New-Item -ItemType Directory -Path $target -Force | Out-Null
        & robocopy.exe $source $target /E /NFL /NDL /NJH /NJS /NP | Out-Null
        if ($LASTEXITCODE -ge 8) { throw "Copy failed: $relative" }
        $global:LASTEXITCODE = 0
    }
    New-Item -ItemType Directory -Path (Join-Path $ai 'models') | Out-Null
    foreach ($name in @('Qwen3-4B-Instruct-2507-Q4_K_M.gguf', 'Qwen2.5-1.5B-Instruct-Q4_K_M.gguf', 'qwen-dds-1000-f32.gguf')) {
        Copy-Item -LiteralPath (Join-Path $root "local_ai/models/$name") -Destination (Join-Path $ai "models/$name")
    }
    Copy-Item -LiteralPath (Join-Path $root 'packaging/QUICKSTART.txt') -Destination (Join-Path $app 'README.txt')
    if ($PreparedSpeech) {
        if (!(Test-Path -LiteralPath (Join-Path $PreparedSpeech 'manifest.json'))) { throw 'Prepared speech manifest not found.' }
        & robocopy.exe $PreparedSpeech (Join-Path $ai 'voice/builtin') /E /NFL /NDL /NJH /NJS /NP | Out-Null
        if ($LASTEXITCODE -ge 8) { throw 'Prepared speech copy failed.' }
        $global:LASTEXITCODE = 0
    }
    Copy-Item -LiteralPath (Join-Path $root 'packaging/TWO_DDS_TESTING.txt') -Destination (Join-Path $release 'README-two-dds.txt')
    & $SevenZip a -t7z ('-sfx' + (Join-Path (Split-Path $SevenZip -Parent) '7z.sfx')) -mx=0 -mmt=on $archive $release
    if ($LASTEXITCODE) { throw 'Portable EXE creation failed.' }
    $hash = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
    "$hash  $(Split-Path $archive -Leaf)" | Set-Content -LiteralPath "$archive.sha256" -Encoding ascii
    Write-Output "APP: $(Join-Path $app 'Dispetcher112.exe')"
    Write-Output "PORTABLE: $archive"
    Write-Output "SHA256: $hash"
} finally {
    Pop-Location
}
