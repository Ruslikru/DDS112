#define AppVersion "0.8.26"
#ifndef PayloadDir
#define PayloadDir "..\release\Dispetcher112-fix-bilets-20261020-r12"
#endif
#ifndef BuildTag
#define BuildTag "20261020-r12"
#endif
[Setup]
AppId={{A6F6F021-37DD-48BB-B651-76B37DD31A12}{param:VerificationInstance|}
AppName=Тренажёр 112
AppVersion={#AppVersion}
AppVerName=Тренажёр 112 {#AppVersion}{param:VerificationInstance|}
AppPublisher=Команда тренажёра 112
DefaultDirName={autopf}\Dispetcher112
DefaultGroupName=Тренажёр 112
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\release\Dispetcher112-{#AppVersion}-{#BuildTag}-installer
OutputBaseFilename=Dispetcher112-Setup-{#AppVersion}-win-x64
Compression=none
SolidCompression=no
DiskSpanning=yes
DiskSliceSize=2000000000
SlicesPerDisk=1
CompressionThreads=4
WizardStyle=modern
DisableDirPage=no
AlwaysShowDirOnReadyPage=yes
UninstallDisplayIcon={app}\Dispetcher112.exe
DisableProgramGroupPage=yes
UsePreviousLanguage=no
UsePreviousPrivileges=no
CloseApplications=yes
RestartApplications=no
SetupIconFile=assets\trainer.ico

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicons"; Description: "Создать два ярлыка на рабочем столе: на одном ПК и в локальной сети"

[Files]
; One verified payload is shared by the portable release and the installer.
Source: "{#PayloadDir}\*"; DestDir: "{app}"; Excludes: "*.lnk,*.gguf"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#PayloadDir}\local_ai\models\Qwen3-4B-Instruct-2507-Q4_K_M.gguf"; DestDir: "{app}\local_ai\models"; Flags: ignoreversion nocompression
Source: "..\local_ai\downloads\MicrosoftEdgeWebView2RuntimeInstallerX64.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall

[Icons]
Name: "{group}\На одном ПК"; Filename: "{app}\Dispetcher112.exe"; Parameters: "--local"; WorkingDir: "{app}"; Check: not VerificationInstall
Name: "{group}\В локальной сети"; Filename: "{app}\Dispetcher112.exe"; Parameters: "--lan"; WorkingDir: "{app}"; Check: not VerificationInstall
Name: "{code:DesktopShortcutRoot}\Тренажёр 112 — На одном ПК"; Filename: "{app}\Dispetcher112.exe"; Parameters: "--local"; WorkingDir: "{app}"; Tasks: desktopicons
Name: "{code:DesktopShortcutRoot}\Тренажёр 112 — В локальной сети"; Filename: "{app}\Dispetcher112.exe"; Parameters: "--lan"; WorkingDir: "{app}"; Tasks: desktopicons

[Run]
Filename: "{tmp}\MicrosoftEdgeWebView2RuntimeInstallerX64.exe"; Parameters: "/silent /install"; StatusMsg: "Подготовка встроенного интерфейса WebView2…"; Flags: waituntilterminated; Check: NeedsWebView
Filename: "{app}\Dispetcher112.exe"; Parameters: "--local"; Description: "Запустить Тренажёр 112 на одном ПК"; Flags: nowait postinstall skipifsilent

[Code]
function VerificationInstall: Boolean;
begin
  Result := ExpandConstant('{param:VerificationInstance|}') <> '';
end;

function DesktopShortcutRoot(Param: String): String;
begin
  { Isolated installation checks must preserve existing shortcuts and uninstall registration. }
  if VerificationInstall then
    Result := ExpandConstant('{app}\Проверка ярлыков')
  else
    Result := ExpandConstant('{autodesktop}');
end;

function NeedsWebView: Boolean;
var Version: String;
begin
  Result := not ((RegQueryStringValue(HKCU, 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0')) or
    (RegQueryStringValue(HKLM32, 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0')));
end;
