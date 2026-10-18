param([string]$Runtime = '')
# Installs the speech dependencies into the bundled Python itself. Links to
# developer virtualenvs (.pth with absolute paths) are removed: the installed
# application must not depend on folders that exist only on the build PC.
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
if (!$Runtime) { $Runtime = Join-Path $root 'local_ai/voice/runtime' }
$python = Join-Path $Runtime 'python.exe'
if (!(Test-Path -LiteralPath $python)) { throw "Voice runtime python.exe was not found: $python" }
$site = Join-Path $Runtime 'Lib/site-packages'
$runtimeFull = (Resolve-Path -LiteralPath $Runtime).Path.TrimEnd('\') + '\'
Get-ChildItem -LiteralPath $site -Filter '*.pth' | ForEach-Object {
    $file = $_
    $external = Get-Content -LiteralPath $file.FullName | Where-Object {
        $line = $_.Trim()
        $line -and !$line.StartsWith('#') -and !$line.StartsWith('import') -and [IO.Path]::IsPathRooted($line) -and
            !([IO.Path]::GetFullPath($line).TrimEnd('\') + '\').StartsWith($runtimeFull, [StringComparison]::OrdinalIgnoreCase)
    }
    if ($external) {
        Write-Output "Removing $($file.Name): $($external -join ', ')"
        Remove-Item -LiteralPath $file.FullName
    }
}
# The runtime is a private copy of a uv-managed Python: its Lib/EXTERNALLY-MANAGED
# marker blocks pip, and ensurepip ignores PIP_* variables, so the marker is moved
# aside while packages are installed and put back afterwards.
$marker = Join-Path $Runtime 'Lib/EXTERNALLY-MANAGED'
$markerAside = "$marker.disabled"
if (Test-Path -LiteralPath $marker) { Move-Item -LiteralPath $marker -Destination $markerAside -Force }
try {
    # Copies of the runtime have ended up with files from two pip versions mixed
    # together; reinstall pip from the interpreter's own wheel before using it.
    Get-ChildItem -LiteralPath $site -Directory | Where-Object { $_.Name -eq 'pip' -or $_.Name -like 'pip-*.dist-info' } | Remove-Item -Recurse -Force
    & $python -m ensurepip --default-pip
    if ($LASTEXITCODE) { throw 'pip could not be restored in the voice runtime' }
    & $python -m pip install --no-deps --no-warn-script-location -r (Join-Path $root 'local_ai/voice-requirements.lock.txt') --extra-index-url https://download.pytorch.org/whl/cu128
    if ($LASTEXITCODE) { throw 'Voice dependencies failed to install' }
} finally {
    if (Test-Path -LiteralPath $markerAside) { Move-Item -LiteralPath $markerAside -Destination $marker -Force }
}
& $python -I (Join-Path $PSScriptRoot 'check_voice_runtime.py')
if ($LASTEXITCODE) { throw 'Voice runtime is not self-contained' }
