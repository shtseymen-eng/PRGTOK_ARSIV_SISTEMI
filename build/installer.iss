; ============================================================
; Inno Setup Script – PRGTOK Arsiv Sistemi Kurulum Dosyasi
; Inno Setup 6.x gerektirir: https://jrsoftware.org/isdl.php
; ============================================================

#define AppName      "PRGTOK Arsiv Sistemi"
#define AppVersion   "1.0.2"
#define AppPublisher "S.SEYMEN"
#define AppExeName   "PRGTOK.exe"
#define DistDir      "..\dist\PRGTOK"

; --- Tesseract OCR (Windows 64-bit, UB-Mannheim)
; Otomatik indirilir; isterseniz yerel kopyayı buraya yazın:
#define TesseractURL "https://digi.bib.uni-mannheim.de/tesseract/tesseract-ocr-w64-setup-5.4.0.20240606.exe"
#define TesseractEXE "tesseract-ocr-w64-setup.exe"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\PRGTOK
DefaultGroupName={#AppName}
AllowNoIcons=yes
LicenseFile=
OutputDir=..\dist\installer
OutputBaseFilename=PRGTOK_Kurulum_v{#AppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\{#AppExeName}
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"

[CustomMessages]
turkish.TesseractCheck=Tesseract OCR kontrol ediliyor...
turkish.TesseractInstalling=Tesseract OCR (Turkce dil paketi dahil) kuruluyor...
turkish.TesseractSkipped=Tesseract OCR zaten yuklu, atlanıyor.
turkish.TesseractFailed=Tesseract OCR indirilemedi veya kurulamadi.%nOCR ozelligi calismayabilir.
turkish.Downloading=Tesseract indiriliyor, lutfen bekleyin...

[Tasks]
Name: "desktopicon"; Description: "Masaustu kisayolu olustur"; GroupDescription: "Ek secenekler:"; Flags: checked
Name: "startmenuicon"; Description: "Baslat menusu kisayolu olustur"; GroupDescription: "Ek secenekler:"; Flags: checked

[Files]
; --- Ana uygulama dosyalari (PyInstaller dist klasoru)
Source: "{#DistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\Kaldır"; Filename: "{uninstallexe}"
Name: "{commondesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon
Name: "{commonstartmenu}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: startmenuicon

[Run]
; Kurulum tamamlandiktan sonra uygulamayi baslat
Filename: "{app}\{#AppExeName}"; Description: "PRGTOK'u simdi baslat"; \
  Flags: nowait postinstall skipifsilent

[Code]

var
  TesseractPage: TWizardPage;
  TesseractStatus: TLabel;
  ProgressBar: TProgressBar;

{ ── Tesseract kayit defterinde kurulu mu? ──────────────────────────────── }
function TesseractInstalled: Boolean;
var
  Path: String;
begin
  Result := RegQueryStringValue(HKLM, 'SOFTWARE\Tesseract-OCR', 'InstallDir', Path)
         or RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\Tesseract-OCR', 'InstallDir', Path)
         or FileExists(ExpandConstant('{pf}\Tesseract-OCR\tesseract.exe'))
         or FileExists(ExpandConstant('{pf64}\Tesseract-OCR\tesseract.exe'));
end;

{ ── Internetten dosya indir (WinHTTP) ──────────────────────────────────── }
function DownloadFile(URL, Dest: String): Boolean;
var
  WinHTTP: Variant;
  Stream: Variant;
  Buffer: AnsiString;
  BSize: Integer;
begin
  Result := False;
  try
    WinHTTP := CreateOleObject('WinHttp.WinHttpRequest.5.1');
    WinHTTP.Open('GET', URL, False);
    WinHTTP.SetOption(6, False);   { WinHttpRequestOption_EnableRedirects }
    WinHTTP.Send('');
    if WinHTTP.Status = 200 then
    begin
      Stream := CreateOleObject('ADODB.Stream');
      Stream.Type_ := 1;  { Binary }
      Stream.Open;
      Stream.Write(WinHTTP.ResponseBody);
      Stream.SaveToFile(Dest, 2);
      Stream.Close;
      Result := FileExists(Dest);
    end;
  except
    Result := False;
  end;
end;

{ ── Tesseract kurulumu ─────────────────────────────────────────────────── }
procedure InstallTesseract;
var
  TempDir, TessExe: String;
  ResultCode: Integer;
begin
  if TesseractInstalled then
  begin
    { Zaten kurulu – atla }
    MsgBox(ExpandConstant('{cm:TesseractSkipped}'), mbInformation, MB_OK);
    Exit;
  end;

  TempDir := ExpandConstant('{tmp}');
  TessExe := TempDir + '\' + '{#TesseractEXE}';

  MsgBox(ExpandConstant('{cm:Downloading}'), mbInformation, MB_OK);

  if not DownloadFile('{#TesseractURL}', TessExe) then
  begin
    MsgBox(ExpandConstant('{cm:TesseractFailed}'), mbError, MB_OK);
    Exit;
  end;

  { Sessiz kurulum: /S = sessiz, tur dil paketi dahil }
  Exec(TessExe,
       '/S /COMPONENTS=langfiles\tur',
       '', SW_HIDE, ewWaitUntilTerminated, ResultCode);

  if ResultCode <> 0 then
    MsgBox(ExpandConstant('{cm:TesseractFailed}'), mbError, MB_OK);

  { Geçici dosyayı sil }
  DeleteFile(TessExe);
end;

{ ── Kurulum tamamlandiktan sonra Tesseract kur ─────────────────────────── }
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    InstallTesseract;
end;
