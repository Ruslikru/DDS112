param(
    [string]$BuildFolder = 'build/desktop-dist-group-20261019-v4/Dispetcher112',
    [string]$ReleaseName = 'Dispetcher112-0.8.25-portable-20261019-v4'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$source = Join-Path $root $BuildFolder
$destination = Join-Path $root "release/$ReleaseName"
if (!(Test-Path -LiteralPath (Join-Path $source 'Dispetcher112.exe'))) { throw "Сборка не найдена: $source" }
if (Test-Path -LiteralPath $destination) { throw "Папка уже существует: $destination" }

function Copy-Tree([string]$from, [string]$to) {
    if (!(Test-Path -LiteralPath $from -PathType Container)) { throw "Не найдена папка: $from" }
    New-Item -ItemType Directory -Path $to -Force | Out-Null
    & robocopy.exe $from $to /E /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "Не удалось скопировать $from (код $LASTEXITCODE)" }
    $global:LASTEXITCODE = 0
}

function Copy-Required([string]$relative, [string]$target) {
    $from = Join-Path $root $relative
    if (!(Test-Path -LiteralPath $from -PathType Leaf)) { throw "Не найден файл: $from" }
    New-Item -ItemType Directory -Path (Split-Path $target -Parent) -Force | Out-Null
    Copy-Item -LiteralPath $from -Destination $target
}

New-Item -ItemType Directory -Path $destination | Out-Null
Copy-Tree $source $destination
$ai = Join-Path $destination 'local_ai'
foreach ($name in @('config.json', 'manifest.json', 'README.md', 'LICENSE-llama.cpp.txt', 'LICENSE-Qwen.txt', 'voice_worker.py', 'speech_text.py')) {
    Copy-Required "local_ai/$name" (Join-Path $ai $name)
}
foreach ($item in @(
    @('local_ai/runtime/cpu', 'local_ai/runtime/cpu'),
    @('local_ai/runtime/vulkan', 'local_ai/runtime/vulkan'),
    @('local_ai/voice/runtime-0.8.24b', 'local_ai/voice/runtime'),
    @('local_ai/voice/models/gigaam', 'local_ai/voice/models/gigaam'),
    @('local_ai/voice/piper/FINAL_MODELS_29800', 'local_ai/voice/piper/FINAL_MODELS_29800'),
    @('local_ai/voice/builtin', 'local_ai/voice/builtin'),
    @('local_ai/voice/fillers', 'local_ai/voice/fillers')
)) {
    Copy-Tree (Join-Path $root $item[0]) (Join-Path $destination $item[1])
}
foreach ($name in @('Qwen3-4B-Instruct-2507-Q4_K_M.gguf')) {
    Copy-Required "local_ai/models/$name" (Join-Path $ai "models/$name")
}

$target = Join-Path $destination 'Dispetcher112.exe'
$shell = New-Object -ComObject WScript.Shell
foreach ($mode in @(@('На одном ПК', '--local'), @('В локальной сети', '--lan'))) {
    $shortcut = $shell.CreateShortcut((Join-Path $destination ($mode[0] + '.lnk')))
    $shortcut.TargetPath = $target
    $shortcut.Arguments = $mode[1]
    $shortcut.WorkingDirectory = $destination
    $shortcut.IconLocation = "$target,0"
    $shortcut.Save()
    ('@echo off' + "`r`n" + 'start "" "%~dp0Dispetcher112.exe" ' + $mode[1]) |
        Set-Content -LiteralPath (Join-Path $destination ($mode[0] + '.cmd')) -Encoding ASCII
}
@'
Для работы на одном компьютере откройте ярлык «На одном ПК».
Первое окно — сервер. Повторный запуск этого же ярлыка открывает рабочее место студента.
Для локальной сети откройте ярлык «В локальной сети». Сразу появится логин и пароль.
При первом запуске войдите администратором и настройте сервер или рабочее место.
На новом ПК начальный пароль admin: 12345678. Существующие пароли сохраняются.
После настройки следующие запуски сразу открывают вход; студенту вход администратора не нужен.
Если перенесли папку, используйте соответствующий файл .cmd: «На одном ПК.cmd» или «В локальной сети.cmd».
Сам Dispetcher112.exe использует сохранённое подключение; на новом ПК настройка доступна после входа администратора.
Переносите папку целиком: нейросети находятся в local_ai.
Перед запуском закройте ранее открытые окна тренажёра.
Для входа выберите учётную запись на экране входа.
'@ | Set-Content -LiteralPath (Join-Path $destination 'КАК ЗАПУСТИТЬ.txt') -Encoding UTF8
Copy-Required 'packaging/QUICKSTART.txt' (Join-Path $destination 'ПОДРОБНАЯ ИНСТРУКЦИЯ.txt')

foreach ($relative in @('Dispetcher112.exe','_internal/dist/index.html','local_ai/voice/runtime/python.exe','local_ai/voice/models/gigaam/config.json','local_ai/voice/piper/FINAL_MODELS_29800/denis_29800.onnx','local_ai/models/Qwen3-4B-Instruct-2507-Q4_K_M.gguf','На одном ПК.lnk','В локальной сети.lnk')) {
    if (!(Test-Path -LiteralPath (Join-Path $destination $relative))) { throw "Неполная папка: $relative" }
}
Write-Output $destination
