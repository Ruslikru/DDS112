param([string]$SevenZip = 'C:/Program Files/7-Zip/7z.exe', [string]$OutputSuffix = '')
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$versionLine = Get-Content (Join-Path $root 'packaging/installer.iss') | Select-String '^#define AppVersion "([^"]+)"$'
if (!$versionLine) { throw 'AppVersion was not found in packaging/installer.iss' }
$version = $versionLine.Matches[0].Groups[1].Value
if ($OutputSuffix -and $OutputSuffix -notmatch '^-[a-zA-Z0-9-]+$') { throw 'OutputSuffix must start with a dash and contain only letters, numbers or dashes.' }
$releaseName = "Dispetcher112-$version$OutputSuffix-portable"
$source = Join-Path $root 'build/desktop-dist/Dispetcher112'
$destination = Join-Path $root "release/$releaseName"
$archive = Join-Path $root "release/$releaseName.exe"
if (!(Test-Path -LiteralPath (Join-Path $source 'Dispetcher112.exe'))) { throw 'Build the desktop application first.' }
if (!(Test-Path -LiteralPath $SevenZip)) { throw '7-Zip was not found. Pass -SevenZip with its full path.' }
if (Test-Path -LiteralPath $destination) { throw "Portable directory already exists: $destination" }
if (Test-Path -LiteralPath $archive) { throw "Portable archive already exists: $archive" }

function Copy-Tree([string]$from, [string]$to) {
    if (!(Test-Path -LiteralPath $from)) { throw "Required directory is missing: $from" }
    New-Item -ItemType Directory -Force -Path $to | Out-Null
    & robocopy.exe $from $to /E /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "Copy failed: $from -> $to (robocopy code $LASTEXITCODE)" }
    $global:LASTEXITCODE = 0
}

function Copy-Required([string]$relative, [string]$target) {
    $from = Join-Path $root $relative
    if (!(Test-Path -LiteralPath $from)) { throw "Required file is missing: $from" }
    New-Item -ItemType Directory -Force -Path (Split-Path $target -Parent) | Out-Null
    Copy-Item -LiteralPath $from -Destination $target
}

New-Item -ItemType Directory -Force -Path $destination | Out-Null
Copy-Tree $source $destination
$ai = Join-Path $destination 'local_ai'
foreach ($name in @('config.json', 'manifest.json', 'README.md', 'LICENSE-llama.cpp.txt', 'LICENSE-Qwen.txt', 'voice_worker.py', 'speech_text.py')) {
    Copy-Required "local_ai/$name" (Join-Path $ai $name)
}
foreach ($item in @(
    @('local_ai/runtime/cpu', 'local_ai/runtime/cpu'),
    @('local_ai/runtime/vulkan', 'local_ai/runtime/vulkan'),
    @('local_ai/voice/runtime', 'local_ai/voice/runtime'),
    @('local_ai/voice/models', 'local_ai/voice/models'),
    @('local_ai/voice/builtin', 'local_ai/voice/builtin'),
    @('local_ai/voice/fillers', 'local_ai/voice/fillers')
)) {
    Copy-Tree (Join-Path $root $item[0]) (Join-Path $destination $item[1])
}
foreach ($name in @('Qwen3-4B-Instruct-2507-Q4_K_M.gguf', 'Qwen3-0.6B-Q4_K_M.gguf')) {
    Copy-Required "local_ai/models/$name" (Join-Path $ai "models/$name")
}
Copy-Required 'packaging/QUICKSTART.txt' (Join-Path $destination 'README.txt')

# The SFX opens a folder picker. It extracts the complete portable application
# to the user's chosen location; no Python, Node.js or 7-Zip is required there.
Push-Location (Join-Path $root 'release')
try {
    & $SevenZip a -t7z ('-sfx' + (Join-Path (Split-Path $SevenZip -Parent) '7z.sfx')) -mx=0 -mmt=on $archive (Split-Path $destination -Leaf)
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the single-file portable package.' }
} finally { Pop-Location }
$hash = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
"$hash  $(Split-Path $archive -Leaf)" | Set-Content -Encoding ascii ($archive + '.sha256')
Write-Output $archive
