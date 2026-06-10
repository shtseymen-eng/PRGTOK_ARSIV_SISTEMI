@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

echo.
echo ╔══════════════════════════════════════════════════════════╗
echo ║        PRGTOK Arsiv Sistemi - EXE Build Script          ║
echo ║                    S.SEYMEN                              ║
echo ╚══════════════════════════════════════════════════════════╝
echo.

:: ─── Çalışma dizinini bu bat dosyasının üst klasörüne al ───────────────────
cd /d "%~dp0.."
set "ROOT=%CD%"
set "BUILD_DIR=%ROOT%\build"
set "DIST_DIR=%ROOT%\dist"
set "WORK_DIR=%BUILD_DIR%\work"

echo [1/6] Python kontrol ediliyor...
where python >nul 2>&1
if errorlevel 1 (
    echo HATA: Python bulunamadi!
    echo Python 3.10+ indirin: https://www.python.org/downloads/
    echo Kurulum sirasinda "Add Python to PATH" secenegini isaretleyin.
    pause
    exit /b 1
)

for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo [OK] Python %PYVER% bulundu.
echo.

:: ─── pip bağımlılıklarını kur ───────────────────────────────────────────────
echo [2/6] Python kutuphane bagimliliklar kuruluyor...
echo      (Zaten kurulu olanlar atlanir)
echo.

python -m pip install --upgrade pip --quiet

set PACKAGES=pyinstaller customtkinter pdfplumber pytesseract pillow pandas openpyxl

for %%p in (%PACKAGES%) do (
    echo      [%%p] kontrol ediliyor...
    python -m pip show %%p >nul 2>&1
    if errorlevel 1 (
        echo      [%%p] kuruluyor...
        python -m pip install %%p --quiet
        if errorlevel 1 (
            echo HATA: %%p kurulamadi!
            pause
            exit /b 1
        )
        echo      [%%p] kuruldu.
    ) else (
        echo      [%%p] zaten kurulu, atlanıyor.
    )
)

echo.
echo [OK] Tum Python kutuphaneleri hazir.
echo.

:: ─── PyInstaller ile .exe oluştur ──────────────────────────────────────────
echo [3/6] PyInstaller ile uygulama derleniyor...
echo      (Bu islem 2-5 dakika surebilir, lutfen bekleyin...)
echo.

if exist "%DIST_DIR%\PRGTOK" (
    echo      Eski dist klasoru temizleniyor...
    rmdir /s /q "%DIST_DIR%\PRGTOK"
)

python -m PyInstaller "%BUILD_DIR%\PRGTOK.spec" ^
    --distpath "%DIST_DIR%" ^
    --workpath "%WORK_DIR%" ^
    --noconfirm ^
    --log-level WARN

if errorlevel 1 (
    echo.
    echo HATA: PyInstaller derleme basarisiz!
    echo Build/work klasorundeki gecici dosyalara bakin.
    pause
    exit /b 1
)

echo.
echo [OK] Uygulama derlendi: %DIST_DIR%\PRGTOK\PRGTOK.exe
echo.

:: ─── UPX ile sıkıştırma (opsiyonel, varsa) ─────────────────────────────────
echo [4/6] UPX sıkistirma (opsiyonel)...
where upx >nul 2>&1
if not errorlevel 1 (
    echo      UPX bulundu, exe sikistiriliyor...
) else (
    echo      UPX bulunamadi, atlanıyor. (isteğe baglı: https://upx.github.io)
)
echo.

:: ─── Inno Setup ile kurulum dosyası oluştur ─────────────────────────────────
echo [5/6] Inno Setup ile kurulum dosyasi olusturuluyor...

:: Inno Setup'ın olası kurulum yollarını dene
set "ISCC="
for %%p in (
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    "C:\Program Files\Inno Setup 6\ISCC.exe"
    "C:\Program Files (x86)\Inno Setup 5\ISCC.exe"
) do (
    if exist %%p set "ISCC=%%p"
)

if not defined ISCC (
    echo      UYARI: Inno Setup bulunamadi.
    echo      Kurulum dosyasi olusturulamadi.
    echo.
    echo      Inno Setup indirin: https://jrsoftware.org/isdl.php
    echo      Kurduktan sonra bu scripti tekrar calistirin.
    echo.
    echo      Simdlik sadece uygulama klasoru hazir:
    echo      %DIST_DIR%\PRGTOK\PRGTOK.exe
    echo.
    goto :dist_only
)

if not exist "%DIST_DIR%\installer" mkdir "%DIST_DIR%\installer"

%ISCC% "%BUILD_DIR%\installer.iss"

if errorlevel 1 (
    echo HATA: Inno Setup basarisiz!
    pause
    exit /b 1
)

echo.
echo [OK] Kurulum dosyasi hazir:
echo      %DIST_DIR%\installer\PRGTOK_Kurulum_v1.0.2.exe
echo.
goto :done

:dist_only
echo [5/6] Inno Setup atlandi - sadece portable klasor hazir.
echo.

:done
:: ─── Özet ───────────────────────────────────────────────────────────────────
echo [6/6] Derleme tamamlandi!
echo.
echo ╔══════════════════════════════════════════════════════════╗
echo ║  HAZIR DOSYALAR:                                         ║
echo ║                                                          ║
if exist "%DIST_DIR%\installer\PRGTOK_Kurulum_v1.0.2.exe" (
echo ║  KURULUM EXE:                                            ║
echo ║  dist\installer\PRGTOK_Kurulum_v1.0.2.exe               ║
echo ║  (Bu dosyayi paylasabilirsiniz)                          ║
echo ║                                                          ║
)
echo ║  PORTABLE UYGULAMA:                                      ║
echo ║  dist\PRGTOK\PRGTOK.exe                                  ║
echo ║  (Dogrudan calistirilabilir, tum dosyalar bu klasorde)   ║
echo ╚══════════════════════════════════════════════════════════╝
echo.
echo NOT: Kurulum EXE'si hedefe kurulurken Tesseract OCR'i
echo      (Turkce dil paketi dahil) otomatik indirir ve kurar.
echo      Hedef PC'de Tesseract zaten varsa atlar.
echo.
pause
