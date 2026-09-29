#define AppVersion "0.8.20"
[Setup]
AppId={{A6F6F021-37DD-48BB-B651-76B37DD31A12}
AppName=Тренажёр 112
AppVersion={#AppVersion}
AppPublisher=Команда тренажёра 112
DefaultDirName={localappdata}\Programs\Dispetcher112
DefaultGroupName=Тренажёр 112
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\release\Dispetcher112-{#AppVersion}-installer
OutputBaseFilename=Dispetcher112-Setup-{#AppVersion}-win-x64
Compression=lzma2/fast
SolidCompression=yes
DiskSpanning=yes
DiskSliceSize=2000000000
SlicesPerDisk=1
CompressionThreads=4
WizardStyle=modern
DisableDirPage=no
AlwaysShowDirOnReadyPage=yes
UninstallDisplayIcon={app}\Dispetcher112.exe
DisableProgramGroupPage=yes
InfoAfterFile=QUICKSTART.txt
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; Flags: unchecked

[Files]
Source: "..\build\desktop-dist\Dispetcher112\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\local_ai\config.json"; DestDir: "{app}\local_ai"; Flags: ignoreversion
Source: "..\local_ai\manifest.json"; DestDir: "{app}\local_ai"; Flags: ignoreversion
Source: "..\local_ai\README.md"; DestDir: "{app}\local_ai"; Flags: ignoreversion
Source: "..\local_ai\LICENSE*"; DestDir: "{app}\local_ai"; Flags: ignoreversion
Source: "..\local_ai\runtime\cpu\*"; DestDir: "{app}\local_ai\runtime\cpu"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\local_ai\runtime\vulkan\*"; DestDir: "{app}\local_ai\runtime\vulkan"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\local_ai\models\Qwen3-4B-Instruct-2507-Q4_K_M.gguf"; DestDir: "{app}\local_ai\models"; Flags: ignoreversion nocompression
Source: "..\local_ai\models\Qwen3-0.6B-Q4_K_M.gguf"; DestDir: "{app}\local_ai\models"; Flags: ignoreversion nocompression
Source: "..\local_ai\downloads\MicrosoftEdgeWebView2RuntimeInstallerX64.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall

; Speech runs in its own bundled Python environment, independent of host Python.
Source: "..\local_ai\voice_worker.py"; DestDir: "{app}\local_ai"; Flags: ignoreversion
Source: "..\local_ai\speech_text.py"; DestDir: "{app}\local_ai"; Flags: ignoreversion
Source: "..\local_ai\voice\runtime\*"; DestDir: "{app}\local_ai\voice\runtime"; Excludes: "__pycache__\*,*.pyc"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\local_ai\voice\models\*"; DestDir: "{app}\local_ai\voice\models"; Flags: ignoreversion recursesubdirs createallsubdirs nocompression
Source: "..\local_ai\voice\builtin\*"; DestDir: "{app}\local_ai\voice\builtin"; Excludes: "*.build.json"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\local_ai\voice\fillers\*"; DestDir: "{app}\local_ai\voice\fillers"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Тренажёр 112"; Filename: "{app}\Dispetcher112.exe"
Name: "{autodesktop}\Тренажёр 112"; Filename: "{app}\Dispetcher112.exe"; Tasks: desktopicon

[Run]
Filename: "{tmp}\MicrosoftEdgeWebView2RuntimeInstallerX64.exe"; Parameters: "/silent /install"; StatusMsg: "Подготовка встроенного интерфейса WebView2…"; Flags: waituntilterminated; Check: NeedsWebView
Filename: "{app}\Dispetcher112.exe"; Description: "Запустить Тренажёр 112"; Flags: nowait postinstall skipifsilent

[Code]
function NeedsWebView: Boolean;
var Version: String;
begin
  Result := not ((RegQueryStringValue(HKCU, 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0')) or
    (RegQueryStringValue(HKLM32, 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0')));
end;
