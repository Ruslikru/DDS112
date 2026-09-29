# One-time local update: waits for the user to close the existing application.
# Does not stop processes, delete files, or copy a database/model over user data.
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Split-Path $PSScriptRoot -Parent))
$stagedRoot = [IO.Path]::GetFullPath((Join-Path $projectRoot 'tmp/ui-050/portable'))
$installedRoot = [IO.Path]::GetFullPath((Join-Path $projectRoot 'Dispetcher112'))
$installedExe = Join-Path $installedRoot 'Dispetcher112.exe'
$statusFile = Join-Path $projectRoot 'tmp/ui-050/update-status.json'
function Set-UpdateStatus([string]$State, [string]$Message) {
    @{state=$State; message=$Message; at=(Get-Date).ToString('o'); version='0.5.0'} |
        ConvertTo-Json | Set-Content -LiteralPath $statusFile -Encoding utf8
}
try {
    if (!$stagedRoot.StartsWith($projectRoot + [IO.Path]::DirectorySeparatorChar) -or
        $installedRoot -ne (Join-Path $projectRoot 'Dispetcher112')) { throw 'Unexpected update path' }
    $report=Get-Content -LiteralPath (Join-Path $projectRoot 'tmp/ui-050/packaged-check/self-test.json') -Raw | ConvertFrom-Json
    if (!$report.ok -or $report.version -ne '0.5.0') { throw 'Packaged verification has not passed' }
    Set-UpdateStatus 'waiting_for_close' 'Сохраните карточку и закройте открытое окно приложения обычным способом.'
    do {
        $running=@(Get-Process Dispetcher112 -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $installedExe })
        if ($running.Count) { $running | Wait-Process -ErrorAction SilentlyContinue }
    } while ($running.Count)
    Set-UpdateStatus 'applying' 'Обновление файлов приложения; база и локальная модель сохраняются.'
    & robocopy $stagedRoot $installedRoot /E /XJ /R:2 /W:1 /NFL /NDL /NJH /NJS |
        Out-File -LiteralPath (Join-Path $projectRoot 'tmp/ui-050/update-copy.log') -Encoding utf8
    if ($LASTEXITCODE -ge 8) { throw "File copy failed: $LASTEXITCODE" }
    if ((Get-FileHash -LiteralPath $installedExe).Hash -ne (Get-FileHash -LiteralPath (Join-Path $stagedRoot 'Dispetcher112.exe')).Hash) { throw 'Executable hash mismatch' }
    Set-UpdateStatus 'applied' 'Обновление установлено. Запускается версия 0.5.0.'
    Start-Process -FilePath $installedExe -WindowStyle Hidden
} catch {
    Set-UpdateStatus 'failed' $_.Exception.Message
    exit 1
}
