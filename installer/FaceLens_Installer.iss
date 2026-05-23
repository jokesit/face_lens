#define MyAppName "FaceLens"
#ifndef MyAppVersion
#define MyAppVersion "0.16"
#endif
#define MyAppPublisher "FaceLens Pharmacy Standalone"
#define MyAppExeName "FaceLens.exe"
#define MyAppIcon "..\assets\logo.ico"

[Setup]
AppId={{9B7A7F69-4F47-45A8-8CC0-0F9D5F8A2B16}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\FaceLens
DefaultGroupName=FaceLens
DisableProgramGroupPage=yes
OutputDir=..\release
OutputBaseFilename=FaceLens_{#MyAppVersion}_Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=admin
UninstallDisplayIcon={app}\FaceLens.ico
SetupIconFile={#MyAppIcon}
SetupLogging=yes

[Languages]
Name: "thai"; MessagesFile: "compiler:Languages\Thai.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a FaceLens desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: checkedonce

[Dirs]
Name: "{commonappdata}\FaceLens"; Permissions: users-modify
Name: "{commonappdata}\FaceLens\data"; Permissions: users-modify
Name: "{commonappdata}\FaceLens\backups"; Permissions: users-modify
Name: "{commonappdata}\FaceLens\logs"; Permissions: users-modify
Name: "{commonappdata}\FaceLens\temp_files"; Permissions: users-modify
Name: "{commonappdata}\FaceLens\.deepface"; Permissions: users-modify
Name: "{commonappdata}\FaceLens\.deepface\weights"; Permissions: users-modify
Name: "{app}\assets"

[Files]
; Main PyInstaller onedir bundle. Build dist\FaceLens first.
Source: "..\dist\FaceLens\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; Copy the icon to a stable top-level location. Desktop/Start Menu shortcuts
; should not point into PyInstaller's _internal folder because that layout can
; change between PyInstaller versions and may not be refreshed by Windows icon cache.
Source: "..\assets\logo.ico"; DestDir: "{app}"; DestName: "FaceLens.ico"; Flags: ignoreversion
Source: "..\assets\logo.ico"; DestDir: "{app}\assets"; DestName: "logo.ico"; Flags: ignoreversion
Source: "..\assets\logo.png"; DestDir: "{app}\assets"; DestName: "logo.png"; Flags: ignoreversion skipifsourcedoesntexist

; Marker that tells FaceLens to keep writable data in C:\ProgramData\FaceLens.
Source: "installed_mode.txt"; DestDir: "{app}"; Flags: ignoreversion

; Thai documentation for pharmacies and support.
Source: "..\README_TH.md"; DestDir: "{app}\docs"; Flags: ignoreversion skipifsourcedoesntexist
Source: "..\RELEASE_NOTES.md"; DestDir: "{app}\docs"; Flags: ignoreversion skipifsourcedoesntexist
Source: "..\docs\*.md"; DestDir: "{app}\docs"; Flags: ignoreversion skipifsourcedoesntexist

[Icons]
Name: "{group}\FaceLens"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\FaceLens.ico"; IconIndex: 0
Name: "{autodesktop}\FaceLens"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\FaceLens.ico"; IconIndex: 0; Tasks: desktopicon
Name: "{group}\FaceLens User Guide"; Filename: "{app}\docs\README_TH.md"; IconFilename: "{app}\FaceLens.ico"; IconIndex: 0
Name: "{group}\Uninstall FaceLens"; Filename: "{uninstallexe}"; IconFilename: "{app}\FaceLens.ico"; IconIndex: 0

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Open FaceLens"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Do not delete {commonappdata}\FaceLens\data or backups automatically.
; Customer data should only be removed by explicit user/admin action.
Type: filesandordirs; Name: "{commonappdata}\FaceLens\temp_files"
Type: filesandordirs; Name: "{commonappdata}\FaceLens\logs"
