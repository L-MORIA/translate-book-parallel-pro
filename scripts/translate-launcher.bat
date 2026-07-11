@echo off
chcp 65001 >nul
title Translate Book Pro

:: ============================================================
:: Translate Book Parallel Pro — Launcher
:: Supported: EPUB, PDF, DOCX, TXT
:: Output: EPUB + DOCX + PDF + HTML
:: ============================================================

setlocal enabledelayedexpansion

set "REPO_DIR=%~dp0.."
set "SCRIPTS_DIR=%REPO_DIR%\scripts"
set "OUTPUT_ROOT=%REPO_DIR%\translations"

:: ─── Header ──────────────────────────────────────────────────
cls
echo.
echo ============================================
echo   translate-book-parallel-pro  v1.0
echo   AI-powered book translation (Hermes)
echo ============================================
echo.

:: ─── Input file ──────────────────────────────────────────────
:input_file
set "INPUT_FILE=%1"
if "%INPUT_FILE%"=="" (
    echo Opening file picker...
    for /f "usebackq tokens=*" %%i in (`powershell -Command "Add-Type -AssemblyName System.Windows.Forms; $f = New-Object System.Windows.Forms.OpenFileDialog; $f.Filter = 'Books (EPUB,PDF,DOCX,TXT)|*.epub;*.pdf;*.docx;*.txt|EPUB files|*.epub|PDF files|*.pdf|DOCX files|*.docx|TXT files|*.txt|All files|*.*'; $f.Title = 'Select a book to translate'; if ($f.ShowDialog() -eq 'OK') { Write-Output $f.FileName }"`) do set "INPUT_FILE=%%i"
    echo.
)

set "INPUT_FILE=%INPUT_FILE:"=%"

if not exist "%INPUT_FILE%" (
    echo No file selected. Exiting.
    echo.
    pause
    exit /b 1
)

:: ─── Detect format ───────────────────────────────────────────
for %%i in ("%INPUT_FILE%") do set "EXT=%%~xi"
set "EXT=%EXT:.=%"

echo File: %INPUT_FILE%
echo Format: %EXT%

echo %EXT% | findstr /i "epub pdf docx txt" >nul
if errorlevel 1 (
    echo Format .%EXT% not supported.
    echo Supported: EPUB, PDF, DOCX, TXT
    pause
    exit /b 1
)
echo.

:: ─── Target language ─────────────────────────────────────────
:input_lang
echo Target language code:
echo   ru  = Russian     en  = English
echo   zh  = Chinese     de  = German
echo   fr  = French      es  = Spanish
echo   ja  = Japanese    ko  = Korean
echo.
set /p "TARGET_LANG=^> "
if "%TARGET_LANG%"=="" set "TARGET_LANG=ru"
echo.

:: ─── Book name ───────────────────────────────────────────────
for %%i in ("%INPUT_FILE%") do set "BOOK_NAME=%%~ni"
echo Book: %BOOK_NAME%
echo.

:: ─── Create output dir ───────────────────────────────────────
for /f "usebackq tokens=*" %%d in (`powershell -Command "Get-Date -Format 'yyyy-MM-dd_HH-mm-ss'"`) do set "TIMESTAMP=%%d"
set "OUT_DIR=%OUTPUT_ROOT%\%BOOK_NAME%_%TIMESTAMP%"
md "%OUT_DIR%" 2>nul

echo Output: %OUT_DIR%
echo.

:: ─── Ensure dependencies ────────────────────────────────────
echo Installing dependencies (pypandoc, beautifulsoup4)...
python "%SCRIPTS_DIR%\setup.py" >nul 2>&1
pip install pypandoc beautifulsoup4 >nul 2>&1
echo Done.
echo.

:: ─── Step 1: Convert ─────────────────────────────────────────
echo [1/2] Converting to chunks...
echo.

set "START_TIME=%TIME%"
echo Started: %START_TIME%
echo.

python "%SCRIPTS_DIR%\convert.py" "%INPUT_FILE%" --olang %TARGET_LANG% --temp-root "%OUT_DIR%"
if errorlevel 1 (
    echo Conversion failed!
    pause
    exit /b 1
)

echo.
echo Done - conversion complete.
echo.

:: ─── Pause for Hermes translation ────────────────────────────
echo ============================================
echo   NOW TRANSLATE VIA HERMES AGENT
echo ============================================
echo.
echo Tell the agent in chat:
echo.
echo   Translate the book in "%OUT_DIR%\%BOOK_NAME%_temp" to %TARGET_LANG%
echo.
echo When done, press any key...
pause >nul

:: ─── Step 2: Build ───────────────────────────────────────────
echo.
echo [2/2] Building output formats...
echo.

set "TEMP_DIR=%OUT_DIR%\%BOOK_NAME%_temp"
python "%SCRIPTS_DIR%\merge_and_build.py" --temp-dir "%TEMP_DIR%" --title "%BOOK_NAME%" --cleanup
if errorlevel 1 (
    echo Build failed - translation may not be complete yet.
    pause
    exit /b 1
)

:: ─── Move results ────────────────────────────────────────────
if exist "%TEMP_DIR%\book.epub" (
    move "%TEMP_DIR%\book.epub" "%OUT_DIR%\" >nul 2>&1
    move "%TEMP_DIR%\book.docx" "%OUT_DIR%\" >nul 2>&1
    move "%TEMP_DIR%\book.pdf"  "%OUT_DIR%\" >nul 2>&1
    move "%TEMP_DIR%\book.html" "%OUT_DIR%\" >nul 2>&1
)

:: ─── Finish ──────────────────────────────────────────────────
set "END_TIME=%TIME%"

echo.
echo ============================================
echo        TRANSLATION COMPLETE!
echo ============================================
echo.
echo Folder: %OUT_DIR%
echo.
echo Files:
dir "%OUT_DIR%\book.*" /b 2>nul
echo.
echo Started: %START_TIME%
echo Ended:   %END_TIME%
echo.

start explorer "%OUT_DIR%"

echo Press Enter to exit...
pause >nul
exit /b 0
