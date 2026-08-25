; Instagram Reel Scraper — Inno Setup installer script
; Build: run install.bat (or ISCC.exe Reelminner.iss)

#define MyAppName "Instagram Reel Scraper"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "IRS Tools"
#define MyAppExeName "Reelminner.exe"

[Setup]
AppId={{8F2A6D1E-3C5B-4E7A-9B4F-5F1E0A2D9C31}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\Reelminner
DefaultGroupName={#MyAppName}
OutputDir=..\dist
OutputBaseFilename=Reelminner-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"

[Files]
; Onedir build: install the whole app folder (exe + _internal + browsers)
Source: "..\dist\Reelminner\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
