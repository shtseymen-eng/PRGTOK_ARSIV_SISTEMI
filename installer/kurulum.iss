; PRGTOK Arsiv Sistemi - Inno Setup Kurulum Scripti
; Bu script GitHub Actions tarafindan otomatik calistirilir.
; Amac: tek tikla calisan bir Setup.exe uretmek; masaustu ve baslat
; menusu kisayollarini otomatik olusturmak; dogru ikonu kullanmak.

#define MyAppName "PRGTOK Arsiv Sistemi"
#define MyAppVersion "2.4.0"
#define MyAppPublisher "Poliport"
#define MyAppExeName "PRGTOK_ARSIV_SISTEMI.exe"

[Setup]
AppId={{B7E1B2D4-4F1A-4C9E-9B3A-7C2D5E8A1F00}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=cikti
OutputBaseFilename=PRGTOK_Arsiv_Kurulum_v{#MyAppVersion}
SetupIconFile=..\assets\app_icon.ico
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"

[Tasks]
Name: "desktopicon"; Description: "Masaüstü simgesi oluştur"; GroupDescription: "Ek simgeler:"; Flags: checkedonce

[Files]
Source: "..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; IconFilename: "{app}\{#MyAppExeName}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
