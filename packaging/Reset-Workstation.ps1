[CmdletBinding(SupportsShouldProcess=$true)]
param(
    [ValidateSet('Connection','All')][string]$Mode='Connection',
    [string]$DataDir=(Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'Dispetcher112')
)
$ErrorActionPreference='Stop'

function Assert-SafePath([string]$Path) {
    $full=[IO.Path]::GetFullPath($Path).TrimEnd('\')
    $windows=[IO.Path]::GetFullPath($env:SystemRoot).TrimEnd('\')
    if($full -eq [IO.Path]::GetPathRoot($full).TrimEnd('\') -or
       $full.StartsWith($windows+'\',[StringComparison]::OrdinalIgnoreCase) -or
       $full.Equals($windows,[StringComparison]::OrdinalIgnoreCase) -or
       $windows.StartsWith($full+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Системные каталоги изменять запрещено.' }
    $cursor=$full
    while($cursor) {
        if(Test-Path -LiteralPath $cursor) {
            $item=Get-Item -LiteralPath $cursor -Force
            if($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw ('Ссылки и точки подключения не поддерживаются: '+$cursor) }
        }
        $parent=Split-Path $cursor -Parent
        if($parent -eq $cursor){break};$cursor=$parent
    }
    return $full
}

function Get-Inventory([string]$Path) {
    $files=[Collections.Generic.List[string]]::new()
    $dirs=[Collections.Generic.List[string]]::new()
    $item=Get-Item -LiteralPath $Path -Force
    if(-not $item.PSIsContainer) {$files.Add($item.FullName)}
    else {
        $pending=[Collections.Generic.Stack[string]]::new();$pending.Push($item.FullName)
        while($pending.Count) {
            $dir=$pending.Pop();$dirs.Add($dir)
            foreach($child in Get-ChildItem -LiteralPath $dir -Force) {
                if($child.Attributes -band [IO.FileAttributes]::ReparsePoint) {throw ('Обнаружена ссылка: '+$child.FullName)}
                if($child.PSIsContainer){$pending.Push($child.FullName)}else{$files.Add($child.FullName)}
            }
        }
    }
    return [pscustomobject]@{Files=@($files.ToArray());Directories=@($dirs.ToArray())}
}

function Assert-VerifiedManifest([string]$ManifestPath,$Inventory) {
    $manifest=Get-Content -LiteralPath $ManifestPath -Encoding UTF8 -Raw | ConvertFrom-Json
    if($manifest.status -ne 'verified') {throw 'Резервная копия не прошла проверку. Сброс отменён.'}
    if(@($manifest.files).Count -ne @($Inventory.Files).Count) {throw 'Неполная копия файлов. Сброс отменён.'}
    foreach($file in $Inventory.Files) {
        $row=@($manifest.files | Where-Object {$_.source -eq $file})
        if($row.Count -ne 1 -or -not (Test-Path -LiteralPath $row[0].backup -PathType Leaf)) {throw ('Нет копии: '+$file)}
        $original=Get-Item -LiteralPath $file
        $copy=Get-Item -LiteralPath $row[0].backup
        if($original.Length -ne $row[0].size -or $copy.Length -ne $original.Length -or
           (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash -ne $row[0].sha256 -or
           (Get-FileHash -LiteralPath $row[0].backup -Algorithm SHA256).Hash -ne $row[0].sha256) {throw ('Не совпала SHA-256: '+$file)}
    }
    foreach($dir in $Inventory.Directories) {
        $row=@($manifest.directories | Where-Object {$_.source -eq $dir})
        if($row.Count -ne 1 -or -not (Test-Path -LiteralPath $row[0].backup -PathType Container)) {throw ('Нет копии каталога: '+$dir)}
    }
}

function Backup-Verified([string]$Path,$Inventory) {
    $session=Join-Path ([Environment]::GetFolderPath('UserProfile')) ('Codex Backups\Deleted\Trainer112-reset-'+(Get-Date -Format 'yyyyMMdd-HHmmss')+'-'+[guid]::NewGuid().ToString('N').Substring(0,8))
    $session=Assert-SafePath $session
    New-Item -ItemType Directory -Path $session | Out-Null
    $helper='C:\AI\TelegramAgent\Codex Telegram Remote\Codex Telegram Remote.exe'
    if(Test-Path -LiteralPath $helper -PathType Leaf) {
        $stdout=Join-Path $session 'helper.stdout.log';$stderr=Join-Path $session 'helper.stderr.log'
        $process=Start-Process -WindowStyle Hidden -FilePath $helper -ArgumentList @('--backup-before-delete',('"'+$Path+'"')) -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru -Wait
        if($process.ExitCode -ne 0){throw ('Помощник резервного копирования завершился с ошибкой. См. '+$stderr)}
        $manifest=@(Get-Content -LiteralPath $stdout -Encoding UTF8 | Where-Object {$_.Trim().EndsWith('manifest.json')})
        if(-not $manifest.Count){throw 'Помощник не сообщил путь manifest.json. Ничего не изменено.'}
        $manifest=$manifest[-1].Trim()
    } else {
        $destination=Join-Path $session 'data';$rows=@();$directories=@()
        foreach($dir in $Inventory.Directories) {
            $relative=$dir.Substring($Path.Length).TrimStart('\');$copy=Join-Path $destination $relative
            New-Item -ItemType Directory -Path $copy -Force | Out-Null
            $directories+=@{source=$dir;backup=$copy}
        }
        foreach($file in $Inventory.Files) {
            $relative=if($Inventory.Directories.Count){$file.Substring($Path.Length).TrimStart('\')}else{Split-Path $file -Leaf}
            $copy=Join-Path $destination $relative
            New-Item -ItemType Directory -Path (Split-Path $copy -Parent) -Force | Out-Null
            Copy-Item -LiteralPath $file -Destination $copy
            $rows+=@{source=$file;backup=$copy;size=(Get-Item -LiteralPath $file).Length;sha256=(Get-FileHash -LiteralPath $copy -Algorithm SHA256).Hash.ToLowerInvariant()}
        }
        $manifest=Join-Path $session 'manifest.json'
        @{status='verified';sources=@($Path);files=@($rows);directories=@($directories);createdAt=(Get-Date).ToUniversalTime().ToString('o')} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $manifest -Encoding UTF8
    }
    Assert-VerifiedManifest $manifest $Inventory
    return $manifest
}

try {
    $data=Assert-SafePath $DataDir
    if((Split-Path $data -Leaf) -notlike 'Dispetcher112*'){throw 'Выберите каталог данных Dispetcher112, а не родительскую папку.'}
    $target=if($Mode -eq 'Connection'){Join-Path $data 'classroom.json'}else{$data}
    $target=Assert-SafePath $target
    if(-not (Test-Path -LiteralPath $target)){Write-Host ('Сбрасывать нечего: '+$target);exit 0}
    $archive=$data+'.before-reset-'+(Get-Date -Format 'yyyyMMdd-HHmmss')+'-'+[guid]::NewGuid().ToString('N').Substring(0,8)
    if($Mode -eq 'All'){$archive=Assert-SafePath $archive}
    Write-Host 'Будет изменён только этот путь:';Write-Host $target
    if($Mode -eq 'Connection'){Write-Host 'Сбросится подключение. Ученики, билеты, результаты и звук сохранятся.'}
    else{Write-Host 'Будет создан чистый профиль. Старый профиль останется здесь:';Write-Host $archive}
    Write-Host ('Постоянная копия: '+(Join-Path ([Environment]::GetFolderPath('UserProfile')) 'Codex Backups\Deleted'))
    if(-not $PSCmdlet.ShouldProcess($target,'Сброс с проверенной резервной копией')){exit 0}
    $running=Get-CimInstance Win32_Process | Where-Object {$_.Name -eq 'Dispetcher112.exe' -or ($_.Name -match '^python' -and $_.CommandLine -like '*packaging/desktop_launcher.py*')}
    if($running){throw 'Сначала закройте все окна Тренажёра 112, затем повторите запуск скрипта.'}
    $inventory=Get-Inventory $target
    $required='RESET '+$Mode.ToUpperInvariant()
    $answer=Read-Host ('Для отдельного подтверждения введите '+$required)
    if($answer -cne $required){Write-Host 'Отменено. Ничего не изменено.';exit 0}
    $manifest=Backup-Verified $target $inventory
    if($Mode -eq 'Connection') {
        [IO.File]::WriteAllText($target,'{}',[Text.UTF8Encoding]::new($false))
    } else {
        if((Split-Path $archive -Parent) -ne (Split-Path $data -Parent)){throw 'Некорректный путь архива.'}
        Rename-Item -LiteralPath $data -NewName (Split-Path $archive -Leaf)
        New-Item -ItemType Directory -Path $data | Out-Null
    }
    Write-Host 'Сброс выполнен. Проверенная резервная копия:';Write-Host $manifest
    Write-Host 'Запустите ярлык «В локальной сети», войдите администратором и выберите роль ПК.'
    if($Mode -eq 'All'){Write-Host 'Для чистого класса: admin / 12345678. Остальные ПК потребуется подключить заново.'}
    else{Write-Host 'Используйте существующий пароль администратора. Для нового ПК: admin / 12345678.'}
    Write-Host 'Резервные копии и старый профиль автоматически не удаляются.'
} catch {Write-Error $_;exit 1}
